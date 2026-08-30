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
    internal_api_secret: str = "change-this-secret"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    pterodactyl_url: str = ""
    pterodactyl_api_key: str = ""
    pterodactyl_client_api_key: str = ""
    docker_node_name: str = "local-01"
    docker_network: str = "arvex-vps"
    vps_image: str = "ubuntu:24.04"
    vps_rootfs: str = "/srv/arvex/vps"
    admin_user_ids: str = ""
    public_api_url: str = "http://localhost:8000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def admin_ids(self) -> set[int]:
        return {int(x.strip()) for x in self.admin_user_ids.split(",") if x.strip().isdigit()}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
