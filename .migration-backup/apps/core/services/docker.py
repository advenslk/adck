from dataclasses import dataclass
from pathlib import Path
import secrets
import docker
from apps.core.config import settings
from apps.core.security import encrypt_secret, validate_provision_limits

@dataclass
class VPSResult:
    container_id: str
    name: str
    status: str
    ssh_host: str
    ssh_port: int
    ssh_password_encrypted: str

class DockerProvisioner:
    """Privileged infrastructure adapter. It is used only by the isolated worker."""
    def __init__(self):
        self.client = docker.from_env(); self.network_name = settings.docker_network

    def ensure_network(self):
        try: self.client.networks.get(self.network_name)
        except docker.errors.NotFound: self.client.networks.create(self.network_name, driver="bridge", internal=False, labels={"com.arvex.managed":"true"})

    def create_vps(self, name: str, ram_mb: int, cpu_percent: int, disk_mb: int, image: str | None = None) -> VPSResult:
        image = image or settings.vps_image
        validate_provision_limits(ram_mb, cpu_percent, disk_mb)
        if image not in settings.allowed_images: raise ValueError("VPS image is not allow-listed")
        self.ensure_network()
        safe_name = "arvex-" + "".join(c for c in name.lower() if c.isalnum() or c == "-")[:48]
        safe_name = safe_name or "arvex-vps"
        if self.client.containers.list(all=True, filters={"name": f"^{safe_name}$"}): safe_name = f"{safe_name[:38]}-{secrets.token_hex(4)}"
        volume_host = Path(settings.vps_rootfs) / safe_name
        volume_host.mkdir(parents=True, exist_ok=True)
        password = secrets.token_urlsafe(18)
        command = ("/bin/bash -lc 'set -e; apt-get update -qq; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server; "
                   "mkdir -p /run/sshd; echo root:%s | chpasswd; "
                   "sed -ri \"s/^#?PermitRootLogin.*/PermitRootLogin yes/\" /etc/ssh/sshd_config; "
                   "sed -ri \"s/^#?PasswordAuthentication.*/PasswordAuthentication yes/\" /etc/ssh/sshd_config; "
                   "exec /usr/sbin/sshd -D -e'" % password)
        container = self.client.containers.run(
            image=image, name=safe_name, detach=True, command=command, mem_limit=f"{ram_mb}m", nano_cpus=max(1, round(cpu_percent / 100)) * 1_000_000_000,
            pids_limit=512, cap_drop=["ALL"], cap_add=["CHOWN","DAC_OVERRIDE","FOWNER","SETGID","SETUID","NET_BIND_SERVICE","SYS_CHROOT"],
            security_opt=["no-new-privileges:true"], privileged=False, read_only=False,
            volumes={str(volume_host): {"bind":"/srv","mode":"rw"}}, labels={"com.arvex.managed":"true","com.arvex.node":settings.docker_node_name},
            network=self.network_name, ports={"22/tcp": None}, restart_policy={"Name":"unless-stopped"},
        )
        container.reload()
        bindings = container.attrs.get("NetworkSettings", {}).get("Ports", {}).get("22/tcp") or []
        if not bindings: raise RuntimeError("Docker did not allocate an SSH port")
        return VPSResult(container.id, safe_name, container.status, settings.vps_public_host, int(bindings[0]["HostPort"]), encrypt_secret(password))

    def status(self, container_id: str) -> dict:
        container=self.client.containers.get(container_id); container.reload(); return {"id":container.id,"name":container.name,"status":container.status}
    def restart(self, container_id: str): self.client.containers.get(container_id).restart()
    def stop(self, container_id: str): self.client.containers.get(container_id).stop(timeout=10)
    def start(self, container_id: str): self.client.containers.get(container_id).start()
    def remove(self, container_id: str): self.client.containers.get(container_id).remove(force=True)
