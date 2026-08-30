from datetime import datetime
from uuid import uuid4
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from apps.core.db import Base


def uid():
    return uuid4()


class Guild(Base):
    __tablename__ = "guilds"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    discord_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str] = mapped_column(String(120), default="")
    invite_balance: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class InviteEvent(Base):
    __tablename__ = "invite_events"
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    inviter_discord_id: Mapped[int] = mapped_column(BigInteger, index=True)
    invited_discord_id: Mapped[int] = mapped_column(BigInteger, index=True)
    code: Mapped[str] = mapped_column(String(100))
    valid: Mapped[bool] = mapped_column(Boolean, default=True)
    left_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("guild_id", "invited_discord_id"),)


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    guild_id: Mapped[int] = mapped_column(ForeignKey("guilds.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(20), default="vps")
    required_invites: Mapped[int] = mapped_column(Integer, default=0)
    ram_mb: Mapped[int] = mapped_column(Integer)
    cpu_percent: Mapped[int] = mapped_column(Integer)
    disk_mb: Mapped[int] = mapped_column(Integer)
    image: Mapped[str | None] = mapped_column(String(255), nullable=True)
    egg_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    docker_image: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Node(Base):
    __tablename__ = "nodes"
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    kind: Mapped[str] = mapped_column(String(20), default="docker")
    endpoint: Mapped[str] = mapped_column(String(255), default="local")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    maintenance: Mapped[bool] = mapped_column(Boolean, default=False)
    capacity: Mapped[dict] = mapped_column(JSONB, default=dict)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Server(Base):
    __tablename__ = "servers"
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[UUID] = mapped_column(ForeignKey("plans.id"), index=True)
    node_id: Mapped[UUID | None] = mapped_column(ForeignKey("nodes.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20))
    provider_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="provisioning")
    access: Mapped[dict] = mapped_column(JSONB, default=dict)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DeploymentJob(Base):
    __tablename__ = "deployment_jobs"
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    server_id: Mapped[UUID] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    actor_discord_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    guild_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    action: Mapped[str] = mapped_column(String(120))
    target: Mapped[str] = mapped_column(String(120), default="")
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
