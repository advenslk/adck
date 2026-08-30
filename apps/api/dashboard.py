from uuid import UUID
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from apps.core.db import get_db
from apps.core.models import AuditLog, Plan
from apps.core.security import require_dashboard_token, validate_provision_limits
from apps.core.config import settings

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

class DashboardPlanIn(BaseModel):
    guild_id: int
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=1000)
    kind: str = Field(default="vps", pattern="^(vps|game)$")
    required_invites: int = Field(ge=0, le=100000)
    ram_mb: int = Field(gt=0)
    cpu_percent: int = Field(gt=0)
    disk_mb: int = Field(gt=0)
    image: str | None = None
    egg_id: int | None = None
    docker_image: str | None = None
    enabled: bool = True
    sort_order: int = Field(default=0, ge=0, le=100000)
    config: dict = Field(default_factory=dict)

class MoveIn(BaseModel):
    direction: str = Field(pattern="^(up|down)$")

def auth(authorization: str | None): require_dashboard_token(authorization)
def validate_plan(p: DashboardPlanIn):
    if p.kind == "vps":
        validate_provision_limits(p.ram_mb, p.cpu_percent, p.disk_mb)
        if (p.docker_image or p.image or settings.vps_image) not in settings.allowed_images: raise HTTPException(400, "VPS image is not allow-listed")
    elif p.egg_id is None: raise HTTPException(400, "Game plans require an egg_id")

@router.get("/plans")
async def list_plans(authorization: str | None = Header(default=None), guild_id: int | None = None, db: AsyncSession = __import__('fastapi').Depends(get_db)):
    auth(authorization); query=select(Plan).order_by(Plan.guild_id,Plan.sort_order,Plan.required_invites)
    if guild_id is not None: query=query.where(Plan.guild_id==guild_id)
    return (await db.execute(query)).scalars().all()

@router.post("/plans")
async def create_plan(payload: DashboardPlanIn, authorization: str | None = Header(default=None), db: AsyncSession = __import__('fastapi').Depends(get_db)):
    auth(authorization); validate_plan(payload); plan=Plan(**payload.model_dump()); db.add(plan); db.add(AuditLog(actor_discord_id=None,guild_id=payload.guild_id,action="dashboard.plan.create",target=payload.name,data={"name":payload.name})); await db.commit(); await db.refresh(plan); return plan

@router.patch("/plans/{plan_id}")
async def update_plan(plan_id: UUID, payload: DashboardPlanIn, authorization: str | None = Header(default=None), db: AsyncSession = __import__('fastapi').Depends(get_db)):
    auth(authorization); validate_plan(payload); plan=await db.get(Plan,plan_id)
    if not plan: raise HTTPException(404,"Plan not found")
    for key,value in payload.model_dump().items(): setattr(plan,key,value)
    db.add(AuditLog(actor_discord_id=None,guild_id=payload.guild_id,action="dashboard.plan.update",target=str(plan_id),data={"name":payload.name})); await db.commit(); await db.refresh(plan); return plan

@router.post("/plans/{plan_id}/move")
async def move_plan(plan_id: UUID, payload: MoveIn, authorization: str | None = Header(default=None), db: AsyncSession = __import__('fastapi').Depends(get_db)):
    auth(authorization); plan=await db.get(Plan,plan_id)
    if not plan: raise HTTPException(404,"Plan not found")
    result=await db.execute(select(Plan).where(Plan.guild_id==plan.guild_id,Plan.enabled.is_(True)).order_by(Plan.sort_order,Plan.created_at)); plans=list(result.scalars()); i=plans.index(plan); j=i+(-1 if payload.direction=="up" else 1)
    if j<0 or j>=len(plans): return {"ok":True,"moved":False}
    other=plans[j]; plan.sort_order,other.sort_order=other.sort_order,plan.sort_order; db.add(AuditLog(actor_discord_id=None,guild_id=plan.guild_id,action="dashboard.plan.move",target=str(plan_id),data={"direction":payload.direction})); await db.commit(); return {"ok":True,"moved":True}

@router.delete("/plans/{plan_id}")
async def disable_plan(plan_id: UUID, authorization: str | None = Header(default=None), db: AsyncSession = __import__('fastapi').Depends(get_db)):
    auth(authorization); plan=await db.get(Plan,plan_id)
    if not plan: raise HTTPException(404,"Plan not found")
    plan.enabled=False; db.add(AuditLog(actor_discord_id=None,guild_id=plan.guild_id,action="dashboard.plan.disable",target=str(plan_id),data={})); await db.commit(); return {"ok":True}
