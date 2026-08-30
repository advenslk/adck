import asyncio
import logging
import httpx
from datetime import datetime, timedelta
from sqlalchemy import select
from apps.core.config import settings
from apps.core.db import SessionLocal
from apps.core.models import DeploymentJob, Plan, Server, User
from apps.core.security import decrypt_secret
from apps.core.services.docker import DockerProvisioner
from apps.core.services.pterodactyl import PterodactylService

log=logging.getLogger("arvex.worker"); logging.basicConfig(level=getattr(logging,settings.log_level.upper(),logging.INFO))
def discord_headers(): return {"Authorization":f"Bot {settings.discord_token}","Content-Type":"application/json"}
async def send_dm(discord_id:int,content:str):
    if not settings.discord_token:return
    async with httpx.AsyncClient(base_url="https://discord.com/api/v10",headers=discord_headers(),timeout=20) as c:
        ch=await c.post("/users/@me/channels",json={"recipient_id":str(discord_id)}); ch.raise_for_status(); m=await c.post(f"/channels/{ch.json()['id']}/messages",json={"content":content[:2000]}); m.raise_for_status()

async def claim_jobs(limit:int):
    async with SessionLocal() as db:
        stale=datetime.utcnow()-timedelta(minutes=10)
        await db.execute(__import__('sqlalchemy').update(DeploymentJob).where(DeploymentJob.status=="provisioning",DeploymentJob.updated_at<stale).values(status="queued"))
        rows=(await db.execute(select(DeploymentJob).where(DeploymentJob.status=="queued").order_by(DeploymentJob.created_at).with_for_update(skip_locked=True).limit(limit))).scalars().all()
        ids=[]
        for job in rows:
            if job.attempts>=settings.max_deployment_attempts: job.status="failed"; job.error="Maximum deployment attempts reached"; continue
            job.status="provisioning"; job.attempts+=1; ids.append(job.id)
        await db.commit(); return ids

async def process_job(job_id):
    async with SessionLocal() as db:
        job=await db.get(DeploymentJob,job_id); server=await db.get(Server,job.server_id) if job else None; plan=await db.get(Plan,server.plan_id) if server else None; user=await db.get(User,server.user_id) if server else None
        if not job or not server or not plan or not user:return
        try:
            if plan.kind=="vps":
                r=await asyncio.to_thread(DockerProvisioner().create_vps,server.name,plan.ram_mb,plan.cpu_percent,plan.disk_mb,plan.docker_image or plan.image)
                server.provider_id=r.container_id; server.access={"ssh":{"host":r.ssh_host,"port":r.ssh_port,"password_encrypted":r.ssh_password_encrypted}}; ready=f"🔐 SSH: `ssh root@{r.ssh_host} -p {r.ssh_port}`\n🔑 Password: `{decrypt_secret(r.ssh_password_encrypted)}`"
            elif plan.kind=="game":
                c=plan.config; p=PterodactylService(); payload={"name":server.name,"user":c["pterodactyl_user_id"],"nest":c["nest_id"],"egg":plan.egg_id,"docker_image":plan.docker_image or c.get("docker_image","ghcr.io/pterodactyl/yolks:java_21"),"startup":c.get("startup","java -Xms128M -Xmx{{SERVER_MEMORY}}M -jar {{SERVER_JARFILE}}"),"environment":c.get("environment",{}),"limits":{"memory":plan.ram_mb,"swap":0,"disk":plan.disk_mb,"io":500,"cpu":plan.cpu_percent},"feature_limits":c.get("feature_limits",{"databases":1,"allocations":1,"backups":1}),"deploy":c.get("deploy",{"locations":[c.get("location_id")],"port_range":[],"dedicated_ip":False}),"start_on_completion":True}; created=await p.create_server(payload); server.provider_id=str(created.get("attributes",{}).get("id",created.get("id",""))); server.access={"panel":settings.pterodactyl_url,"server_id":server.provider_id}; ready=f"🎮 Panel: {settings.pterodactyl_url}\n🆔 Server ID: `{server.provider_id}`"
            else: raise RuntimeError(f"Unsupported plan kind: {plan.kind}")
            server.status="ready"; job.status="completed"; job.error=None; await db.commit(); await send_dm(user.discord_id,f"🟢 **ArveX Server Ready**\n\n**{server.name}**\nPlan: `{plan.name}`\nType: `{plan.kind}`\n\n{ready}\n\nManage it with `/servers`. Keep credentials private.")
        except Exception as exc:
            log.exception("Deployment failed: %s",job.id); server.status="failed"; job.status="queued" if job.attempts<settings.max_deployment_attempts else "failed"; job.error=str(exc)[:4000]; await db.commit()
            if job.status=="failed": await send_dm(user.discord_id,f"❌ **Deployment failed** for `{server.name}` after {job.attempts} attempts. Staff intervention is required.")

async def run_worker():
    concurrency=max(1,settings.deployment_concurrency)
    while True:
        try:
            ids=await claim_jobs(concurrency)
            await asyncio.gather(*(process_job(i) for i in ids))
        except Exception:log.exception("Worker loop error")
        await asyncio.sleep(2)
if __name__=="__main__":asyncio.run(run_worker())
