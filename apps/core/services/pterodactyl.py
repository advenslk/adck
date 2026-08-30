from typing import Any
import httpx
from apps.core.config import settings

class PterodactylService:
    def __init__(self):
        self.base=settings.pterodactyl_url.rstrip("/");self.application_headers={"Authorization":f"Bearer {settings.pterodactyl_api_key}","Accept":"Application/vnd.pterodactyl.v1+json","Content-Type":"application/json"};self.client_headers={"Authorization":f"Bearer {settings.pterodactyl_client_api_key}","Accept":"Application/vnd.pterodactyl.v1+json","Content-Type":"application/json"}
    async def _request(self,method:str,path:str,**kwargs)->dict[str,Any]:
        if not self.base or not settings.pterodactyl_api_key:raise RuntimeError("Pterodactyl application API is not configured")
        async with httpx.AsyncClient(base_url=self.base,headers=self.application_headers,timeout=30) as c:
            r=await c.request(method,path,**kwargs);r.raise_for_status();return r.json() if r.content else {}
    async def _client_request(self,method:str,path:str,**kwargs)->dict[str,Any]:
        if not self.base or not settings.pterodactyl_client_api_key:raise RuntimeError("Pterodactyl client API is not configured")
        async with httpx.AsyncClient(base_url=self.base,headers=self.client_headers,timeout=30) as c:
            r=await c.request(method,path,**kwargs);r.raise_for_status();return r.json() if r.content else {}
    async def list_nodes(self):return await self._request("GET","/api/application/nodes",params={"per_page":100})
    async def create_user(self,email:str,username:str,first_name:str="ArveX",last_name:str="User"):
        return await self._request("POST","/api/application/users",json={"email":email,"username":username[:32],"first_name":first_name,"last_name":last_name})
    async def create_server(self,payload:dict[str,Any]):return await self._request("POST","/api/application/servers",json=payload)
    async def get_server(self,server_id:int):return await self._request("GET",f"/api/application/servers/{server_id}")
    async def power(self,server_identifier:str,signal:str):
        if signal not in {"start","stop","restart"}:raise ValueError("Invalid power signal")
        identifier=str(server_identifier)
        if identifier.isdigit():
            data=await self.get_server(int(identifier));identifier=str(data.get("attributes",{}).get("identifier",identifier))
        return await self._client_request("POST",f"/api/client/servers/{identifier}/power",json={"signal":signal})
    async def suspend_server(self,server_id:int):return await self._request("POST",f"/api/application/servers/{server_id}/suspend")
    async def unsuspend_server(self,server_id:int):return await self._request("POST",f"/api/application/servers/{server_id}/unsuspend")
    async def delete_server(self,server_id:int,force:bool=False):return await self._request("DELETE",f"/api/application/servers/{server_id}",params={"force":str(force).lower()})
