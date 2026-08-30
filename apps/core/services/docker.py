from dataclasses import dataclass
from pathlib import Path
import docker
from docker.errors import DockerException
from apps.core.config import settings


@dataclass
class VPSResult:
    container_id: str
    name: str
    status: str


class DockerProvisioner:
    """Safe application-level Docker adapter. Customer containers never receive the Docker socket."""

    def __init__(self):
        self.client = docker.from_env()
        self.network_name = settings.docker_network

    def ensure_network(self):
        try:
            self.client.networks.get(self.network_name)
        except docker.errors.NotFound:
            self.client.networks.create(self.network_name, driver="bridge", internal=False)

    def create_vps(self, name: str, ram_mb: int, cpu_percent: int, disk_mb: int, image: str | None = None) -> VPSResult:
        self.ensure_network()
        image = image or settings.vps_image
        memory = f"{ram_mb}m"
        cpus = max(1, round(cpu_percent / 100))
        safe_name = "arvex-" + "".join(c for c in name.lower() if c.isalnum() or c == "-")[:48]
        volume_host = Path(settings.vps_rootfs) / safe_name
        volume_host.mkdir(parents=True, exist_ok=True)
        container = self.client.containers.run(
            image=image,
            name=safe_name,
            detach=True,
            command="/bin/bash -lc 'while true; do sleep 3600; done'",
            mem_limit=memory,
            nano_cpus=cpus * 1_000_000_000,
            pids_limit=512,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            privileged=False,
            read_only=False,
            volumes={str(volume_host): {"bind": "/srv", "mode": "rw"}},
            labels={"com.arvex.managed": "true", "com.arvex.node": settings.docker_node_name},
            network=self.network_name,
            restart_policy={"Name": "unless-stopped"},
        )
        return VPSResult(container.id, safe_name, container.status)

    def status(self, container_id: str) -> dict:
        container = self.client.containers.get(container_id)
        container.reload()
        return {"id": container.id, "name": container.name, "status": container.status}

    def restart(self, container_id: str):
        self.client.containers.get(container_id).restart()

    def stop(self, container_id: str):
        self.client.containers.get(container_id).stop(timeout=10)

    def remove(self, container_id: str):
        self.client.containers.get(container_id).remove(force=True)
