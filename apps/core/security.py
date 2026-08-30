from __future__ import annotations
import hashlib
import hmac
import secrets
import time
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Header, HTTPException, Request
from apps.core.config import settings
MAX_CLOCK_SKEW = 60
_NONCES: dict[str, int] = {}

def _signature(discord_id: str, timestamp: str, nonce: str, method: str, path: str, body: bytes) -> str:
    message = "\n".join([timestamp, nonce, method.upper(), path, discord_id, hashlib.sha256(body).hexdigest()]).encode()
    return hmac.new(settings.internal_api_secret.encode(), message, hashlib.sha256).hexdigest()

def sign_bot_request(discord_id: int, method: str, path: str, body: bytes = b"") -> dict[str, str]:
    timestamp = str(int(time.time())); nonce = secrets.token_urlsafe(18)
    return {"X-Discord-Id": str(discord_id), "X-Arvex-Timestamp": timestamp, "X-Arvex-Nonce": nonce, "X-Arvex-Signature": _signature(str(discord_id), timestamp, nonce, method, path, body)}

async def verify_bot_request(request: Request, x_discord_id: str | None = Header(default=None, alias="X-Discord-Id"), x_timestamp: str | None = Header(default=None, alias="X-Arvex-Timestamp"), x_nonce: str | None = Header(default=None, alias="X-Arvex-Nonce"), x_signature: str | None = Header(default=None, alias="X-Arvex-Signature")) -> int:
    if not x_discord_id or not x_timestamp or not x_nonce or not x_signature: raise HTTPException(401, "Missing request authentication")
    try: timestamp = int(x_timestamp)
    except ValueError: raise HTTPException(401, "Invalid request timestamp")
    now = int(time.time())
    if abs(now - timestamp) > MAX_CLOCK_SKEW: raise HTTPException(401, "Expired request")
    if len(x_nonce) > 128 or not x_nonce.replace("-", "").replace("_", "").isalnum(): raise HTTPException(401, "Invalid request nonce")
    # Process-local replay protection. Deployments with multiple API replicas should use a shared nonce store.
    for key, expiry in list(_NONCES.items()):
        if expiry < now: _NONCES.pop(key, None)
    nonce_key = f"{x_discord_id}:{x_nonce}"
    if nonce_key in _NONCES: raise HTTPException(401, "Request replay detected")
    canonical_path = request.url.path + (("?" + request.url.query) if request.url.query else "")
    expected = _signature(x_discord_id, x_timestamp, x_nonce, request.method, canonical_path, await request.body())
    if not hmac.compare_digest(expected, x_signature): raise HTTPException(401, "Invalid request signature")
    _NONCES[nonce_key] = now + MAX_CLOCK_SKEW
    try: return int(x_discord_id)
    except ValueError: raise HTTPException(401, "Invalid Discord id")

def require_dashboard_token(authorization: str | None) -> None:
    if not settings.admin_dashboard_token or not authorization: raise HTTPException(401, "Admin authentication required")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token, settings.admin_dashboard_token): raise HTTPException(403, "Invalid admin credentials")

def credential_cipher() -> Fernet:
    if not settings.credential_encryption_key: raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY is required")
    return Fernet(settings.credential_encryption_key.encode())

def encrypt_secret(value: str) -> str: return credential_cipher().encrypt(value.encode()).decode()
def decrypt_secret(value: str) -> str:
    try: return credential_cipher().decrypt(value.encode()).decode()
    except InvalidToken as exc: raise RuntimeError("Stored credential cannot be decrypted") from exc

def validate_provision_limits(ram_mb: int, cpu_percent: int, disk_mb: int) -> None:
    if not 256 <= ram_mb <= settings.max_vps_ram_mb: raise HTTPException(400, "RAM is outside platform limits")
    if not 10 <= cpu_percent <= settings.max_vps_cpu_percent: raise HTTPException(400, "CPU is outside platform limits")
    if not 1024 <= disk_mb <= settings.max_vps_disk_mb: raise HTTPException(400, "Disk is outside platform limits")
