import asyncio
import hmac
import logging
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.core.config import settings
from apps.core.db import Base, engine, get_db
from apps.core.models import AuditLog, DeploymentJob, InviteEvent, Plan, Server, User
from apps.core.security import require_dashboard_token, validate_provision_limits, verify_bot_request
from apps.core.services.docker import DockerProvisioner
from apps.core.services.groq import GroqService
from apps.core.services.pterodactyl import PterodactylService

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
log = logging.getLogger("arvex.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.environment == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="ArveX Hosting API", version="0.2.0", docs_url="/docs" if settings.environment == "development" else None)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type", "X-Discord-Id", "X-Arvex-Timestamp", "X-Arvex-Signature"])
groq = GroqService()


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else response.headers.get("Cache-Control", "public, max-age=60")
    return response


class PlanIn(BaseModel):
    guild_id: int
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=1000)
    kind: str = Field(default="vps", pattern="^(vps|game)$")
    required_invites: int = Field(ge=0, le=100000)
    ram_mb: int = Field(gt=0)
    cpu_percent: int = Field(gt=0)
    disk_mb: int = Field(gt=0)
    image: str | None = Field(default=None, max_length=255)
    egg_id: int | None = Field(default=None, ge=1)
    docker_image: str | None = Field(default=None, max_length=255)
    enabled: bool = True
    sort_order: int = Field(default=0, ge=0, le=100000)
    config: dict = Field(default_factory=dict)

    @field_validator("config")
    @classmethod
    def config_size(cls, value: dict):
        if len(str(value)) > 20000:
            raise ValueError("config is too large")
        return value


class ServerCreateIn(BaseModel):
    guild_id: int
    plan_id: UUID
    name: str = Field(min_length=2, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9 _.-]{1,78}[A-Za-z0-9]$")


class AIIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class InviteEventIn(BaseModel):
    guild_id: int
    inviter_discord_id: int = Field(gt=0)
    invited_discord_id: int = Field(gt=0)
    code: str = Field(min_length=2, max_length=100)


class MovePlanIn(BaseModel):
    direction: str = Field(pattern="^(up|down)$")


async def current_user(discord_id: int = Depends(verify_bot_request), db: AsyncSession = Depends(get_db)) -> User:
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
        raise HTTPException(403, "Admin access required")


def require_internal(secret: str):
    if not settings.internal_api_secret or not hmac.compare_digest(secret, settings.internal_api_secret):
        raise HTTPException(401, "Invalid internal credential")


def validate_plan(payload: PlanIn):
    if payload.kind == "vps":
        validate_provision_limits(payload.ram_mb, payload.cpu_percent, payload.disk_mb)
        image = payload.docker_image or payload.image or settings.vps_image
        if image not in settings.allowed_images:
            raise HTTPException(400, "VPS image is not allow-listed")
    elif payload.egg_id is None:
        raise HTTPException(400, "Game plans require an egg_id")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "arvex-api", "version": "0.2.0"}


@app.get("/api/v1/plans")
async def list_plans(guild_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Plan).where(Plan.guild_id == guild_id, Plan.enabled.is_(True)).order_by(Plan.sort_order, Plan.required_invites))
    return result.scalars().all()


@app.post("/api/v1/admin/plans")
async def create_plan(payload: PlanIn, x_discord_id: int = Depends(verify_bot_request), db: AsyncSession = Depends(get_db)):
    require_admin(x_discord_id)
    validate_plan(payload)
    plan = Plan(**payload.model_dump())
    db.add(plan)
    db.add(AuditLog(actor_discord_id=x_discord_id, guild_id=payload.guild_id, action="plan.create", target=payload.name, data={"name": payload.name, "kind": payload.kind, "required_invites": payload.required_invites}))
    await db.commit()
    await db.refresh(plan)
    return plan


