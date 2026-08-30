import time
from collections import defaultdict, deque
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from apps.core.config import settings

class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app); self.hits=defaultdict(deque)
    async def dispatch(self, request, call_next):
        host=request.headers.get("host","").split(":",1)[0].lower()
        if host and settings.trusted_host_list and not any(host==h or (h.startswith("*.") and host.endswith(h[1:])) for h in settings.trusted_host_list):
            return JSONResponse({"detail":"Invalid host"},status_code=400)
        if request.url.path.startswith("/api/"):
            ip=request.client.host if request.client else "unknown"; now=time.monotonic(); q=self.hits[ip]
            while q and now-q[0]>60:q.popleft()
            if len(q)>=settings.rate_limit_per_minute:return JSONResponse({"detail":"Rate limit exceeded"},status_code=429,headers={"Retry-After":"60"})
            q.append(now)
        response=await call_next(request)
        response.headers["X-Content-Type-Options"]="nosniff"; response.headers["X-Frame-Options"]="DENY"; response.headers["Referrer-Policy"]="no-referrer"; response.headers["Permissions-Policy"]="camera=(), microphone=(), geolocation=()"
        if settings.environment=="production": response.headers["Strict-Transport-Security"]="max-age=31536000; includeSubDomains"
        if request.url.path.startswith("/api/"): response.headers["Cache-Control"]="no-store"
        return response
