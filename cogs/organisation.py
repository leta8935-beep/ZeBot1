import io
import time

import discord
from discord import app_commands
from discord.ext import commands

from utils.render import render_template


def fmt(value: int) -> str:
    return f"{int(value):,}".replace(",", " ")


def is_admin(interaction: discord.Interaction) -> bool:
    return bool(
        interaction.guild
        and (
            interaction.user.id == interaction.guild.owner_id
            or interaction.user.guild_permissions.administrator
        )
    )


async def get_org_access(interaction: discord.Interaction, bot, org_id: int):
    """Return (org, member, admin). Admins may manage every organization."""
    org = await bot.db.get_organization(org_id)
    if not org:
        return None, None, False

    admin = is_admin(interaction)
    member = await bot.db.get_org_member(org_id, interaction.user.id)
    # Owners of organizations created before this version may not have an
    # org_members row yet, so ownership itself is always sufficient access.
    if org["owner_id"] == interaction.user.id:
        if not member:
            member = {"org_id": org_id, "user_id": interaction.user.id, "rank": "Владелец"}
        return org, member, admin
    if admin or member:
        return org, member, admin
    return org, None, False


async def can_manage(interaction: discord.Interaction, bot, org_id: int) -> bool:
    org, member, admin = await get_org_access(interaction, bot, org_id)
    if not org:
        return False
    return admin or org["owner_id"] == interaction.user.id


async def org_image(bot, org):
    now = time.time()
    income = max(1, int(org["level"])) * 500
    last_collect = float(org["last_collect"] or now)
    elapsed_hours = max(0.0, (now - last_collect) / 3600)
    accumulated = min(int(elapsed_hours * income), income * 24)
    members_count = await bot.db.get_org_member_count(org["org_id"])
    next_cost = int(org["level"]) * 10000

    data = {
        "name": org["name"],
        "org_type": org["org_type"] or "Бизнес",
        "sphere": org["sphere"] or "Не указана",
        "logo_url": org["logo_url"] or "",
        "income": income,
        "acc": accumulated,
        "balance": int(org["balance"] or 0),
        "level": int(org["level"] or 1),
        "owner": f"<@{org['owner_id']}>",
        "members": members_count,
        "upgrade_cost": next_cost,
    }
    png = await render_template("organisation.html", data)
    return discord.File(io.BytesIO(png), filename="organisation.png")


class OrgEditModal(discord.ui.Modal, title="Настройка организации"):
    name = discord.ui.TextInput(label="Название", max_length=50)
    org_type = discord.ui.TextInput(label="Тип организации", max_length=30)
    sphere = discord.ui.TextInput(label="Сфера деятельности", max_length=60)
    logo_url = discord.ui.TextInput(
        label="Ссылка на логотип",
        placeholder="https://...",
        required=False,
        max_length=300,
    )

    def __init__(self, bot, org_id: int, org):
        super().__init__()
        self.bot = bot
        self.org_id = org_id
        self.name.default = org["name"]
        self.org_type.default = org["org_type"] or "Бизнес"
        self.sphere.default = org["sphere"] or "Не указана"
        self.logo_url.default = org["logo_url"] or ""

    async def on_submit(self, interaction: discord.Interaction):
        if not await can_manage(interaction, self.bot, self.org_id):
            return await interaction.response.send_message(
                "🚫 Недостаточно прав.",
                ephemeral=True,
            )

        await self.bot.db.update_organization(
            self.org_id,
            name=self.name.value.strip(),
            org_type=self.org_type.value.strip(),
            sphere=self.sphere.value.strip(),
            logo_url=self.logo_url.value.strip(),
        )
        await interaction.response.send_message(
            "✅ Данные организации обновлены.",
            ephemeral=True,
        )


