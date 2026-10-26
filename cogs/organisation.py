import io
import time

import discord
from discord.ext import commands
from discord import app_commands

from utils.render import render_template


def fmt(n: int) -> str:
    return f"{int(n):,}".replace(",", " ")


def is_admin(interaction: discord.Interaction) -> bool:
    return bool(
        interaction.guild
        and (
            interaction.user.id == interaction.guild.owner_id
            or interaction.user.guild_permissions.administrator
        )
    )


async def render_org(bot, org):
    now = time.time()
    income = max(1, org["level"]) * 500
    accumulated = min(
        max(0, int(((now - org["last_collect"]) / 3600) * income)),
        income * 24,
    )
    data = {
        "name": org["name"],
        "org_type": org["org_type"],
        "sphere": org["sphere"],
        "logo_url": org["logo_url"],
        "income": income,
        "acc": accumulated,
        "balance": org["balance"],
        "level": org["level"],
        "owner": f"<@{org['owner_id']}>",
    }
    png = await render_template("organisation.html", data)
    return png


async def can_view(bot, interaction, org) -> bool:
    if is_admin(interaction):
        return True
    return org["owner_id"] == interaction.user.id or await bot.db.is_org_member(
        org["org_id"], interaction.user.id
    )


async def can_manage(bot, interaction, org) -> bool:
    if is_admin(interaction):
        return True
    return org["owner_id"] == interaction.user.id


class OrgEditModal(discord.ui.Modal, title="Настройки организации"):
    name = discord.ui.TextInput(label="Название", max_length=50)
    logo_url = discord.ui.TextInput(label="Ссылка на логотип", required=False, max_length=300)

    def __init__(self, bot, org_id: int, current_name: str, current_logo: str):
        super().__init__()
        self.bot = bot
        self.org_id = org_id
        self.name.default = current_name
        self.logo_url.default = current_logo or ""

    async def on_submit(self, interaction: discord.Interaction):
        await self.bot.db.update_organization(
            self.org_id, name=self.name.value.strip(), logo_url=self.logo_url.value.strip()
        )
        await interaction.response.send_message(
            "✅ Данные организации обновлены.", ephemeral=True
        )


class AdminBalanceModal(discord.ui.Modal):
    amount = discord.ui.TextInput(label="Сумма", placeholder="1000", max_length=12)

    def __init__(self, bot, org_id: int, action: str):
        super().__init__(title="Добавить в бюджет" if action == "add" else "Убрать из бюджета")
        self.bot = bot
        self.org_id = org_id
        self.action = action

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount.value)
            if amount <= 0:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(
                "Введите положительное целое число.", ephemeral=True
            )

        org = await self.bot.db.get_organization(self.org_id)
        if not org:
            return await interaction.response.send_message(
                "Организация не найдена.", ephemeral=True
            )

        if self.action == "add":
            new_balance = org["balance"] + amount
            await self.bot.db.add_to_org_balance(self.org_id, amount)
        else:
            new_balance = max(0, org["balance"] - amount)
            await self.bot.db.remove_from_org_balance(self.org_id, amount)

        await interaction.response.send_message(
            f"✅ Бюджет изменён. Текущий баланс: **{fmt(new_balance)}** RUB.",
            ephemeral=True,
        )


