import time
import io
import discord
from discord.ext import commands
from discord import app_commands
from utils.render import render_template

def fmt(n: int) -> str: return f"{n:,}".replace(",", " ")

class OrgEditModal(discord.ui.Modal, title="Настройки организации"):
    name = discord.ui.TextInput(label="Название", max_length=50)
    logo_url = discord.ui.TextInput(label="Ссылка на логотип", max_length=300)

    def __init__(self, bot, org_id: int, current_name: str, current_logo: str):
        super().__init__()
        self.bot = bot
        self.org_id = org_id
        self.name.default = current_name
        self.logo_url.default = current_logo

    async def on_submit(self, interaction: discord.Interaction):
        async with self.bot.db.pool.acquire() as c:
            await c.execute(
                "UPDATE organizations SET name=$1, logo_url=$2 WHERE org_id=$3",
                self.name.value, self.logo_url.value, self.org_id
            )
        await interaction.response.send_message("✅ Данные обновлены! Нажмите `/org` снова.", ephemeral=True)

# ─── Управление сотрудниками ───
class StaffManageView(discord.ui.View):
    def __init__(self, bot, org_id: int):
        super().__init__(timeout=120)
        self.bot = bot
        self.org_id = org_id

    @discord.ui.button(label="Нанять сотрудника", style=discord.ButtonStyle.success, emoji="➕")
    async def hire(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(HireModal(self.bot, self.org_id))

    @discord.ui.button(label="Список сотрудников", style=discord.ButtonStyle.secondary, emoji="📋")
    async def list_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        members = await self.bot.db.get_org_members(self.org_id)
        if not members:
            return await interaction.response.send_message("В организации нет сотрудников.", ephemeral=True)
        
        text = "\n".join([f"• <@{m['user_id']}> — {m['rank']}" for m in members])
        await interaction.response.send_message(f"**Сотрудники:**\n{text}", ephemeral=True)

class HireModal(discord.ui.Modal, title="Нанять сотрудника"):
    user_id = discord.ui.TextInput(label="Discord ID или @упоминание", placeholder="123456789012345678", max_length=50)
    rank = discord.ui.TextInput(label="Должность", placeholder="Менеджер", max_length=30, default="Сотрудник")

    def __init__(self, bot, org_id: int):
        super().__init__()
        self.bot = bot
        self.org_id = org_id

    async def on_submit(self, interaction: discord.Interaction):
        # Очищаем ввод от <@ ! >
        raw_id = self.user_id.value.replace("<@", "").replace("!", "").replace(">", "").strip()
        try:
            uid = int(raw_id)
        except ValueError:
            return await interaction.response.send_message("Ошибка: неверный ID пользователя.", ephemeral=True)
        
        await self.bot.db.add_org_member(self.org_id, uid, self.rank.value)
        await interaction.response.send_message(f"✅ <@{uid}> принят на должность **{self.rank.value}**!", ephemeral=True)

class OrgSelect(discord.ui.Select):
    def __init__(self, orgs: list, bot):
        options = [
            discord.SelectOption(label=o['name'], value=str(o['org_id']), description=f"{o['org_type']} • LVL {o['level']}")
            for o in orgs
        ]
        super().__init__(placeholder="Выберите организацию...", options=options)
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        org_id = int(self.values[0])
        await interaction.response.defer()
        org = await self.bot.db.get_organization(org_id)
        if not org:
            return await interaction.followup.send("Организация не найдена.", ephemeral=True)

        now = time.time()
        income = org["level"] * 500
        accumulated = min(int(((now - org["last_collect"]) / 3600) * income), income * 24)

        data = {
            "name": org["name"], "org_type": org["org_type"], "sphere": org["sphere"],
            "logo_url": org["logo_url"], "income": income, "acc": accumulated,
            "balance": org["balance"], "level": org["level"], "owner": interaction.user.name
        }
        
        png = await render_template("organization.html", data)
        file = discord.File(fp=io.BytesIO(png), filename="org.png")
        
        view = OrgActions(self.bot, org_id, org["name"], org["logo_url"])
        await interaction.followup.send(file=file, view=view, ephemeral=True)

class OrgActions(discord.ui.View):
    def __init__(self, bot, org_id: int, org_name: str, logo_url: str):
        super().__init__(timeout=120)
        self.bot = bot
        self.org_id = org_id
        self.org_name = org_name
        self.logo_url = logo_url

    @discord.ui.button(label="Собрать прибыль", style=discord.ButtonStyle.success, emoji="💰")
    async def collect(self, interaction: discord.Interaction, button: discord.ui.Button):
        org = await self.bot.db.get_organization(self.org_id)
        if not org or org["owner_id"] != interaction.user.id:
            return await interaction.response.send_message("Это не ваша организация.", ephemeral=True)
        now = time.time()
        hours = (now - org["last_collect"]) / 3600
        if hours < 1:
            return await interaction.response.send_message(f"Прибыль появится через {int((1-hours)*60)} мин.", ephemeral=True)
        income = org["level"] * 500
        accumulated = min(int(hours * income), income * 24)
        if accumulated <= 0:
            return await interaction.response.send_message("Нечего собирать.", ephemeral=True)
        await self.bot.db.update_wallet(interaction.user.id, accumulated)
        await self.bot.db.update_organization(self.org_id, last_collect=now)
        await interaction.response.send_message(f"Вы собрали **{fmt(accumulated)}** RUB!", ephemeral=True)

    @discord.ui.button(label="Бюджет", style=discord.ButtonStyle.primary, emoji="🏦")
    async def deposit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DepositModal(self.bot, self.org_id))

    @discord.ui.button(label="Улучшить", style=discord.ButtonStyle.secondary, emoji="📈")
    async def upgrade(self, interaction: discord.Interaction, button: discord.ui.Button):
        org = await self.bot.db.get_organization(self.org_id)
        if not org or org["owner_id"] != interaction.user.id:
            return await interaction.response.send_message("Это не ваша организация.", ephemeral=True)
        cost = org["level"] * 10000
        user = await self.bot.db.get_user(interaction.user.id)
        if user["wallet"] < cost:
            return await interaction.response.send_message(f"Нужно **{fmt(cost)}** RUB на кошельке.", ephemeral=True)
        await self.bot.db.update_wallet(interaction.user.id, -cost)
        await self.bot.db.update_organization(self.org_id, level=org["level"]+1)
        await interaction.response.send_message(f"Организация улучшена до **LVL {org['level']+1}**!", ephemeral=True)

    @discord.ui.button(label="Настройки", style=discord.ButtonStyle.secondary, emoji="⚙️", row=1)
    async def edit_org(self, interaction: discord.Interaction, button: discord.ui.Button):
        org = await self.bot.db.get_organization(self.org_id)
        if not org or org["owner_id"] != interaction.user.id:
            return await interaction.response.send_message("Только владелец может менять настройки.", ephemeral=True)
        await interaction.response.send_modal(OrgEditModal(self.bot, self.org_id, org["name"], org["logo_url"]))

    @discord.ui.button(label="Сотрудники", style=discord.ButtonStyle.secondary, emoji="👥", row=1)
    async def staff_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        org = await self.bot.db.get_organization(self.org_id)
        if not org or org["owner_id"] != interaction.user.id:
            return await interaction.response.send_message("Только владелец может управлять составом.", ephemeral=True)
        await interaction.response.send_message("Управление сотрудниками:", view=StaffManageView(self.bot, self.org_id), ephemeral=True)