class AmountModal(discord.ui.Modal):
    amount = discord.ui.TextInput(
        label="Сумма",
        placeholder="1000",
        min_length=1,
        max_length=15,
    )

    def __init__(self, bot, org_id: int, action: str):
        super().__init__(
            title="Пополнить бюджет" if action == "deposit" else "Вывести из бюджета"
        )
        self.bot = bot
        self.org_id = org_id
        self.action = action

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount.value.replace(" ", "").replace(",", ""))
            if amount <= 0:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(
                "❌ Введите положительное целое число.",
                ephemeral=True,
            )

        org, _, admin = await get_org_access(interaction, self.bot, self.org_id)
        if not org:
            return await interaction.response.send_message(
                "Организация не найдена.",
                ephemeral=True,
            )

        # Администратор работает с бюджетом напрямую, участник/владелец —
        # только со своего кошелька и только с разрешёнными операциями.
        if self.action == "deposit":
            user = await self.bot.db.get_user(interaction.user.id)
            if user["wallet"] < amount:
                return await interaction.response.send_message(
                    f"❌ На кошельке только **{fmt(user['wallet'])} RUB**.",
                    ephemeral=True,
                )
            await self.bot.db.update_wallet(interaction.user.id, -amount)
            await self.bot.db.add_to_org_balance(self.org_id, amount)
            await interaction.response.send_message(
                f"✅ В бюджет внесено **{fmt(amount)} RUB**.",
                ephemeral=True,
            )
            return

        if not admin and org["owner_id"] != interaction.user.id:
            return await interaction.response.send_message(
                "🚫 Вывод средств доступен только владельцу или администратору.",
                ephemeral=True,
            )

        if not await self.bot.db.withdraw_org_balance(
            self.org_id, interaction.user.id, amount
        ):
            return await interaction.response.send_message(
                "❌ Недостаточно средств в бюджете.",
                ephemeral=True,
            )

        await interaction.response.send_message(
            f"✅ На кошелёк зачислено **{fmt(amount)} RUB**.",
            ephemeral=True,
        )


class HireModal(discord.ui.Modal, title="Добавить сотрудника"):
    user_id = discord.ui.TextInput(
        label="Discord ID или упоминание",
        placeholder="123456789012345678 или @пользователь",
        max_length=50,
    )
    rank = discord.ui.TextInput(
        label="Должность",
        placeholder="Сотрудник",
        default="Сотрудник",
        max_length=30,
    )

    def __init__(self, bot, org_id: int):
        super().__init__()
        self.bot = bot
        self.org_id = org_id

    async def on_submit(self, interaction: discord.Interaction):
        if not await can_manage(interaction, self.bot, self.org_id):
            return await interaction.response.send_message(
                "🚫 Только владелец или администратор может управлять составом.",
                ephemeral=True,
            )

        raw = (
            self.user_id.value.replace("<@", "")
            .replace("!", "")
            .replace(">", "")
            .strip()
        )
        try:
            uid = int(raw)
        except ValueError:
            return await interaction.response.send_message(
                "❌ Не удалось распознать Discord ID.",
                ephemeral=True,
            )

        org = await self.bot.db.get_organization(self.org_id)
        if uid == org["owner_id"]:
            return await interaction.response.send_message(
                "ℹ️ Владелец уже является участником организации.",
                ephemeral=True,
            )

        await self.bot.db.get_user(uid)
        await self.bot.db.add_org_member(
            self.org_id, uid, self.rank.value.strip() or "Сотрудник"
        )
        await interaction.response.send_message(
            f"✅ <@{uid}> добавлен в организацию как **{self.rank.value.strip() or 'Сотрудник'}**.",
            ephemeral=True,
        )


