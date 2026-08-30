from contextlib import asynccontextmanager
from uuid import UUID
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from apps.core.config import settings
from apps.core.db import Base, engine, get_db
from apps.core.models import AuditLog, DeploymentJob, InviteEvent, Plan, Server, User
from apps.core.services.docker import DockerProvisioner
from apps.core.services.groq import GroqService
from apps.core.services.pterodactyl import PterodactylService


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.environment == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="ArveX Hosting API", version="0.1.0", lifespan=lifespan)
groq = GroqService()


class PlanIn(BaseModel):
    guild_id: int
    name: str = Field(min_length=2, max_length=100)
    description: str = ""
    kind: str = "vps"
    required_invites: int = Field(ge=0)
    ram_mb: int = Field(gt=0)
    cpu_percent: int = Field(gt=0)
    disk_mb: int = Field(gt=0)
    image: str | None = None
    egg_id: int | None = None
    docker_image: str | None = None
    enabled: bool = True
    sort_order: int = 0
    config: dict = Field(default_factory=dict)


class ServerCreateIn(BaseModel):
    plan_id: UUID
    name: str = Field(min_length=2, max_length=80)


class AIIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class InviteEventIn(BaseModel):
    guild_id: int
    inviter_discord_id: int
    invited_discord_id: int
    code: str


class MovePlanIn(BaseModel):
    direction: str = Field(pattern="^(up|down)$")


async def current_user(discord_id: int = Header(alias="X-Discord-Id"), db: AsyncSession = Depends(get_db)) -> User:
    result = await db.execute(select(User).where(User.discord_id == discord_id))
    user = result.scalar_one_or_none()
    if not user:
        user = User(discord_id=discord_id, username=f"discord-{discord_id}")
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


def require_admin(discord_id: int):
    if discord_id not in settings.admin_ids:
        raise HTTPException(status_code=403, detail="Admin access required")


def require_internal(secret: str):
    if secret != settings.internal_api_secret:
        raise HTTPException(status_code=401, detail="Invalid internal credential")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "arvex-api"}


@app.get("/api/v1/plans")
async def list_plans(guild_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Plan).where(Plan.guild_id == guild_id, Plan.enabled.is_(True)).order_by(Plan.sort_order, Plan.required_invites))
    return result.scalars().all()


@app.post("/api/v1/admin/plans")
async def create_plan(payload: PlanIn, x_discord_id: int = Header(alias="X-Discord-Id"), db: AsyncSession = Depends(get_db)):
    require_admin(x_discord_id)
    plan = Plan(**payload.model_dump())
    db.add(plan)
    db.add(AuditLog(actor_discord_id=x_discord_id, guild_id=payload.guild_id, action="plan.create", target=payload.name, data=payload.model_dump()))
    await db.commit()
    await db.refresh(plan)
    return plan


