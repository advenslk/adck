from __future__ import annotations
import hashlib
import hmac
import time
from fastapi import Header, HTTPException, Request
from apps.core.config import settings
MAX_CLOCK_SKEW = 60
def _signature(discord_id: str, timestamp: str, method: str, path: str, body: bytes) -> str:
    message = "\n".join([timestamp, method.upper(), path, discord_id, hashlib.sha256(body).hexdigest()]).encode()
    return hmac.new(settings.internal_api_secret.encode(), message, hashlib.sha256).hexdigest()
def sign_bot_request(discord_id: int, method: str, path: str, body: bytes = b"") -> dict[str, str]:
    timestamp = str(int(time.time()))
    return {"X-Discord-Id": str(discord_id), "X-Arvex-Timestamp": timestamp, "X-Arvex-Signature": _signature(str(discord_id), timestamp, method, path, body)}
async def verify_bot_request(request: Request, x_discord_id: str | None = Header(default=None, alias="X-Discord-Id"), x_timestamp: str | None = Header(default=None, alias="X-Arvex-Timestamp"), x_signature: str | None = Header(default=None, alias="X-Arvex-Signature")) -> int:
    if not x_discord_id or not x_timestamp or not x_signature: raise HTTPException(401, "Missing request authentication")
    try: timestamp = int(x_timestamp)
    except ValueError: raise HTTPException(401, "Invalid request timestamp")
    if abs(int(time.time()) - timestamp) > MAX_CLOCK_SKEW: raise HTTPException(401, "Expired request")
    expected = _signature(x_discord_id, x_timestamp, request.method, request.url.path, await request.body())
    if not hmac.compare_digest(expected, x_signature): raise HTTPException(401, "Invalid request signature")
    try: return int(x_discord_id)
    except ValueError: raise HTTPException(401, "Invalid Discord id")
def require_dashboard_token(authorization: str | None) -> None:
    if not settings.admin_dashboard_token or not authorization: raise HTTPException(401, "Admin authentication required")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token, settings.admin_dashboard_token): raise HTTPException(403, "Invalid admin credentials")
def validate_provision_limits(ram_mb: int, cpu_percent: int, disk_mb: int) -> None:
    if not 256 <= ram_mb <= settings.max_vps_ram_mb: raise HTTPException(400, "RAM is outside platform limits")
    if not 10 <= cpu_percent <= settings.max_vps_cpu_percent: raise HTTPException(400, "CPU is outside platform limits")
    if not 1024 <= disk_mb <= settings.max_vps_disk_mb: raise HTTPException(400, "Disk is outside platform limits")
