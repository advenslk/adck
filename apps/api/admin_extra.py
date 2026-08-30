from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from apps.core.config import settings
from apps.core.db import get_db
from apps.core.models import AuditLog, DeploymentJob, Node, Server, User
from apps.core.security import require_dashboard_token

router = APIRouter(tags=["dashboard-admin"])
def auth(value: str | None): require_dashboard_token(value)
class NodeIn(BaseModel):
    name: str = Field(min_length=2, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    kind: str = Field(default="docker", pattern="^(docker|pterodactyl)$")
    endpoint: str = Field(default="local", max_length=255)
    enabled: bool = True; maintenance: bool = False
    capacity: dict = Field(default_factory=dict); metadata: dict = Field(default_factory=dict)
class BoolIn(BaseModel): enabled: bool
class MaintenanceIn(BaseModel): maintenance: bool

@router.get("/nodes")
async def list_nodes(authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)):
    auth(authorization); return (await db.execute(select(Node).order_by(Node.name))).scalars().all()

@router.post("/nodes")
async def create_node(payload: NodeIn, authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)):
    auth(authorization)
    if await db.scalar(select(Node).where(Node.name == payload.name)): raise HTTPException(409, "Node name already exists")
    node = Node(name=payload.name, kind=payload.kind, endpoint=payload.endpoint, enabled=payload.enabled, maintenance=payload.maintenance, capacity=payload.capacity, metadata_json=payload.metadata)
    db.add(node); db.add(AuditLog(action="dashboard.node.create", target=payload.name, data={"kind": payload.kind})); await db.commit(); await db.refresh(node); return node

@router.patch("/nodes/{node_id}")
async def update_node(node_id: UUID, payload: NodeIn, authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)):
    auth(authorization); node = await db.get(Node, node_id)
    if not node: raise HTTPException(404, "Node not found")
    if await db.scalar(select(Node).where(Node.name == payload.name, Node.id != node_id)): raise HTTPException(409, "Node name already exists")
    node.name=payload.name; node.kind=payload.kind; node.endpoint=payload.endpoint; node.enabled=payload.enabled; node.maintenance=payload.maintenance; node.capacity=payload.capacity; node.metadata_json=payload.metadata
    db.add(AuditLog(action="dashboard.node.update", target=str(node_id), data={"name": payload.name})); await db.commit(); await db.refresh(node); return node

@router.post("/nodes/{node_id}/maintenance")
async def set_maintenance(node_id: UUID, payload: MaintenanceIn, authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)):
    auth(authorization); node=await db.get(Node,node_id)
    if not node: raise HTTPException(404,"Node not found")
    node.maintenance=payload.maintenance; db.add(AuditLog(action="dashboard.node.maintenance",target=str(node_id),data={"maintenance":payload.maintenance})); await db.commit(); return {"ok":True,"maintenance":node.maintenance}

@router.post("/nodes/{node_id}/enabled")
async def set_enabled(node_id: UUID, payload: BoolIn, authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)):
    auth(authorization); node=await db.get(Node,node_id)
    if not node: raise HTTPException(404,"Node not found")
    node.enabled=payload.enabled; db.add(AuditLog(action="dashboard.node.enabled",target=str(node_id),data={"enabled":payload.enabled})); await db.commit(); return {"ok":True,"enabled":node.enabled}

@router.get("/servers")
async def list_servers(authorization: str | None = Header(default=None), status: str | None = None, db: AsyncSession = Depends(get_db)):
    auth(authorization); q=select(Server).order_by(Server.created_at.desc()).limit(500)
    if status:q=q.where(Server.status==status)
    return (await db.execute(q)).scalars().all()

@router.post("/servers/{server_id}/retry")
async def retry_server(server_id: UUID, authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)):
    auth(authorization); server=await db.get(Server,server_id)
    if not server:raise HTTPException(404,"Server not found")
    job=(await db.execute(select(DeploymentJob).where(DeploymentJob.server_id==server_id).order_by(DeploymentJob.created_at.desc()).limit(1))).scalar_one_or_none()
    if not job:raise HTTPException(404,"Deployment job not found")
    job.status="queued"; job.error=None; server.status="provisioning"; db.add(AuditLog(action="dashboard.server.retry",target=str(server_id))); await db.commit(); return {"ok":True}

@router.get("/users")
async def list_users(authorization: str | None = Header(default=None), limit: int = 100, db: AsyncSession = Depends(get_db)):
    auth(authorization); limit=min(max(limit,1),500); return (await db.execute(select(User).order_by(User.created_at.desc()).limit(limit))).scalars().all()

@router.get("/deployments")
async def deployments(authorization: str | None = Header(default=None), limit: int = 100, db: AsyncSession = Depends(get_db)):
    auth(authorization); limit=min(max(limit,1),500); return (await db.execute(select(DeploymentJob).order_by(DeploymentJob.created_at.desc()).limit(limit))).scalars().all()

@router.get("/security")
async def security_summary(authorization: str | None = Header(default=None)):
    auth(authorization)
    return {"environment":settings.environment,"docs_enabled":settings.environment=="development","trusted_hosts_configured":bool(settings.trusted_host_list),"cors_origins":settings.cors_origin_list,"rate_limit_per_minute":settings.rate_limit_per_minute,"max_deployment_attempts":settings.max_deployment_attempts,"credential_encryption_configured":bool(settings.credential_encryption_key),"internal_secret_configured":bool(settings.internal_api_secret)}