class DepositModal(discord.ui.Modal, title="Пополнение бюджета"):
    amount = discord.ui.TextInput(label="Сумма", placeholder="1000", max_length=12)

    def __init__(self, bot, org_id: int):
        super().__init__()
        self.bot = bot
        self.org_id = org_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt = int(self.amount.value)
            if amt <= 0: raise ValueError
        except ValueError:
            return await interaction.response.send_message("Введите положительное число.", ephemeral=True)
        user = await self.bot.db.get_user(interaction.user.id)
        if user["wallet"] < amt:
            return await interaction.response.send_message("Недостаточно средств.", ephemeral=True)
        await self.bot.db.update_wallet(interaction.user.id, -amt)
        await self.bot.db.add_to_org_balance(self.org_id, amt)
        await interaction.response.send_message(f"Бюджет пополнен на **{fmt(amt)}** RUB.", ephemeral=True)

class Organization(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="org", description="Управление вашими организациями")
    async def org(self, i: discord.Interaction):
        orgs = await self.bot.db.get_user_organizations(i.user.id)
        if not orgs:
            return await i.response.send_message("У вас нет организаций.", ephemeral=True)
        
        if len(orgs) == 1:
            org_id = orgs[0]["org_id"]
            await i.response.defer(ephemeral=True)
            org = orgs[0]
            now = time.time()
            income = org["level"] * 500
            accumulated = min(int(((now - org["last_collect"]) / 3600) * income), income * 24)
            data = {
                "name": org["name"], "org_type": org["org_type"], "sphere": org["sphere"],
                "logo_url": org["logo_url"], "income": income, "acc": accumulated,
                "balance": org["balance"], "level": org["level"], "owner": i.user.name
            }
            png = await render_template("organization.html", data)
            file = discord.File(fp=io.BytesIO(png), filename="org.png")
            view = OrgActions(self.bot, org_id, org["name"], org["logo_url"])
            await i.followup.send(file=file, view=view, ephemeral=True)
        else:
            view = discord.ui.View()
            view.add_item(OrgSelect(orgs, self.bot))
            await i.response.send_message("Выберите организацию:", view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Organization(bot))
