import asyncio
import os
from sqlalchemy import select
from apps.core.db import Base, SessionLocal, engine
from apps.core.models import Guild, Plan

GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0"))

PLANS = [
    ("ARX VPS 4", 2, 4096, 200, 10240),
    ("ARX VPS 8", 6, 8192, 300, 20480),
    ("ARX VPS 10", 10, 10240, 300, 25600),
    ("ARX VPS 16", 14, 16384, 400, 40960),
    ("ARX VPS 24", 18, 24576, 600, 61440),
    ("ARX VPS 32", 24, 32768, 800, 81920),
    ("ARX VPS 64", 36, 65536, 1200, 256000),
]


async def main():
    if not GUILD_ID:
        raise SystemExit("Set DISCORD_GUILD_ID first")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as db:
        guild = await db.get(Guild, GUILD_ID)
        if not guild:
            db.add(Guild(id=GUILD_ID, name="ArveX Discord"))
        for index, (name, invites, ram, cpu, disk) in enumerate(PLANS):
            exists = await db.execute(select(Plan).where(Plan.guild_id == GUILD_ID, Plan.name == name))
            if exists.scalar_one_or_none():
                continue
            db.add(Plan(guild_id=GUILD_ID, name=name, description=f"{ram//1024}GB RAM • {cpu//100} vCPU • {disk//1024}GB SSD", kind="vps", required_invites=invites, ram_mb=ram, cpu_percent=cpu, disk_mb=disk, sort_order=index))
        await db.commit()
    print("Seed complete")


if __name__ == "__main__":
    asyncio.run(main())