class StaffManageView(discord.ui.View):
    def __init__(self, bot, org_id: int):
        super().__init__(timeout=120)
        self.bot = bot
        self.org_id = org_id

    @discord.ui.button(label="Нанять", style=discord.ButtonStyle.success, emoji="➕")
    async def hire(self, interaction: discord.Interaction, button: discord.ui.Button):
        org = await self.bot.db.get_organization(self.org_id)
        if not org or not await can_manage(self.bot, interaction, org):
            return await interaction.response.send_message("Нет прав.", ephemeral=True)
        await interaction.response.send_modal(HireModal(self.bot, self.org_id))

    @discord.ui.button(label="Список", style=discord.ButtonStyle.secondary, emoji="📋")
    async def list_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        org = await self.bot.db.get_organization(self.org_id)
        if not org or not await can_view(self.bot, interaction, org):
            return await interaction.response.send_message("Нет доступа.", ephemeral=True)

        members = await self.bot.db.get_org_members(self.org_id)
        if not members:
            return await interaction.response.send_message(
                "В организации пока нет записанных сотрудников.", ephemeral=True
            )

        text = "\n".join(
            f"• <@{m['user_id']}> — **{m['rank']}**" for m in members
        )
        await interaction.response.send_message(
            f"**Сотрудники организации:**\n{text}", ephemeral=True
        )

    @discord.ui.button(label="Уволить", style=discord.ButtonStyle.danger, emoji="➖", row=1)
    async def fire(self, interaction: discord.Interaction, button: discord.ui.Button):
        org = await self.bot.db.get_organization(self.org_id)
        if not org or not await can_manage(self.bot, interaction, org):
            return await interaction.response.send_message("Нет прав.", ephemeral=True)
        await interaction.response.send_modal(FireModal(self.bot, self.org_id))

    @discord.ui.button(label="Изменить должность", style=discord.ButtonStyle.primary, emoji="🪪", row=1)
    async def rank(self, interaction: discord.Interaction, button: discord.ui.Button):
        org = await self.bot.db.get_organization(self.org_id)
        if not org or not await can_manage(self.bot, interaction, org):
            return await interaction.response.send_message("Нет прав.", ephemeral=True)
        await interaction.response.send_modal(RankModal(self.bot, self.org_id))


class HireModal(discord.ui.Modal, title="Нанять сотрудника"):
    user_id = discord.ui.TextInput(label="Discord ID или @упоминание", max_length=50)
    rank = discord.ui.TextInput(label="Должность", max_length=30, default="Сотрудник")

    def __init__(self, bot, org_id: int):
        super().__init__()
        self.bot = bot
        self.org_id = org_id

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.user_id.value.replace("<@", "").replace("!", "").replace(">", "").strip()
        try:
            uid = int(raw)
        except ValueError:
            return await interaction.response.send_message("Неверный Discord ID.", ephemeral=True)

        await self.bot.db.add_org_member(self.org_id, uid, self.rank.value.strip() or "Сотрудник")
        await interaction.response.send_message(
            f"✅ <@{uid}> добавлен в организацию.", ephemeral=True
        )


class FireModal(discord.ui.Modal, title="Уволить сотрудника"):
    user_id = discord.ui.TextInput(label="Discord ID или @упоминание", max_length=50)

    def __init__(self, bot, org_id: int):
        super().__init__()
        self.bot = bot
        self.org_id = org_id

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.user_id.value.replace("<@", "").replace("!", "").replace(">", "").strip()
        try:
            uid = int(raw)
        except ValueError:
            return await interaction.response.send_message("Неверный Discord ID.", ephemeral=True)

        await self.bot.db.remove_org_member(self.org_id, uid)
        await interaction.response.send_message("✅ Сотрудник удалён.", ephemeral=True)


class RankModal(discord.ui.Modal, title="Изменить должность"):
    user_id = discord.ui.TextInput(label="Discord ID или @упоминание", max_length=50)
    rank = discord.ui.TextInput(label="Новая должность", max_length=30)

    def __init__(self, bot, org_id: int):
        super().__init__()
        self.bot = bot
        self.org_id = org_id

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.user_id.value.replace("<@", "").replace("!", "").replace(">", "").strip()
        try:
            uid = int(raw)
        except ValueError:
            return await interaction.response.send_message("Неверный Discord ID.", ephemeral=True)

        await self.bot.db.set_org_member_rank(self.org_id, uid, self.rank.value.strip() or "Сотрудник")
        await interaction.response.send_message("✅ Должность изменена.", ephemeral=True)


class DepositModal(discord.ui.Modal, title="Пополнение бюджета"):
    amount = discord.ui.TextInput(label="Сумма", placeholder="1000", max_length=12)

    def __init__(self, bot, org_id: int):
        super().__init__()
        self.bot = bot
        self.org_id = org_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount.value)
            if amount <= 0:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(
                "Введите положительную сумму.", ephemeral=True
            )

        org = await self.bot.db.get_organization(self.org_id)
        if not org or not await can_manage(self.bot, interaction, org):
            return await interaction.response.send_message("Нет прав.", ephemeral=True)

        user = await self.bot.db.get_user(interaction.user.id)
        if user["wallet"] < amount:
            return await interaction.response.send_message("Недостаточно денег.", ephemeral=True)

        await self.bot.db.update_wallet(interaction.user.id, -amount)
        await self.bot.db.add_to_org_balance(self.org_id, amount)
        await interaction.response.send_message(
            f"✅ В бюджет внесено **{fmt(amount)}** RUB.", ephemeral=True
        )