@app.patch("/api/v1/admin/plans/{plan_id}")
async def update_plan(plan_id: UUID, payload: PlanIn, x_discord_id: int = Depends(verify_bot_request), db: AsyncSession = Depends(get_db)):
    require_admin(x_discord_id)
    validate_plan(payload)
    plan = await db.get(Plan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    for key, value in payload.model_dump().items():
        setattr(plan, key, value)
    db.add(AuditLog(actor_discord_id=x_discord_id, guild_id=payload.guild_id, action="plan.update", target=str(plan_id), data={"name": payload.name, "kind": payload.kind, "required_invites": payload.required_invites}))
    await db.commit()
    await db.refresh(plan)
    return plan


@app.post("/api/v1/admin/plans/{plan_id}/move")
async def move_plan(plan_id: UUID, payload: MovePlanIn, x_discord_id: int = Depends(verify_bot_request), db: AsyncSession = Depends(get_db)):
    require_admin(x_discord_id)
    plan = await db.get(Plan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    result = await db.execute(select(Plan).where(Plan.guild_id == plan.guild_id, Plan.enabled.is_(True)).order_by(Plan.sort_order, Plan.created_at))
    plans = list(result.scalars())
    index = plans.index(plan)
    target = index + (-1 if payload.direction == "up" else 1)
    if target < 0 or target >= len(plans):
        return {"ok": True, "moved": False}
    other = plans[target]
    plan.sort_order, other.sort_order = other.sort_order, plan.sort_order
    db.add(AuditLog(actor_discord_id=x_discord_id, guild_id=plan.guild_id, action="plan.move", target=str(plan_id), data={"direction": payload.direction}))
    await db.commit()
    return {"ok": True, "moved": True}


@app.delete("/api/v1/admin/plans/{plan_id}")
async def delete_plan(plan_id: UUID, x_discord_id: int = Depends(verify_bot_request), db: AsyncSession = Depends(get_db)):
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
    inviter_result = await db.execute(select(User).where(User.discord_id == payload.inviter_discord_id).with_for_update())
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
    result = await db.execute(select(InviteEvent).where(InviteEvent.guild_id == guild_id, InviteEvent.invited_discord_id == invited_discord_id, InviteEvent.valid.is_(True)).with_for_update())
    event = result.scalar_one_or_none()
    if not event:
        return {"ok": True, "adjusted": False}
    event.valid = False
    event.left_at = func.now()
    user_result = await db.execute(select(User).where(User.discord_id == event.inviter_discord_id).with_for_update())
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
    if not plan or not plan.enabled or plan.guild_id != payload.guild_id:
        raise HTTPException(404, "Plan not found")
    if user.invite_balance < plan.required_invites:
        raise HTTPException(400, f"Need {plan.required_invites} invites")
    user_locked = await db.execute(select(User).where(User.id == user.id).with_for_update())
    user = user_locked.scalar_one()
    if user.invite_balance < plan.required_invites:
        raise HTTPException(409, "Invite balance changed; please retry")
    user.invite_balance -= plan.required_invites
    server = Server(user_id=user.id, plan_id=plan.id, name=payload.name, kind=plan.kind)
    db.add(server)
    await db.flush()
    job = DeploymentJob(server_id=server.id, payload={"plan_id": str(plan.id), "kind": plan.kind, "guild_id": payload.guild_id})
    db.add(job)
    db.add(AuditLog(actor_discord_id=user.discord_id, guild_id=payload.guild_id, action="server.redeem", target=str(server.id), data={"plan_id": str(plan.id)}))
    await db.commit()
    return {"server_id": str(server.id), "job_id": str(job.id), "status": job.status, "remaining_invites": user.invite_balance}


@app.get("/api/v1/servers")
async def my_servers(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Server).where(Server.user_id == user.id, Server.status != "deleted").order_by(Server.created_at.desc()))
    return result.scalars().all()


@app.post("/api/v1/servers/{server_id}/action")
async def server_action(server_id: UUID, action: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if action not in {"start", "stop", "restart", "delete"}:
        raise HTTPException(400, "Unsupported action")
    server = await db.get(Server, server_id)
    if not server or server.user_id != user.id:
        raise HTTPException(404, "Server not found")
    if server.status in {"provisioning", "failed", "deleted"}:
        raise HTTPException(409, f"Server is {server.status}")
    try:
        if server.kind == "vps":
            if not server.provider_id:
                raise HTTPException(409, "Provider ID is missing")
            provisioner = DockerProvisioner()
            if action == "restart":
                await asyncio.to_thread(provisioner.restart, server.provider_id)
            elif action == "stop":
                await asyncio.to_thread(provisioner.stop, server.provider_id)
            elif action == "start":
                await asyncio.to_thread(provisioner.start, server.provider_id)
            elif action == "delete":
                await asyncio.to_thread(provisioner.remove, server.provider_id)
        elif server.kind == "game":
            ptero = PterodactylService()
            if action in {"start", "stop", "restart"}:
                await ptero.power(server.provider_id or "", action)
            elif action == "delete":
                await ptero.delete_server(int(server.provider_id or 0))
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("Provider action failed")
        raise HTTPException(502, "Provider operation failed") from exc
    server.status = "deleted" if action == "delete" else ("running" if action in {"start", "restart"} else "stopped")
    db.add(AuditLog(actor_discord_id=user.discord_id, action=f"server.{action}", target=str(server.id), data={}))
    await db.commit()
    return {"ok": True, "server_id": str(server.id), "status": server.status}


@app.post("/api/v1/ai")
async def ai(payload: AIIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Server).where(Server.user_id == user.id).order_by(Server.created_at.desc()).limit(10))
    servers = result.scalars().all()
    context = {"invite_balance": user.invite_balance, "servers": [{"id": str(s.id), "name": s.name, "status": s.status, "kind": s.kind} for s in servers]}
    return {"response": groq.chat(payload.message, context)}


async def admin_overview(db: AsyncSession):
    users = await db.scalar(select(func.count()).select_from(User))
    servers = await db.scalar(select(func.count()).select_from(Server))
    plans = await db.scalar(select(func.count()).select_from(Plan).where(Plan.enabled.is_(True)))
    jobs = await db.scalar(select(func.count()).select_from(DeploymentJob).where(DeploymentJob.status.in_(["queued", "provisioning"])))
    nodes = await db.scalar(select(func.count()).select_from(Server).where(Server.status == "ready"))
    return {"users": users or 0, "servers": servers or 0, "plans": plans or 0, "active_deployments": jobs or 0, "ready_servers": nodes or 0}


@app.get("/api/v1/admin/overview")
async def overview(x_discord_id: int = Depends(verify_bot_request), db: AsyncSession = Depends(get_db)):
    require_admin(x_discord_id)
    return await admin_overview(db)


@app.get("/api/v1/dashboard/overview")
async def dashboard_overview(authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)):
    require_dashboard_token(authorization)
    return await admin_overview(db)


@app.get("/api/v1/dashboard/plans")
async def dashboard_plans(authorization: str | None = Header(default=None), guild_id: int | None = None, db: AsyncSession = Depends(get_db)):
    require_dashboard_token(authorization)
    query = select(Plan).order_by(Plan.guild_id, Plan.sort_order, Plan.required_invites)
    if guild_id is not None:
        query = query.where(Plan.guild_id == guild_id)
    result = await db.execute(query)
    return result.scalars().all()


@app.get("/api/v1/dashboard/audit")
async def dashboard_audit(authorization: str | None = Header(default=None), limit: int = 100, db: AsyncSession = Depends(get_db)):
    require_dashboard_token(authorization)
    limit = min(max(limit, 1), 200)
    result = await db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit))
    return result.scalars().all()


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    log.exception("Unhandled API exception", extra={"path": request.url.path})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
