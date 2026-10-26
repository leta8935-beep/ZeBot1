import discord
from discord.ext import commands
from discord import app_commands
from utils.checks import is_staff

def fmt(n: int) -> str: return f"{n:,}".replace(",", " ")

class BalanceModal(discord.ui.Modal):
    amount = discord.ui.TextInput(label="Сумма", placeholder="1000 или -1000", max_length=12)

    def __init__(self, bot, org_id: int, action: str):
        super().__init__(title="Добавить в бюджет" if action == "add" else "Убрать из бюджета")
        self.bot = bot
        self.org_id = org_id
        self.action = action

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt = int(self.amount.value)
            if amt <= 0: raise ValueError
        except ValueError:
            return await interaction.response.send_message("Введите положительное число.", ephemeral=True)
        
        org = await self.bot.db.get_organization(self.org_id)
        if self.action == "add":
            await self.bot.db.add_to_org_balance(self.org_id, amt)
        else:
            await self.bot.db.update_organization(self.org_id, balance=max(0, org["balance"] - amt))
        
        await interaction.response.send_message(f"✅ Бюджет обновлён. Текущий: **{fmt(org['balance'] + (amt if self.action == 'add' else -amt))}** RUB", ephemeral=True)

class EditOrgSelect(discord.ui.Select):
    def __init__(self, bot, org_id: int):
        options = [
            discord.SelectOption(label="Название", value="name"),
            discord.SelectOption(label="Логотип (URL)", value="logo_url"),
            discord.SelectOption(label="Тип организации", value="org_type"),
            discord.SelectOption(label="Сфера деятельности", value="sphere"),
            discord.SelectOption(label="Уровень", value="level")
        ]
        super().__init__(placeholder="Что изменить?", options=options)
        self.bot = bot
        self.org_id = org_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EditOrgFieldModal(self.bot, self.org_id, self.values[0]))

class EditOrgFieldModal(discord.ui.Modal, title="Редактирование поля"):
    value = discord.ui.TextInput(label="Новое значение")

    def __init__(self, bot, org_id: int, field: str):
        super().__init__()
        self.bot = bot
        self.org_id = org_id
        self.field = field
        self.value.label = f"Значение для '{field}'"

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.value.value) if self.field == "level" else self.value.value
            async with self.bot.db.pool.acquire() as c:
                await c.execute(f"UPDATE organizations SET {self.field}=$1 WHERE org_id=$2", val, self.org_id)
            await interaction.response.send_message(f"✅ Поле `{self.field}` обновлено!", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Ошибка: уровень должен быть числом.", ephemeral=True)

class ManageOrgActions(discord.ui.View):
    def __init__(self, bot, org_id: int):
        super().__init__(timeout=180)
        self.bot = bot
        self.org_id = org_id

    @discord.ui.button(label="Изменить баланс", style=discord.ButtonStyle.primary, emoji="💰")
    async def balance_btn(self, i: discord.Interaction, b: discord.ui.Button):
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Пополнить", style=discord.ButtonStyle.success, custom_id="add"))
        view.add_item(discord.ui.Button(label="Списать", style=discord.ButtonStyle.danger, custom_id="remove"))
        
        async def callback(inter: discord.Interaction):
            action = inter.data["custom_id"]
            await inter.response.send_modal(BalanceModal(self.bot, self.org_id, action))
            
        for child in view.children:
            child.callback = callback
        await i.response.send_message("Выберите действие с бюджетом:", view=view, ephemeral=True)

    @discord.ui.button(label="Редактировать поля", style=discord.ButtonStyle.secondary, emoji="⚙️")
    async def edit_btn(self, i: discord.Interaction, b: discord.ui.Button):
        view = discord.ui.View()
        view.add_item(EditOrgSelect(self.bot, self.org_id))
        await i.response.send_message("Выберите поле для изменения:", view=view, ephemeral=True)

    @discord.ui.button(label="Удалить организацию", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_btn(self, i: discord.Interaction, b: discord.ui.Button):
        org = await self.bot.db.get_organization(self.org_id)
        await self.bot.db.delete_organization(self.org_id)
        await i.response.edit_message(content=f"🗑️ Организация **{org['name']}** удалена.", embed=None, view=None)

class AdminOrgSelect(discord.ui.Select):
    def __init__(self, bot, orgs):
        options = [
            discord.SelectOption(label=o['name'], value=str(o['org_id']), description=f"Тип: {o['org_type']} | Владелец: {o['owner_id']}")
            for o in orgs
        ]
        super().__init__(placeholder="Выберите организацию для управления...", options=options)
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        org_id = int(self.values[0])
        org = await self.bot.db.get_organization(org_id)
        
        embed = discord.Embed(title=f"Управление: {org['name']}", color=0x5865F2)
        embed.add_field(name="Владелец", value=f"<@{org['owner_id']}>", inline=True)
        embed.add_field(name="Тип", value=org['org_type'], inline=True)
        embed.add_field(name="Уровень", value=str(org['level']), inline=True)
        embed.add_field(name="Бюджет", value=f"{fmt(org['balance'])} RUB", inline=True)
        embed.add_field(name="Логотип", value=org['logo_url'] or "Нет", inline=False)

        view = ManageOrgActions(self.bot, org_id)
        await interaction.response.edit_message(embed=embed, view=view)

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="admin", description="[STAFF] Управление балансом игроков")
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

    @app_commands.command(name="create_org", description="[STAFF] Создать организацию для игрока")
    @is_staff()
    async def create_org(self, i: discord.Interaction, member: discord.Member, name: str, org_type: str = "Бизнес"):
        await self.bot.db.create_organization(member.id, name, org_type, "Не указана", "")
        await i.response.send_message(f"✅ Организация **{name}** создана для {member.mention}!", ephemeral=True)

    @app_commands.command(name="manage_org", description="[STAFF] Меню управления организациями")
    @is_staff()
    async def manage_org(self, i: discord.Interaction):
        orgs = await self.bot.db.get_all_organizations()
        if not orgs:
            return await i.response.send_message("На сервере пока нет организаций.", ephemeral=True)
        
        view = discord.ui.View()
        view.add_item(AdminOrgSelect(self.bot, orgs))
        
        embed = discord.Embed(title="🏢 Управление организациями", description="Выберите организацию из списка по названию.", color=0x2b2d31)
        await i.response.send_message(embed=embed, view=view, ephemeral=True)

    async def cog_app_command_error(self, i, error):
        if isinstance(error, app_commands.CheckFailure): await i.response.send_message(f"🚫 {error}", ephemeral=True)

async def setup(bot): 
    await bot.add_cog(Admin(bot))
