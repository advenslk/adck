import json
import logging
import httpx
import discord
from discord import app_commands
from apps.core.config import settings
from apps.core.security import sign_bot_request
from apps.bot.ui import HostingView, PlanSelectView, ServerManageView

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
log = logging.getLogger("arvex.bot")

class ArveXBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default(); intents.members = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self); self.invite_cache = {}

    async def setup_hook(self):
        if settings.discord_guild_id:
            guild = discord.Object(id=settings.discord_guild_id); self.tree.copy_global_to(guild=guild); await self.tree.sync(guild=guild)
        else: await self.tree.sync()

    async def on_ready(self):
        log.info("Logged in as %s", self.user)
        for guild in self.guilds:
            try:
                invites = await guild.invites(); self.invite_cache[guild.id] = {i.code: i.uses or 0 for i in invites}
            except discord.Forbidden: log.warning("Cannot read invites in guild %s", guild.id)

    async def on_member_join(self, member):
        if settings.discord_guild_id and member.guild.id != settings.discord_guild_id: return
        try:
            invites = await member.guild.invites(); old = self.invite_cache.get(member.guild.id, {})
            used = next((i for i in invites if (i.uses or 0) > old.get(i.code, 0)), None)
            self.invite_cache[member.guild.id] = {i.code: i.uses or 0 for i in invites}
            if used and used.inviter:
                await self.internal_post("/api/v1/internal/invites/join", {"guild_id": member.guild.id, "inviter_discord_id": used.inviter.id, "invited_discord_id": member.id, "code": used.code})
        except Exception: log.exception("Invite attribution failed")

    async def on_member_remove(self, member):
        try: await self.internal_post("/api/v1/internal/invites/leave", None, {"guild_id": member.guild.id, "invited_discord_id": member.id})
        except Exception: log.exception("Invite reconciliation failed")

    async def internal_post(self, path, json_body=None, params=None):
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{settings.public_api_url}{path}", headers={"X-Internal-Secret": settings.internal_api_secret}, json=json_body, params=params); r.raise_for_status(); return r.json()

    async def signed_request(self, method, path, user_id, payload=None):
        body = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else b""
        headers = sign_bot_request(user_id, method, path, body)
        if body: headers["Content-Type"] = "application/json"
        async with httpx.AsyncClient(timeout=30) as client:
            return await client.request(method, f"{settings.public_api_url}{path}", headers=headers, content=body or None)

    async def on_interaction(self, interaction):
        await super().on_interaction(interaction)
        custom_id = interaction.data.get("custom_id") if interaction.data else None
        if custom_id == "arvex:invites": await self.send_plans(interaction)
        elif custom_id == "arvex:servers": await self.send_servers(interaction)
        elif custom_id == "arvex:ai": await interaction.response.send_message("Use `/ai <message>` for AI support.", ephemeral=True)

    async def send_plans(self, interaction):
        if interaction.response.is_done(): return
        r = await self.signed_request("GET", f"/api/v1/plans?guild_id={interaction.guild_id}", interaction.user.id)
        if not r.is_success: return await interaction.response.send_message("Could not load plans.", ephemeral=True)
        plans = r.json()
        if not plans: return await interaction.response.send_message("No plans are currently available.", ephemeral=True)
        await interaction.response.send_message(view=PlanSelectView(interaction.user.id, interaction.guild_id, plans), ephemeral=True)

    async def send_servers(self, interaction):
        r = await self.signed_request("GET", "/api/v1/servers", interaction.user.id)
        if not r.is_success: return await interaction.response.send_message("Could not load your servers.", ephemeral=True)
        servers = r.json()
        if not servers: return await interaction.response.send_message("You don't have any servers yet. Use `/invites` first.", ephemeral=True)
        await interaction.response.send_message(view=ServerManageView(interaction.user.id, servers), ephemeral=True)

bot = ArveXBot()

@bot.tree.command(name="hosting", description="Open the ArveX hosting control center")
async def hosting(interaction): await interaction.response.send_message(view=HostingView(interaction.user.id), ephemeral=True)

@bot.tree.command(name="invites", description="View your invite balance and available plans")
async def invites(interaction): await bot.send_plans(interaction)

@bot.tree.command(name="servers", description="View and manage your hosting services")
async def servers(interaction): await bot.send_servers(interaction)

@bot.tree.command(name="ai", description="Ask the ArveX AI hosting assistant")
@app_commands.describe(message="Your hosting question")
async def ai(interaction, message: str):
    await interaction.response.defer(ephemeral=True)
    r = await bot.signed_request("POST", "/api/v1/ai", interaction.user.id, {"message": message})
    answer = r.json().get("response", "No response") if r.is_success else "AI service is currently unavailable."
    await interaction.followup.send(answer[:4000], ephemeral=True)

@bot.tree.command(name="admin", description="Open the ArveX admin dashboard summary")
async def admin(interaction):
    if interaction.user.id not in settings.admin_ids: return await interaction.response.send_message("You do not have permission.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    r = await bot.signed_request("GET", "/api/v1/admin/overview", interaction.user.id); data = r.json() if r.is_success else {}
    view = discord.ui.LayoutView(timeout=120); view.add_item(discord.ui.Container(discord.ui.TextDisplay(f"# 🛡️ ArveX Admin\n\n**Users:** {data.get('users',0)}\n**Servers:** {data.get('servers',0)}\n**Plans:** {data.get('plans',0)}\n**Active Deployments:** {data.get('active_deployments',0)}"), accent_color=0x7C3AED))
    await interaction.followup.send(view=view, ephemeral=True)

def run():
    if not settings.discord_token: raise RuntimeError("DISCORD_TOKEN is required")
    if not settings.internal_api_secret or len(settings.internal_api_secret) < 32: raise RuntimeError("INTERNAL_API_SECRET must be at least 32 random characters")
    bot.run(settings.discord_token)

if __name__ == "__main__": run()