class OrgActions(discord.ui.View):
    def __init__(self, bot, org_id: int, viewer_is_admin: bool = False):
        super().__init__(timeout=180)
        self.bot = bot
        self.org_id = org_id
        self.viewer_is_admin = viewer_is_admin

    @discord.ui.button(label="Собрать прибыль", style=discord.ButtonStyle.success, emoji="💰")
    async def collect(self, interaction: discord.Interaction, button: discord.ui.Button):
        org = await self.bot.db.get_organization(self.org_id)
        if not org or not await can_manage(self.bot, interaction, org):
            return await interaction.response.send_message(
                "Только владелец или администратор может собирать прибыль.", ephemeral=True
            )

        now = time.time()
        hours = (now - org["last_collect"]) / 3600
        if hours < 1:
            return await interaction.response.send_message(
                f"Прибыль будет доступна через {int((1 - hours) * 60)} мин.",
                ephemeral=True,
            )

        income = org["level"] * 500
        accumulated = min(int(hours * income), income * 24)
        await self.bot.db.update_wallet(org["owner_id"], accumulated)
        await self.bot.db.update_organization(self.org_id, last_collect=now)
        await interaction.response.send_message(
            f"💰 Собрано **{fmt(accumulated)}** RUB владельцу организации.",
            ephemeral=True,
        )

    @discord.ui.button(label="Пополнить бюджет", style=discord.ButtonStyle.primary, emoji="🏦")
    async def deposit(self, interaction: discord.Interaction, button: discord.ui.Button):
        org = await self.bot.db.get_organization(self.org_id)
        if not org or not await can_manage(self.bot, interaction, org):
            return await interaction.response.send_message("Нет прав.", ephemeral=True)
        await interaction.response.send_modal(DepositModal(self.bot, self.org_id))

    @discord.ui.button(label="Улучшить", style=discord.ButtonStyle.secondary, emoji="📈")
    async def upgrade(self, interaction: discord.Interaction, button: discord.ui.Button):
        org = await self.bot.db.get_organization(self.org_id)
        if not org or not await can_manage(self.bot, interaction, org):
            return await interaction.response.send_message("Нет прав.", ephemeral=True)

        cost = org["level"] * 10000
        user = await self.bot.db.get_user(org["owner_id"])
        if user["wallet"] < cost:
            return await interaction.response.send_message(
                f"В кошельке владельца нужно **{fmt(cost)}** RUB.", ephemeral=True
            )

        await self.bot.db.update_wallet(org["owner_id"], -cost)
        await self.bot.db.update_organization(self.org_id, level=org["level"] + 1)
        await interaction.response.send_message(
            f"📈 Организация улучшена до **LVL {org['level'] + 1}**.",
            ephemeral=True,
        )

    @discord.ui.button(label="Настройки", style=discord.ButtonStyle.secondary, emoji="⚙️", row=1)
    async def edit_org(self, interaction: discord.Interaction, button: discord.ui.Button):
        org = await self.bot.db.get_organization(self.org_id)
        if not org or not await can_manage(self.bot, interaction, org):
            return await interaction.response.send_message("Нет прав.", ephemeral=True)
        await interaction.response.send_modal(
            OrgEditModal(self.bot, self.org_id, org["name"], org["logo_url"])
        )

    @discord.ui.button(label="Сотрудники", style=discord.ButtonStyle.secondary, emoji="👥", row=1)
    async def staff_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        org = await self.bot.db.get_organization(self.org_id)
        if not org or not await can_view(self.bot, interaction, org):
            return await interaction.response.send_message("Нет доступа.", ephemeral=True)
        await interaction.response.send_message(
            "Управление сотрудниками:",
            view=StaffManageView(self.bot, self.org_id),
            ephemeral=True,
        )

    @discord.ui.button(label="Админ: бюджет", style=discord.ButtonStyle.danger, emoji="🛠️", row=2)
    async def admin_balance(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin(interaction):
            return await interaction.response.send_message(
                "Эта функция доступна только администраторам.", ephemeral=True
            )
        view = discord.ui.View(timeout=60)
        add = discord.ui.Button(label="Пополнить", style=discord.ButtonStyle.success)
        remove = discord.ui.Button(label="Списать", style=discord.ButtonStyle.danger)

        async def add_cb(inter):
            await inter.response.send_modal(AdminBalanceModal(self.bot, self.org_id, "add"))

        async def remove_cb(inter):
            await inter.response.send_modal(AdminBalanceModal(self.bot, self.org_id, "remove"))

        add.callback = add_cb
        remove.callback = remove_cb
        view.add_item(add)
        view.add_item(remove)
        await interaction.response.send_message(
            "Выберите действие с бюджетом:", view=view, ephemeral=True
        )

    @discord.ui.button(label="Удалить", style=discord.ButtonStyle.danger, emoji="🗑️", row=2)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        org = await self.bot.db.get_organization(self.org_id)
        if not org or not is_admin(interaction):
            return await interaction.response.send_message(
                "Удалять организации может только администратор.", ephemeral=True
            )
        await interaction.response.send_message(
            f"Подтвердить удаление **{org['name']}**?",
            view=DeleteConfirmView(self.bot, self.org_id),
            ephemeral=True,
        )


class DeleteConfirmView(discord.ui.View):
    def __init__(self, bot, org_id):
        super().__init__(timeout=30)
        self.bot = bot
        self.org_id = org_id

    @discord.ui.button(label="Да, удалить", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin(interaction):
            return await interaction.response.send_message("Нет прав.", ephemeral=True)
        org = await self.bot.db.get_organization(self.org_id)
        if not org:
            return await interaction.response.send_message("Организация уже удалена.", ephemeral=True)
        await self.bot.db.delete_organization(self.org_id)
        await interaction.response.edit_message(
            content=f"🗑️ Организация **{org['name']}** удалена.",
            view=None,
        )

    @discord.ui.button(label="Отмена", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Удаление отменено.", view=None)


class OrgSelect(discord.ui.Select):
    def __init__(self, orgs, bot, viewer_is_admin):
        options = [
            discord.SelectOption(
                label=str(o["name"])[:100],
                value=str(o["org_id"]),
                description=(
                    f"Владелец: {o['owner_id']}"
                    if viewer_is_admin
                    else f"LVL {o['level']} • {o['sphere']}"
                )[:100],
            )
            for o in orgs[:25]
        ]
        super().__init__(placeholder="Выберите организацию…", options=options)
        self.bot = bot
        self.viewer_is_admin = viewer_is_admin

    async def callback(self, interaction: discord.Interaction):
        org = await self.bot.db.get_organization(int(self.values[0]))
        if not org or not await can_view(self.bot, interaction, org):
            return await interaction.response.send_message("Нет доступа.", ephemeral=True)

        png = await render_org(self.bot, org)
        await interaction.response.send_message(
            file=discord.File(io.BytesIO(png), filename="org.png"),
            view=OrgActions(self.bot, org["org_id"], self.viewer_is_admin),
            ephemeral=True,
        )


class Organization(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="org", description="Просмотр и управление организацией")
    @app_commands.describe(name="Название организации. Администратор может указать любую.")
    async def org(self, interaction: discord.Interaction, name: str | None = None):
        admin = is_admin(interaction)

        if name:
            org = await self.bot.db.get_organization_by_name(name)
            if not org:
                return await interaction.response.send_message(
                    "Организация с таким названием не найдена.", ephemeral=True
                )
            if not admin and not await can_view(self.bot, interaction, org):
                return await interaction.response.send_message(
                    "Вы можете просматривать только свою организацию.", ephemeral=True
                )
            png = await render_org(self.bot, org)
            await interaction.response.send_message(
                file=discord.File(io.BytesIO(png), filename="org.png"),
                view=OrgActions(self.bot, org["org_id"], admin),
                ephemeral=True,
            )
            return

        orgs = (
            await self.bot.db.get_all_organizations()
            if admin
            else await self.bot.db.get_user_organizations(interaction.user.id)
        )

        if not orgs:
            return await interaction.response.send_message(
                "Организаций, доступных вам, не найдено.", ephemeral=True
            )

        if len(orgs) == 1:
            png = await render_org(self.bot, orgs[0])
            await interaction.response.send_message(
                file=discord.File(io.BytesIO(png), filename="org.png"),
                view=OrgActions(self.bot, orgs[0]["org_id"], admin),
                ephemeral=True,
            )
            return

        view = discord.ui.View(timeout=120)
        view.add_item(OrgSelect(orgs, self.bot, admin))
        await interaction.response.send_message(
            "Выберите организацию:", view=view, ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Organization(bot))
