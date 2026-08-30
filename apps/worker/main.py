import asyncio
import logging
import httpx
from sqlalchemy import select
from apps.core.config import settings
from apps.core.db import SessionLocal
from apps.core.models import DeploymentJob, Plan, Server, User
from apps.core.services.docker import DockerProvisioner
from apps.core.services.pterodactyl import PterodactylService

log = logging.getLogger("arvex.worker")
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))


def discord_headers():
    return {"Authorization": f"Bot {settings.discord_token}", "Content-Type": "application/json"}


async def send_dm(discord_id: int, content: str):
    if not settings.discord_token:
        return
    async with httpx.AsyncClient(base_url="https://discord.com/api/v10", headers=discord_headers(), timeout=20) as client:
        channel = await client.post("/users/@me/channels", json={"recipient_id": str(discord_id)})
        channel.raise_for_status()
        channel_id = channel.json()["id"]
        message = await client.post(f"/channels/{channel_id}/messages", json={"content": content[:2000]})
        message.raise_for_status()


async def process_job(job_id):
    async with SessionLocal() as db:
        job = await db.get(DeploymentJob, job_id)
        if not job or job.status not in {"queued", "failed"}:
            return
        server = await db.get(Server, job.server_id)
        if not server:
            job.status = "failed"
            job.error = "Server record missing"
            await db.commit()
            return
        plan = await db.get(Plan, server.plan_id)
        user = await db.get(User, server.user_id)
        if not plan or not user:
            job.status = "failed"
            job.error = "Plan or user missing"
            await db.commit()
            return
        job.status = "provisioning"
        job.attempts += 1
        await db.commit()
        try:
            if plan.kind == "vps":
                provisioner = DockerProvisioner()
                result = await asyncio.to_thread(
                    provisioner.create_vps,
                    server.name,
                    plan.ram_mb,
                    plan.cpu_percent,
                    plan.disk_mb,
                    plan.docker_image or plan.image,
                )
                server.provider_id = result.container_id
                server.access = {"container": result.container_id, "node": settings.docker_node_name, "sshx": plan.config.get("sshx_url")}
            elif plan.kind == "game":
                ptero = PterodactylService()
                config = plan.config
                payload = {
                    "name": server.name,
                    "user": config["pterodactyl_user_id"],
                    "nest": config["nest_id"],
                    "egg": plan.egg_id,
                    "docker_image": plan.docker_image or config.get("docker_image", "ghcr.io/pterodactyl/yolks:java_21"),
                    "startup": config.get("startup", "java -Xms128M -Xmx{{SERVER_MEMORY}}M -jar {{SERVER_JARFILE}}"),
                    "environment": config.get("environment", {}),
                    "limits": {"memory": plan.ram_mb, "swap": 0, "disk": plan.disk_mb, "io": 500, "cpu": plan.cpu_percent},
                    "feature_limits": config.get("feature_limits", {"databases": 1, "allocations": 1, "backups": 1}),
                    "deploy": config.get("deploy", {"locations": [config.get("location_id")], "port_range": [], "dedicated_ip": False}),
                    "start_on_completion": True,
                }
                created = await ptero.create_server(payload)
                server.provider_id = str(created.get("attributes", {}).get("id", created.get("id", "")))
                server.access = {"panel": settings.pterodactyl_url, "server_id": server.provider_id}
            else:
                raise RuntimeError(f"Unsupported plan kind: {plan.kind}")
            server.status = "ready"
            job.status = "completed"
            job.error = None
            await db.commit()
            await send_dm(user.discord_id, f"🟢 **ArveX Server Ready**\n\n**{server.name}**\nPlan: `{plan.name}`\nType: `{plan.kind}`\nStatus: `ready`\n\nManage it with `/servers`.\n{('SSHX: ' + server.access.get('sshx')) if server.access.get('sshx') else 'SSH/SSHX access will appear when your VPS image is configured with an SSH gateway.'}")
        except Exception as exc:
            log.exception("Deployment failed: %s", job.id)
            job.status = "failed"
            job.error = str(exc)[:4000]
            server.status = "failed"
            await db.commit()
            await send_dm(user.discord_id, f"❌ **Deployment failed** for `{server.name}`.\n\nThe system recorded the failure and staff can retry it.\nError: `{str(exc)[:500]}`")


async def run_worker():
    while True:
        try:
            async with SessionLocal() as db:
                result = await db.execute(select(DeploymentJob.id).where(DeploymentJob.status == "queued").order_by(DeploymentJob.created_at).limit(5))
                ids = [row[0] for row in result.all()]
            for job_id in ids:
                await process_job(job_id)
        except Exception:
            log.exception("Worker loop error")
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(run_worker())
