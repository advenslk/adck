import httpx
import discord
from discord import ui
from apps.core.config import settings


class HostingView(ui.LayoutView):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.container = ui.Container(
            ui.TextDisplay("# 🚀 ArveX Hosting\n**Discord-first hosting control center**"),
            ui.Separator(),
            ui.TextDisplay("Choose an action below to manage your hosting services."),
            accent_color=0x7C3AED,
        )
        row = ui.ActionRow()
        row.add_item(ui.Button(label="🎟️ Invite Rewards", style=discord.ButtonStyle.primary, custom_id="arvex:invites"))
        row.add_item(ui.Button(label="🖥️ My Servers", style=discord.ButtonStyle.secondary, custom_id="arvex:servers"))
        row.add_item(ui.Button(label="🤖 AI Support", style=discord.ButtonStyle.secondary, custom_id="arvex:ai"))
        self.container.add_item(row)
        self.add_item(self.container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This control panel belongs to another user.", ephemeral=True)
            return False
        return True


class PlanSelectView(ui.LayoutView):
    def __init__(self, user_id: int, plans: list[dict]):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.container = ui.Container(
            ui.TextDisplay("# 🎟️ Upgrade\nSelect a plan to redeem with your invite balance."),
            accent_color=0x7C3AED,
        )
        row = ui.ActionRow()
        select = ui.Select(placeholder="Select a plan", min_values=1, max_values=1)
        for plan in plans[:25]:
            select.add_option(
                label=f"{plan['name']} • {plan['required_invites']} invites",
                description=f"{plan['ram_mb']//1024}GB RAM • {max(1, plan['cpu_percent']//100)} vCPU • {plan['disk_mb']//1024}GB",
                value=str(plan['id']),
            )
        async def selected(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("This menu belongs to another user.", ephemeral=True)
                return
            plan_id = select.values[0]
            await interaction.response.defer(ephemeral=True)
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    f"{settings.public_api_url}/api/v1/servers",
                    headers={"X-Discord-Id": str(interaction.user.id)},
                    json={"plan_id": plan_id, "name": f"{interaction.user.name}-server"},
                )
            if response.is_success:
                data = response.json()
                await interaction.followup.send(f"⏳ **Provisioning started**\nServer ID: `{data['server_id']}`\nJob: `{data['job_id']}`\n\nYou will receive a DM when it is ready.", ephemeral=True)
            else:
                try:
                    detail = response.json().get("detail", "Request failed")
                except Exception:
                    detail = response.text[:500]
                await interaction.followup.send(f"❌ {detail}", ephemeral=True)
        select.callback = selected
        row.add_item(select)
        self.container.add_item(row)
        self.add_item(self.container)


class ServerManageView(ui.LayoutView):
    def __init__(self, user_id: int, servers: list[dict]):
        super().__init__(timeout=240)
        self.user_id = user_id
        self.server_map = {str(s["id"]): s for s in servers}
        self.container = ui.Container(
            ui.TextDisplay("# 🖥️ My Servers\nSelect a server, then choose a lifecycle action."),
            accent_color=0x7C3AED,
        )
        select_row = ui.ActionRow()
        select = ui.Select(placeholder="Select a server", min_values=1, max_values=1)
        for server in servers[:25]:
            select.add_option(label=server["name"][:100], description=f"{server['status']} • {server['kind']}", value=str(server["id"]))
        select_row.add_item(select)
        self.container.add_item(select_row)
        action_row = ui.ActionRow()
        for label, action, style in [("▶ Start", "start", discord.ButtonStyle.success), ("⏹ Stop", "stop", discord.ButtonStyle.secondary), ("🔄 Restart", "restart", discord.ButtonStyle.primary), ("🗑 Delete", "delete", discord.ButtonStyle.danger)]:
            button = ui.Button(label=label, style=style, custom_id=f"server-action:{action}")
            async def callback(interaction: discord.Interaction, button=button, action=action):
                if interaction.user.id != self.user_id:
                    await interaction.response.send_message("This panel belongs to another user.", ephemeral=True)
                    return
                if not select.values:
                    await interaction.response.send_message("Select a server first.", ephemeral=True)
                    return
                server_id = select.values[0]
                if action == "delete":
                    await interaction.response.send_message("⚠️ Delete is permanent. Run the action again from your panel after confirming your intent.", ephemeral=True)
                    return
                await interaction.response.defer(ephemeral=True)
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(f"{settings.public_api_url}/api/v1/servers/{server_id}/action", params={"action": action}, headers={"X-Discord-Id": str(interaction.user.id)})
                if response.is_success:
                    await interaction.followup.send(f"✅ `{action}` request completed.", ephemeral=True)
                else:
                    detail = response.json().get("detail", "Action failed") if response.content else "Action failed"
                    await interaction.followup.send(f"❌ {detail}", ephemeral=True)
            button.callback = callback
            action_row.add_item(button)
        self.container.add_item(action_row)
        self.add_item(self.container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This panel belongs to another user.", ephemeral=True)
            return False
        return True
