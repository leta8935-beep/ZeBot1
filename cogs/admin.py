import discord
from discord.ext import commands
from discord import app_commands
from utils.checks import is_staff

def fmt(n: int) -> str: return f"{n:,}".replace(",", " ")

class EditOrgSelectView(discord.ui.View):
    def __init__(self, bot, org_id: int):
        super().__init__(timeout=60)
        self.bot = bot
        self.org_id = org_id

    @discord.ui.select(placeholder="Что изменить?", options=[
        discord.SelectOption(label="Название", value="name"),
        discord.SelectOption(label="Логотип", value="logo_url"),
        discord.SelectOption(label="Сфера", value="sphere"),
        discord.SelectOption(label="Уровень", value="level"),
    ])
    async def select_field(self, interaction: discord.Interaction, select: discord.ui.Select):
        field = select.values[0]
        await interaction.response.send_modal(AdminEditOrgModal(self.bot, self.org_id, field))

class AdminEditOrgModal(discord.ui.Modal, title="Редактирование организации"):
    value = discord.ui.TextInput(label="Новое значение")

    def __init__(self, bot, org_id: int, field: str):
        super().__init__()
        self.bot = bot
        self.org_id = org_id
        self.field = field
        self.value.label = f"Новое значение для '{field}'"

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.value.value) if self.field == "level" else self.value.value
            async with self.bot.db.pool.acquire() as c:
                await c.execute(f"UPDATE organizations SET {self.field}=$1 WHERE org_id=$2", val, self.org_id)
            await interaction.response.send_message(f"✅ Поле `{self.field}` обновлено!", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Ошибка: уровень должен быть числом.", ephemeral=True)

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="admin", description="[STAFF] Управление балансом")
    @app_commands.choices(action=[
        app_commands.Choice(name="➕ Добавить", value="add"),
        app_commands.Choice(name="➖ Убрать", value="remove"),
        app_commands.Choice(name="🔄 Обновить", value="update"),
    ])
    @is_staff()
    async def admin(self, i: discord.Interaction, action: app_commands.Choice[str], member: discord.Member, amount: int):
        if amount < 0: return await i.response.send_message("❌ Сумма > 0.", ephemeral=True)
        await self.bot.db.get_user(member.id)
        
        if action.value == "add": await self.bot.db.update_wallet(member.id, amount)
        elif action.value == "remove": await self.bot.db.update_wallet(member.id, -amount)
        else: await self.bot.db.set_wallet(member.id, amount)
        
        u = await self.bot.db.get_user(member.id)
        embed = discord.Embed(title="Баланс изменен", color=0xEB459E, description=f"**Игрок:** {member.mention}\n**Новый баланс:** {fmt(u['wallet'])} 💰")
        await i.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="edit_org", description="[STAFF] Редактировать организацию по ID")
    @is_staff()
    async def edit_org(self, i: discord.Interaction, org_id: int):
        org = await self.bot.db.get_organization(org_id)
        if not org:
            return await i.response.send_message("Организация с таким ID не найдена.", ephemeral=True)
        
        await i.response.send_message(f"Выберите поле для изменения у **{org['name']}**:", view=EditOrgSelectView(self.bot, org_id), ephemeral=True)

    async def cog_app_command_error(self, i, error):
        if isinstance(error, app_commands.CheckFailure): await i.response.send_message(f"🚫 {error}", ephemeral=True)

async def setup(bot): await bot.add_cog(Admin(bot))
