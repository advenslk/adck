import logging
import httpx
import discord
from discord import app_commands
from apps.core.config import settings
from apps.bot.ui import HostingView, PlanSelectView

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
log = logging.getLogger("arvex.bot")


class ArveXBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.invite_cache: dict[int, dict[str, int]] = {}

    async def setup_hook(self):
        if settings.discord_guild_id:
            guild = discord.Object(id=settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self):
        log.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "?")
        for guild in self.guilds:
            try:
                invites = await guild.invites()
                self.invite_cache[guild.id] = {invite.code: invite.uses or 0 for invite in invites}
            except discord.Forbidden:
                log.warning("Cannot read invites in guild %s; grant Manage Guild.", guild.id)

    async def on_member_join(self, member: discord.Member):
        if settings.discord_guild_id and member.guild.id != settings.discord_guild_id:
            return
        try:
            invites = await member.guild.invites()
            old = self.invite_cache.get(member.guild.id, {})
            used = next((invite for invite in invites if (invite.uses or 0) > old.get(invite.code, 0)), None)
            self.invite_cache[member.guild.id] = {invite.code: invite.uses or 0 for invite in invites}
            if used and used.inviter:
                await self.internal_post("/api/v1/internal/invites/join", {
                    "guild_id": member.guild.id,
                    "inviter_discord_id": used.inviter.id,
                    "invited_discord_id": member.id,
                    "code": used.code,
                })
        except Exception:
            log.exception("Invite attribution failed for %s", member.id)

    async def on_member_remove(self, member: discord.Member):
        try:
            await self.internal_post("/api/v1/internal/invites/leave", None, params={
                "guild_id": member.guild.id,
                "invited_discord_id": member.id,
            })
        except Exception:
            log.exception("Invite reconciliation failed for %s", member.id)

    async def internal_post(self, path: str, json=None, params=None):
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{settings.public_api_url}{path}",
                headers={"X-Internal-Secret": settings.internal_api_secret},
                json=json,
                params=params,
            )
            response.raise_for_status()
            return response.json()

    async def on_interaction(self, interaction: discord.Interaction):
        await super().on_interaction(interaction)
        custom_id = interaction.data.get("custom_id") if interaction.data else None
        if not custom_id or not custom_id.startswith("arvex:"):
            return
        if custom_id == "arvex:invites":
            await self.send_plans(interaction)
        elif custom_id == "arvex:servers":
            await self.send_servers(interaction)
        elif custom_id == "arvex:ai":
            await interaction.response.send_message("Use `/ai <message>` for ArveX AI support.", ephemeral=True)

    async def send_plans(self, interaction: discord.Interaction):
        if interaction.response.is_done():
            return
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{settings.public_api_url}/api/v1/plans", params={"guild_id": interaction.guild_id})
        if not response.is_success:
            await interaction.response.send_message("Could not load plans right now.", ephemeral=True)
            return
        plans = response.json()
        if not plans:
            await interaction.response.send_message("No plans are currently available.", ephemeral=True)
            return
        await interaction.response.send_message(view=PlanSelectView(interaction.user.id, plans), ephemeral=True)

    async def send_servers(self, interaction: discord.Interaction):
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{settings.public_api_url}/api/v1/servers", headers={"X-Discord-Id": str(interaction.user.id)})
        if not response.is_success:
            await interaction.response.send_message("Could not load your servers.", ephemeral=True)
            return
        servers = response.json()
        if not servers:
            text = "# 🖥️ My Servers\nYou don't have any servers yet."
        else:
            lines = ["# 🖥️ My Servers"]
            for server in servers[:20]:
                lines.append(f"**{server['name']}** — `{server['status']}` · `{server['kind']}` · `{server['id']}`")
            text = "\n".join(lines)
        view = discord.ui.LayoutView(timeout=120)
        view.add_item(discord.ui.Container(discord.ui.TextDisplay(text), accent_color=0x7C3AED))
        await interaction.response.send_message(view=view, ephemeral=True)


bot = ArveXBot()


@bot.tree.command(name="hosting", description="Open the ArveX hosting control center")
async def hosting(interaction: discord.Interaction):
    await interaction.response.send_message(view=HostingView(interaction.user.id), ephemeral=True)


@bot.tree.command(name="invites", description="View your invite balance and available plans")
async def invites(interaction: discord.Interaction):
    await bot.send_plans(interaction)


@bot.tree.command(name="servers", description="View and manage your hosting services")
async def servers(interaction: discord.Interaction):
    await bot.send_servers(interaction)


@bot.tree.command(name="ai", description="Ask the ArveX AI hosting assistant")
@app_commands.describe(message="Your hosting question")
async def ai(interaction: discord.Interaction, message: str):
    await interaction.response.defer(ephemeral=True)
    async with httpx.AsyncClient(timeout=40) as client:
        response = await client.post(
            f"{settings.public_api_url}/api/v1/ai",
            headers={"X-Discord-Id": str(interaction.user.id)},
            json={"message": message},
        )
    answer = response.json().get("response", "No response") if response.is_success else "AI service is currently unavailable."
    await interaction.followup.send(answer[:4000], ephemeral=True)


@bot.tree.command(name="admin", description="Open the ArveX admin dashboard summary")
async def admin(interaction: discord.Interaction):
    if interaction.user.id not in settings.admin_ids:
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(f"{settings.public_api_url}/api/v1/admin/overview", headers={"X-Discord-Id": str(interaction.user.id)})
    data = response.json() if response.is_success else {}
    view = discord.ui.LayoutView(timeout=120)
    view.add_item(discord.ui.Container(
        discord.ui.TextDisplay(
            f"# 🛡️ ArveX Admin\n\n**Users:** {data.get('users', 0)}\n**Servers:** {data.get('servers', 0)}\n**Plans:** {data.get('plans', 0)}\n**Active Deployments:** {data.get('active_deployments', 0)}"
        ), accent_color=0x7C3AED
    ))
    await interaction.response.send_message(view=view, ephemeral=True)


def run():
    if not settings.discord_token:
        raise RuntimeError("DISCORD_TOKEN is required")
    bot.run(settings.discord_token)


if __name__ == "__main__":
    run()