@app.patch("/api/v1/admin/plans/{plan_id}")
async def update_plan(plan_id: UUID, payload: PlanIn, x_discord_id: int = Header(alias="X-Discord-Id"), db: AsyncSession = Depends(get_db)):
    require_admin(x_discord_id)
    plan = await db.get(Plan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    for key, value in payload.model_dump().items():
        setattr(plan, key, value)
    db.add(AuditLog(actor_discord_id=x_discord_id, guild_id=payload.guild_id, action="plan.update", target=str(plan_id), data=payload.model_dump()))
    await db.commit()
    await db.refresh(plan)
    return plan


@app.post("/api/v1/admin/plans/{plan_id}/move")
async def move_plan(plan_id: UUID, payload: MovePlanIn, x_discord_id: int = Header(alias="X-Discord-Id"), db: AsyncSession = Depends(get_db)):
    require_admin(x_discord_id)
    plan = await db.get(Plan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    step = -1 if payload.direction == "up" else 1
    result = await db.execute(select(Plan).where(Plan.guild_id == plan.guild_id).order_by(Plan.sort_order, Plan.created_at))
    plans = list(result.scalars())
    try:
        index = plans.index(plan)
    except ValueError:
        raise HTTPException(404, "Plan not found")
    target = index + step
    if target < 0 or target >= len(plans):
        return {"ok": True, "moved": False}
    other = plans[target]
    plan.sort_order, other.sort_order = other.sort_order, plan.sort_order
    db.add(AuditLog(actor_discord_id=x_discord_id, guild_id=plan.guild_id, action="plan.move", target=str(plan_id), data={"direction": payload.direction}))
    await db.commit()
    return {"ok": True, "moved": True}


@app.delete("/api/v1/admin/plans/{plan_id}")
async def delete_plan(plan_id: UUID, x_discord_id: int = Header(alias="X-Discord-Id"), db: AsyncSession = Depends(get_db)):
    require_admin(x_discord_id)
    plan = await db.get(Plan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    plan.enabled = False
    db.add(AuditLog(actor_discord_id=x_discord_id, guild_id=plan.guild_id, action="plan.disable", target=str(plan_id), data={}))
    await db.commit()
    return {"ok": True}


@app.post("/api/v1/internal/invites/join")
async def invite_join(payload: InviteEventIn, x_internal_secret: str = Header(alias="X-Internal-Secret"), db: AsyncSession = Depends(get_db)):
    require_internal(x_internal_secret)
    existing = await db.execute(select(InviteEvent).where(InviteEvent.guild_id == payload.guild_id, InviteEvent.invited_discord_id == payload.invited_discord_id))
    if existing.scalar_one_or_none():
        return {"ok": True, "counted": False, "reason": "already-tracked"}
    inviter_result = await db.execute(select(User).where(User.discord_id == payload.inviter_discord_id))
    user = inviter_result.scalar_one_or_none()
    if not user:
        user = User(discord_id=payload.inviter_discord_id, username=f"discord-{payload.inviter_discord_id}")
        db.add(user)
        await db.flush()
    user.invite_balance += 1
    db.add(InviteEvent(**payload.model_dump(), valid=True))
    await db.commit()
    return {"ok": True, "counted": True, "invite_balance": user.invite_balance}


@app.post("/api/v1/internal/invites/leave")
async def invite_leave(guild_id: int, invited_discord_id: int, x_internal_secret: str = Header(alias="X-Internal-Secret"), db: AsyncSession = Depends(get_db)):
    require_internal(x_internal_secret)
    result = await db.execute(select(InviteEvent).where(InviteEvent.guild_id == guild_id, InviteEvent.invited_discord_id == invited_discord_id, InviteEvent.valid.is_(True)))
    event = result.scalar_one_or_none()
    if not event:
        return {"ok": True, "adjusted": False}
    event.valid = False
    user_result = await db.execute(select(User).where(User.discord_id == event.inviter_discord_id))
    inviter = user_result.scalar_one_or_none()
    if inviter:
        inviter.invite_balance = max(0, inviter.invite_balance - 1)
    await db.commit()
    return {"ok": True, "adjusted": True}


@app.get("/api/v1/me")
async def me(user: User = Depends(current_user)):
    return {"id": str(user.id), "discord_id": user.discord_id, "username": user.username, "invite_balance": user.invite_balance}


@app.post("/api/v1/servers")
async def create_server(payload: ServerCreateIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    plan = await db.get(Plan, payload.plan_id)
    if not plan or not plan.enabled:
        raise HTTPException(404, "Plan not found")
    if user.invite_balance < plan.required_invites:
        raise HTTPException(400, f"Need {plan.required_invites} invites")
    user.invite_balance -= plan.required_invites
    server = Server(user_id=user.id, plan_id=plan.id, name=payload.name, kind=plan.kind)
    db.add(server)
    await db.flush()
    job = DeploymentJob(server_id=server.id, payload={"plan_id": str(plan.id), "kind": plan.kind})
    db.add(job)
    await db.commit()
    return {"server_id": str(server.id), "job_id": str(job.id), "status": job.status}


@app.get("/api/v1/servers")
async def my_servers(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Server).where(Server.user_id == user.id).order_by(Server.created_at.desc()))
    return result.scalars().all()


@app.post("/api/v1/servers/{server_id}/action")
async def server_action(server_id: UUID, action: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if action not in {"start", "stop", "restart", "delete"}:
        raise HTTPException(400, "Unsupported action")
    server = await db.get(Server, server_id)
    if not server or server.user_id != user.id:
        raise HTTPException(404, "Server not found")
    if server.status in {"provisioning", "failed"}:
        raise HTTPException(409, f"Server is {server.status}")
    if server.kind == "vps":
        if not server.provider_id:
            raise HTTPException(409, "Provider ID is missing")
        provisioner = DockerProvisioner()
        if action == "restart":
            await asyncio.to_thread(provisioner.restart, server.provider_id)
        elif action == "stop":
            await asyncio.to_thread(provisioner.stop, server.provider_id)
        elif action == "start":
            await asyncio.to_thread(provisioner.client.containers.get(server.provider_id).start)
        elif action == "delete":
            await asyncio.to_thread(provisioner.remove, server.provider_id)
    elif server.kind == "game":
        ptero = PterodactylService()
        provider_id = int(server.provider_id or 0)
        if action == "stop":
            await ptero._request("POST", f"/api/client/servers/{server.provider_id}/power", json={"signal": "stop"})
        elif action == "restart":
            await ptero._request("POST", f"/api/client/servers/{server.provider_id}/power", json={"signal": "restart"})
        elif action == "start":
            await ptero._request("POST", f"/api/client/servers/{server.provider_id}/power", json={"signal": "start"})
        elif action == "delete":
            await ptero.delete_server(provider_id)
    if action == "delete":
        server.status = "deleted"
    else:
        server.status = "running" if action == "start" or action == "restart" else "stopped"
    await db.commit()
    return {"ok": True, "server_id": str(server.id), "status": server.status}


@app.post("/api/v1/ai")
async def ai(payload: AIIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Server).where(Server.user_id == user.id).order_by(Server.created_at.desc()).limit(10))
    servers = result.scalars().all()
    context = {"invite_balance": user.invite_balance, "servers": [{"name": s.name, "status": s.status, "kind": s.kind} for s in servers]}
    return {"response": groq.chat(payload.message, context)}


@app.get("/api/v1/admin/overview")
async def overview(x_discord_id: int = Header(alias="X-Discord-Id"), db: AsyncSession = Depends(get_db)):
    require_admin(x_discord_id)
    users = await db.scalar(select(func.count()).select_from(User))
    servers = await db.scalar(select(func.count()).select_from(Server))
    plans = await db.scalar(select(func.count()).select_from(Plan).where(Plan.enabled.is_(True)))
    jobs = await db.scalar(select(func.count()).select_from(DeploymentJob).where(DeploymentJob.status.in_(["queued", "provisioning"])))
    return {"users": users or 0, "servers": servers or 0, "plans": plans or 0, "active_deployments": jobs or 0}