class MemberActionModal(discord.ui.Modal):
    user_id = discord.ui.TextInput(
        label="Discord ID или упоминание",
        placeholder="ID участника",
        max_length=50,
    )

    def __init__(self, bot, org_id: int, action: str):
        super().__init__(
            title="Удалить сотрудника"
            if action == "remove"
            else "Изменить должность"
        )
        self.bot = bot
        self.org_id = org_id
        self.action = action

    async def on_submit(self, interaction: discord.Interaction):
        if not await can_manage(interaction, self.bot, self.org_id):
            return await interaction.response.send_message(
                "🚫 Недостаточно прав.",
                ephemeral=True,
            )

        raw = (
            self.user_id.value.replace("<@", "")
            .replace("!", "")
            .replace(">", "")
            .strip()
        )
        try:
            uid = int(raw)
        except ValueError:
            return await interaction.response.send_message(
                "❌ Неверный Discord ID.",
                ephemeral=True,
            )

        org = await self.bot.db.get_organization(self.org_id)
        if uid == org["owner_id"]:
            return await interaction.response.send_message(
                "❌ Владельца нельзя удалить или изменить через это меню.",
                ephemeral=True,
            )

        member = await self.bot.db.get_org_member(self.org_id, uid)
        if not member:
            return await interaction.response.send_message(
                "ℹ️ Такой участник не найден.",
                ephemeral=True,
            )

        if self.action == "remove":
            await self.bot.db.remove_org_member(self.org_id, uid)
            return await interaction.response.send_message(
                f"✅ <@{uid}> исключён из организации.",
                ephemeral=True,
            )

        await interaction.response.send_modal(
            RankModal(self.bot, self.org_id, uid, member["rank"])
        )


class RankModal(discord.ui.Modal, title="Изменение должности"):
    rank = discord.ui.TextInput(
        label="Новая должность",
        max_length=30,
    )

    def __init__(self, bot, org_id: int, user_id: int, current: str):
        super().__init__()
        self.bot = bot
        self.org_id = org_id
        self.user_id = user_id
        self.rank.default = current

    async def on_submit(self, interaction: discord.Interaction):
        if not await can_manage(interaction, self.bot, self.org_id):
            return await interaction.response.send_message(
                "🚫 Недостаточно прав.",
                ephemeral=True,
            )
        await self.bot.db.update_org_member_rank(
            self.org_id, self.user_id, self.rank.value
        )
        await interaction.response.send_message(
            f"✅ Должность <@{self.user_id}> изменена на **{self.rank.value}**.",
            ephemeral=True,
        )


class TransferModal(discord.ui.Modal, title="Передача организации"):
    user_id = discord.ui.TextInput(
        label="Новый владелец",
        placeholder="Discord ID или @упоминание",
        max_length=50,
    )

    def __init__(self, bot, org_id: int):
        super().__init__()
        self.bot = bot
        self.org_id = org_id

    async def on_submit(self, interaction: discord.Interaction):
        org = await self.bot.db.get_organization(self.org_id)
        if not org or (
            org["owner_id"] != interaction.user.id and not is_admin(interaction)
        ):
            return await interaction.response.send_message(
                "🚫 Передать организацию может только владелец или администратор.",
                ephemeral=True,
            )

        raw = (
            self.user_id.value.replace("<@", "")
            .replace("!", "")
            .replace(">", "")
            .strip()
        )
        try:
            uid = int(raw)
        except ValueError:
            return await interaction.response.send_message(
                "❌ Неверный Discord ID.",
                ephemeral=True,
            )

        if uid == org["owner_id"]:
            return await interaction.response.send_message(
                "ℹ️ Этот пользователь уже владелец.",
                ephemeral=True,
            )

        await self.bot.db.get_user(uid)
        await self.bot.db.transfer_organization(self.org_id, uid)
        await interaction.response.send_message(
            f"✅ Организация **{org['name']}** передана <@{uid}>.",
            ephemeral=True,
        )


