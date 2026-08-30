from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ArveX Hosting"
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://arvex:change-me@localhost:5432/arvex"
    redis_url: str = "redis://localhost:6379/0"
    discord_token: str = ""
    discord_guild_id: int | None = None
    internal_api_secret: str = ""
    admin_dashboard_token: str = ""
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    pterodactyl_url: str = ""
    pterodactyl_api_key: str = ""
    pterodactyl_client_api_key: str = ""
    docker_node_name: str = "local-01"
    docker_network: str = "arvex-vps"
    vps_image: str = "ubuntu:24.04"
    vps_rootfs: str = "/srv/arvex/vps"
    allowed_vps_images: str = "ubuntu:24.04"
    max_vps_ram_mb: int = 65536
    max_vps_cpu_percent: int = 1200
    max_vps_disk_mb: int = 262144
    public_api_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:3000"
    rate_limit_per_minute: int = 60
    max_deployment_attempts: int = 3
    deployment_concurrency: int = 2
    sshx_command_template: str = ""
    admin_user_ids: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def admin_ids(self) -> set[int]:
        return {int(x.strip()) for x in self.admin_user_ids.split(",") if x.strip().isdigit()}

    @property
    def allowed_images(self) -> set[str]:
        return {x.strip() for x in self.allowed_vps_images.split(",") if x.strip()}

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
