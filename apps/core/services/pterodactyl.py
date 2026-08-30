from typing import Any
import httpx
from apps.core.config import settings


class PterodactylService:
    def __init__(self):
        self.base = settings.pterodactyl_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {settings.pterodactyl_api_key}",
            "Accept": "Application/vnd.pterodactyl.v1+json",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        if not self.base or not settings.pterodactyl_api_key:
            raise RuntimeError("Pterodactyl is not configured")
        async with httpx.AsyncClient(base_url=self.base, headers=self.headers, timeout=30) as client:
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else {}

    async def list_nodes(self):
        return await self._request("GET", "/api/application/nodes", params={"per_page": 100})

    async def create_user(self, email: str, username: str, first_name: str = "ArveX", last_name: str = "User"):
        return await self._request("POST", "/api/application/users", json={
            "email": email, "username": username[:32], "first_name": first_name, "last_name": last_name,
        })

    async def create_server(self, payload: dict[str, Any]):
        return await self._request("POST", "/api/application/servers", json=payload)

    async def get_server(self, server_id: int):
        return await self._request("GET", f"/api/application/servers/{server_id}")

    async def suspend_server(self, server_id: int):
        return await self._request("POST", f"/api/application/servers/{server_id}/suspend")

    async def unsuspend_server(self, server_id: int):
        return await self._request("POST", f"/api/application/servers/{server_id}/unsuspend")

    async def delete_server(self, server_id: int, force: bool = False):
        return await self._request("DELETE", f"/api/application/servers/{server_id}", params={"force": str(force).lower()})