class DeleteConfirmView(discord.ui.View):
    def __init__(self, bot, org_id: int):
        super().__init__(timeout=30)
        self.bot = bot
        self.org_id = org_id

    @discord.ui.button(label="Удалить окончательно", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await can_manage(interaction, self.bot, self.org_id):
            return await interaction.response.send_message(
                "🚫 Недостаточно прав.",
                ephemeral=True,
            )
        org = await self.bot.db.get_organization(self.org_id)
        if not org:
            return await interaction.response.edit_message(
                content="Организация уже удалена.",
                view=None,
            )
        await self.bot.db.delete_organization(self.org_id)
        await interaction.response.edit_message(
            content=f"🗑️ Организация **{org['name']}** удалена.",
            view=None,
            attachments=[],
        )

    @discord.ui.button(label="Отмена", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="Удаление отменено.",
            view=None,
        )


class StaffView(discord.ui.View):
    def __init__(self, bot, org_id: int):
        super().__init__(timeout=180)
        self.bot = bot
        self.org_id = org_id

    @discord.ui.button(label="Список", style=discord.ButtonStyle.secondary, emoji="📋")
    async def listing(self, interaction: discord.Interaction, button: discord.ui.Button):
        org, _, _ = await get_org_access(interaction, self.bot, self.org_id)
        if not org:
            return await interaction.response.send_message(
                "🚫 Нет доступа.",
                ephemeral=True,
            )
        members = await self.bot.db.get_org_members(self.org_id)
        if not members:
            text = "В организации пока нет участников."
        else:
            lines = [
                f"**{idx}.** <@{m['user_id']}> — `{m['rank']}`"
                for idx, m in enumerate(members, 1)
            ]
            text = "\n".join(lines[:25])
            if len(lines) > 25:
                text += f"\n… и ещё {len(lines) - 25}."
        await interaction.response.send_message(
            f"### 👥 Состав организации\n{text}",
            ephemeral=True,
        )

    @discord.ui.button(label="Добавить", style=discord.ButtonStyle.success, emoji="➕")
    async def hire(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await can_manage(interaction, self.bot, self.org_id):
            return await interaction.response.send_message(
                "🚫 Только владелец или администратор.",
                ephemeral=True,
            )
        await interaction.response.send_modal(HireModal(self.bot, self.org_id))

    @discord.ui.button(label="Изменить должность", style=discord.ButtonStyle.primary, emoji="✏️")
    async def rank(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await can_manage(interaction, self.bot, self.org_id):
            return await interaction.response.send_message(
                "🚫 Только владелец или администратор.",
                ephemeral=True,
            )
        await interaction.response.send_modal(
            MemberActionModal(self.bot, self.org_id, "rank")
        )

    @discord.ui.button(label="Исключить", style=discord.ButtonStyle.danger, emoji="➖")
    async def remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await can_manage(interaction, self.bot, self.org_id):
            return await interaction.response.send_message(
                "🚫 Только владелец или администратор.",
                ephemeral=True,
            )
        await interaction.response.send_modal(
            MemberActionModal(self.bot, self.org_id, "remove")
        )

    @discord.ui.button(label="Назад", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_org(interaction, self.bot, self.org_id, edit=True)


class OrgActions(discord.ui.View):
    def __init__(self, bot, org_id: int, admin: bool = False):
        super().__init__(timeout=300)
        self.bot = bot
        self.org_id = org_id
        self.admin = admin

    @discord.ui.button(label="Собрать доход", style=discord.ButtonStyle.success, emoji="💰")
    async def collect(self, interaction: discord.Interaction, button: discord.ui.Button):
        org, member, admin = await get_org_access(interaction, self.bot, self.org_id)
        if not org:
            return await interaction.response.send_message("Организация не найдена.", ephemeral=True)
        if not admin and org["owner_id"] != interaction.user.id:
            return await interaction.response.send_message(
                "🚫 Собирать доход может только владелец или администратор.",
                ephemeral=True,
            )

        now = time.time()
        last = float(org["last_collect"] or now)
        income = int(org["level"]) * 500
        hours = max(0.0, (now - last) / 3600)
        if hours < 1:
            minutes = max(1, int((1 - hours) * 60))
            return await interaction.response.send_message(
                f"⏳ Следующий сбор будет доступен примерно через **{minutes} мин.**",
                ephemeral=True,
            )

        accumulated = min(int(hours * income), income * 24)
        await self.bot.db.update_wallet(org["owner_id"], accumulated)
        await self.bot.db.update_organization(
            self.org_id, last_collect=now
        )
        await interaction.response.send_message(
            f"💰 Собрано **{fmt(accumulated)} RUB** на кошелёк владельца.",
            ephemeral=True,
        )

    @discord.ui.button(label="Пополнить", style=discord.ButtonStyle.primary, emoji="🏦")
    async def deposit(self, interaction: discord.Interaction, button: discord.ui.Button):
        org, _, _ = await get_org_access(interaction, self.bot, self.org_id)
        if not org:
            return await interaction.response.send_message("Нет доступа.", ephemeral=True)
        await interaction.response.send_modal(
            AmountModal(self.bot, self.org_id, "deposit")
        )

    @discord.ui.button(label="Бюджет", style=discord.ButtonStyle.secondary, emoji="💳")
    async def budget(self, interaction: discord.Interaction, button: discord.ui.Button):
        org, _, admin = await get_org_access(interaction, self.bot, self.org_id)
        if not org:
            return await interaction.response.send_message("Нет доступа.", ephemeral=True)
        view = BudgetView(self.bot, self.org_id, admin)
        await interaction.response.send_message(
            "### 💳 Управление бюджетом\nВыберите действие:",
            view=view,
            ephemeral=True,
        )

    @discord.ui.button(label="Сотрудники", style=discord.ButtonStyle.secondary, emoji="👥", row=1)
    async def staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        org, _, _ = await get_org_access(interaction, self.bot, self.org_id)
        if not org:
            return await interaction.response.send_message("🚫 Нет доступа.", ephemeral=True)
        await interaction.response.send_message(
            "### 👥 Управление составом",
            view=StaffView(self.bot, self.org_id),
            ephemeral=True,
        )

    @discord.ui.button(label="Настройки", style=discord.ButtonStyle.secondary, emoji="⚙️", row=1)
    async def settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        org, _, _ = await get_org_access(interaction, self.bot, self.org_id)
        if not org:
            return await interaction.response.send_message("🚫 Нет доступа.", ephemeral=True)
        if not await can_manage(interaction, self.bot, self.org_id):
            return await interaction.response.send_message(
                "🚫 Настройки доступны только владельцу или администратору.",
                ephemeral=True,
            )
        await interaction.response.send_modal(
            OrgEditModal(self.bot, self.org_id, org)
        )

    @discord.ui.button(label="Улучшить", style=discord.ButtonStyle.primary, emoji="📈", row=1)
    async def upgrade(self, interaction: discord.Interaction, button: discord.ui.Button):
        org, _, admin = await get_org_access(interaction, self.bot, self.org_id)
        if not org:
            return await interaction.response.send_message("Организация не найдена.", ephemeral=True)
        if not admin and org["owner_id"] != interaction.user.id:
            return await interaction.response.send_message(
                "🚫 Улучшать организацию может только владелец или администратор.",
                ephemeral=True,
            )

        cost = int(org["level"]) * 10000
        owner = await self.bot.db.get_user(org["owner_id"])
        if owner["wallet"] < cost:
            return await interaction.response.send_message(
                f"❌ Для улучшения нужно **{fmt(cost)} RUB** на кошельке владельца.",
                ephemeral=True,
            )
        await self.bot.db.update_wallet(org["owner_id"], -cost)
        await self.bot.db.update_organization(
            self.org_id, level=int(org["level"]) + 1
        )
        await interaction.response.send_message(
            f"📈 Организация улучшена до **LVL {int(org['level']) + 1}**.",
            ephemeral=True,
        )

    @discord.ui.button(label="Передать", style=discord.ButtonStyle.secondary, emoji="🔁", row=2)
    async def transfer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await can_manage(interaction, self.bot, self.org_id):
            return await interaction.response.send_message(
                "🚫 Только владелец или администратор.",
                ephemeral=True,
            )
        await interaction.response.send_modal(
            TransferModal(self.bot, self.org_id)
        )

    @discord.ui.button(label="Удалить", style=discord.ButtonStyle.danger, emoji="🗑️", row=2)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await can_manage(interaction, self.bot, self.org_id):
            return await interaction.response.send_message(
                "🚫 Только владелец или администратор.",
                ephemeral=True,
            )
        org = await self.bot.db.get_organization(self.org_id)
        await interaction.response.send_message(
            f"⚠️ **Удалить «{org['name']}»?**\n"
            "Это действие удалит организацию и весь её состав.",
            view=DeleteConfirmView(self.bot, self.org_id),
            ephemeral=True,
        )

    @discord.ui.button(label="Обновить", style=discord.ButtonStyle.secondary, emoji="🔄", row=2)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_org(interaction, self.bot, self.org_id, edit=True)


class BudgetView(discord.ui.View):
    def __init__(self, bot, org_id: int, admin: bool):
        super().__init__(timeout=120)
        self.bot = bot
        self.org_id = org_id
        self.admin = admin

    @discord.ui.button(label="Пополнить со своего кошелька", style=discord.ButtonStyle.success, emoji="➕")
    async def deposit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            AmountModal(self.bot, self.org_id, "deposit")
        )

    @discord.ui.button(label="Вывести владельцу", style=discord.ButtonStyle.primary, emoji="➖")
    async def withdraw(self, interaction: discord.Interaction, button: discord.ui.Button):
        org = await self.bot.db.get_organization(self.org_id)
        if not org:
            return await interaction.response.send_message("Организация не найдена.", ephemeral=True)
        if not self.admin and org["owner_id"] != interaction.user.id:
            return await interaction.response.send_message(
                "🚫 Вывод доступен только владельцу или администратору.",
                ephemeral=True,
            )
        await interaction.response.send_modal(
            AmountModal(self.bot, self.org_id, "withdraw")
        )

    @discord.ui.button(label="Назад", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_org(interaction, self.bot, self.org_id, edit=True)


class OrgSelect(discord.ui.Select):
    def __init__(self, bot, orgs, admin: bool):
        self.bot = bot
        self.admin = admin
        options = []
        for org in list(orgs)[:25]:
            options.append(
                discord.SelectOption(
                    label=str(org["name"])[:100],
                    value=str(org["org_id"]),
                    description=(
                        f"Владелец: {org['owner_id']}"
                        if admin
                        else f"LVL {org['level']} • {fmt(org['balance'])} RUB"
                    )[:100],
                )
            )
        super().__init__(
            placeholder="Выберите организацию…",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await show_org(
            interaction,
            self.bot,
            int(self.values[0]),
            edit=True,
        )


class OrgListView(discord.ui.View):
    def __init__(self, bot, orgs, admin: bool):
        super().__init__(timeout=180)
        self.bot = bot
        self.orgs = orgs
        self.admin = admin
        self.add_item(OrgSelect(bot, orgs, admin))


async def show_org(
    interaction: discord.Interaction,
    bot,
    org_id: int,
    edit: bool = False,
):
    org, _, admin = await get_org_access(interaction, bot, org_id)
    if not org:
        message = "🚫 Организация не найдена или у вас нет доступа."
        if interaction.response.is_done():
            return await interaction.followup.send(message, ephemeral=True)
        return await interaction.response.send_message(message, ephemeral=True)

    file = await org_image(bot, org)
    view = OrgActions(bot, org_id, admin=admin)

    content = (
        f"### 🏢 {org['name']}\n"
        f"Уровень **{org['level']}** · бюджет **{fmt(org['balance'])} RUB**\n"
        "Используйте кнопки ниже для управления организацией."
    )

    if edit and interaction.response.is_done():
        return await interaction.edit_original_response(
            content=content,
            attachments=[file],
            view=view,
        )

    if edit:
        await interaction.response.edit_message(
            content=content,
            attachments=[file],
            view=view,
        )
    else:
        await interaction.response.send_message(
            content=content,
            file=file,
            view=view,
            ephemeral=True,
        )


class Organization(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="org",
        description="Открыть управление организациями",
    )
    async def org(self, interaction: discord.Interaction):
        admin = is_admin(interaction)
        orgs = (
            await self.bot.db.get_all_organizations()
            if admin
            else await self.bot.db.get_user_organizations(interaction.user.id)
        )

        if not orgs:
            return await interaction.response.send_message(
                "🏢 У вас нет доступных организаций.",
                ephemeral=True,
            )

        if len(orgs) == 1:
            await show_org(
                interaction,
                self.bot,
                int(orgs[0]["org_id"]),
                edit=False,
            )
            return

        visible = list(orgs)[:25]
        suffix = ""
        if len(orgs) > 25:
            suffix = (
                f"\n\n⚠️ Показаны первые 25 из {len(orgs)} организаций."
            )
        await interaction.response.send_message(
            "### 🏢 Ваши организации\n"
            "Выберите организацию из списка:"
            + suffix,
            view=OrgListView(self.bot, visible, admin),
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Organization(bot))
