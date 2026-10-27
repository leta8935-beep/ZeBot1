import io
import time
import discord
from discord import app_commands
from discord.ext import commands
from pathlib import Path
from storage import storage

from database import db
from utils import organization_image


CAT_LABEL = {
    "ministry": "Министерство",
    "organization": "Организация",
    "company": "Компания",
    "other": "Другое",
}
TYPE_LABEL = {"government": "Государственная", "private": "Частная"}
ROLE_LABEL = {"leader": "👑 Лидер", "officer": "🎖️ Офицер", "member": "👤 Участник"}


# ============================================================
# МОДАЛЬНОЕ ОКНО СОЗДАНИЯ
# ============================================================
class CreateOrgModal(discord.ui.Modal, title="Создание организации"):
    name = discord.ui.TextInput(label="Название", max_length=60, required=True,
                                placeholder="Например: Министерство Обороны")
    short = discord.ui.TextInput(label="Короткое название", max_length=12, required=False,
                                 placeholder="МО")
    description = discord.ui.TextInput(label="Описание", style=discord.TextStyle.paragraph,
                                       max_length=400, required=False,
                                       default="—")
    motto = discord.ui.TextInput(label="Девиз", max_length=100, required=False,
                                 placeholder="Например: Служим Отечеству")
    color = discord.ui.TextInput(label="HEX-цвет", max_length=7, required=False,
                                 default="#1e3a8a")

    def __init__(self, bot, leader: discord.Member, type_: str, category: str):
        super().__init__()
        self.bot = bot
        self.leader = leader
        self.type_ = type_
        self.category = category

    async def on_submit(self, interaction: discord.Interaction):
        color = (self.color.value or "#1e3a8a").strip()
        if not color.startswith("#") or len(color) not in (4, 7):
            color = "#1e3a8a"

        if await db.get_org(self.name.value.strip()):
            return await interaction.response.send_message(
                "❌ Организация с таким названием уже есть.", ephemeral=True
            )

        oid = await db.create_org(
            name=self.name.value.strip(),
            leader_id=self.leader.id,
            type_=self.type_,
            category=self.category,
            description=self.description.value.strip() or "—",
            motto=(self.motto.value or "—").strip() or "—",
            color=color,
            short_name=(self.short.value or "").strip() or None,
            created_by=interaction.user.id,
        )

        embed = discord.Embed(
            title="✅ Организация создана",
            description=f"**{self.name.value}** (#{oid})\n"
                        f"Тип: {TYPE_LABEL[self.type_]}\n"
                        f"Категория: {CAT_LABEL[self.category]}\n"
                        f"Лидер: {self.leader.mention}",
            color=discord.Color.from_str(color),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        # Пингануть в ЛС лидера
        try:
            await self.leader.send(
                f"🏛️ Вас назначили лидером организации **{self.name.value}**! "
                f"Используйте `/org panel` для управления."
            )
        except Exception:
            pass


# ============================================================
# МОДАЛЬНОЕ ОКНО РЕДАКТИРОВАНИЯ
# ============================================================
class EditOrgModal(discord.ui.Modal, title="Изменение организации"):
    name = discord.ui.TextInput(label="Название", max_length=60, required=False)
    short = discord.ui.TextInput(label="Короткое название", max_length=12, required=False)
    description = discord.ui.TextInput(label="Описание", style=discord.TextStyle.paragraph,
                                       max_length=400, required=False)
    motto = discord.ui.TextInput(label="Девиз", max_length=100, required=False)
    color = discord.ui.TextInput(label="HEX-цвет", max_length=7, required=False)

    def __init__(self, org):
        super().__init__()
        self.org = org
        self.name.default = org["name"]
        self.short.default = org["short_name"] or ""
        self.description.default = org["description"] or "—"
        self.motto.default = org["motto"] or "—"
        self.color.default = org["color"] or "#1e3a8a"

    async def on_submit(self, interaction: discord.Interaction):
        fields = {}
        if self.name.value and self.name.value.strip() != self.org["name"]:
            fields["name"] = self.name.value.strip()
        if self.short.value is not None:
            fields["short_name"] = self.short.value.strip() or None
        if self.description.value is not None:
            fields["description"] = self.description.value.strip() or "—"
        if self.motto.value is not None:
            fields["motto"] = self.motto.value.strip() or "—"
        color = (self.color.value or "").strip()
        if color.startswith("#") and len(color) in (4, 7):
            fields["color"] = color

        if fields:
            await db.update_org(self.org["org_id"], **fields)
        await interaction.response.send_message("✅ Организация обновлена.", ephemeral=True)


# ============================================================
# МОДАЛЬНОЕ ОКНО ЗАЯВКИ
# ============================================================
class ApplyModal(discord.ui.Modal, title="Заявка на вступление"):
    message = discord.ui.TextInput(
        label="Сопроводительное сообщение",
        style=discord.TextStyle.paragraph,
        max_length=400, required=True,
        placeholder="Почему вы хотите вступить? Чем можете быть полезны?",
    )

    def __init__(self, bot, org):
        super().__init__()
        self.bot = bot
        self.org = org

    async def on_submit(self, interaction: discord.Interaction):
        if await db.get_user_org(interaction.user.id):
            return await interaction.response.send_message(
                "❌ Вы уже состоите в организации.", ephemeral=True
            )
        await db.create_org_request(self.org["org_id"], interaction.user.id, self.message.value)
        await interaction.response.send_message(
            "✅ Заявка отправлена. Ожидайте решения лидера.", ephemeral=True
        )
        # Оповестим лидера
        leader = interaction.guild.get_member(self.org["leader_id"])
        if leader:
            try:
                await leader.send(
                    f"📩 Новая заявка в **{self.org['name']}** от {interaction.user.mention}.\n"
                    f"Проверить: `/org panel`"
                )
            except Exception:
                pass


# ============================================================
# ПАНЕЛЬ УПРАВЛЕНИЯ — View с кнопками
# ============================================================
class OrgPanelView(discord.ui.View):
    def __init__(self, bot, org, is_leader: bool):
        super().__init__(timeout=300)
        self.bot = bot
        self.org = org
        self.is_leader = is_leader

        if not is_leader:
            # Обычный участник — только просмотр
            self.remove_item(self.requests_btn)
            self.remove_item(self.manage_btn)
            self.remove_item(self.edit_btn)
            self.remove_item(self.budget_btn)

    async def _check_leader(self, interaction: discord.Interaction) -> bool:
        org = await db.get_org(self.org["org_id"])
        if not (interaction.user.id == org["leader_id"]
                or interaction.user.guild_permissions.administrator):
            await interaction.response.send_message("❌ Только лидер.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="👥 Участники", style=discord.ButtonStyle.primary, row=0)
    async def members_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        rows = await db.get_org_members(self.org["org_id"])
        lines = []
        for m in rows:
            user = interaction.guild.get_member(m["user_id"])
            name = user.mention if user else f"ID {m['user_id']}"
            role = ROLE_LABEL.get(m["role"], m["role"])
            sal = f" · 💰{m['salary']:,}" if m["salary"] else ""
            lines.append(f"{role} — {name}{sal}")
        embed = discord.Embed(
            title=f"👥 Состав — {self.org['name']}",
            description="\n".join(lines) or "Пусто",
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="📩 Заявки", style=discord.ButtonStyle.success, row=0)
    async def requests_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_leader(interaction):
            return
        reqs = await db.get_org_requests(self.org["org_id"])
        if not reqs:
            return await interaction.response.send_message("📭 Заявок нет.", ephemeral=True)

        # Показываем первую заявку с кнопками
        await self._show_request(interaction, reqs[0], 0)

    async def _show_request(self, interaction, req, idx):
        user = interaction.guild.get_member(req["user_id"])
        uname = user.mention if user else f"ID {req['user_id']}"
        embed = discord.Embed(
            title=f"📩 Заявка #{req['request_id']}",
            description=f"**От:** {uname}\n**Сообщение:**\n{req['message']}",
            color=discord.Color.gold(),
        )
        view = RequestActionView(self.bot, self.org, req)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="💰 Бюджет", style=discord.ButtonStyle.secondary, row=0)
    async def budget_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_leader(interaction):
            return
        org = await db.get_org(self.org["org_id"])
        history = await db.get_org_history(org["org_id"], 10)
        lines = []
        for h in history:
            sign = "+" if h["amount"] >= 0 else ""
            lines.append(f"`{sign}{h['amount']:,}` — {h['kind']} {('(' + h['comment'] + ')') if h['comment'] else ''}")

        embed = discord.Embed(
            title=f"💰 Бюджет — {org['name']}",
            description=f"**Текущий баланс:** `{org['budget']:,}` монет",
            color=discord.Color.green(),
        )
        if lines:
            embed.add_field(name="История", value="\n".join(lines), inline=False)
        view = BudgetActionsView(self.bot, org)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="⚙️ Управление", style=discord.ButtonStyle.secondary, row=1)
    async def manage_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_leader(interaction):
            return
        embed = discord.Embed(
            title=f"⚙️ Управление — {self.org['name']}",
            description="Выберите действие:",
            color=discord.Color.dark_gray(),
        )
        view = ManageActionsView(self.bot, self.org)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="✏️ Редактировать", style=discord.ButtonStyle.secondary, row=1)
    async def edit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_leader(interaction):
            return
        org = await db.get_org(self.org["org_id"])
        await interaction.response.send_modal(EditOrgModal(org))

    @discord.ui.button(label="🖼️ Карточка", style=discord.ButtonStyle.success, row=1)
    async def card_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True)
        data = await _build_org_card_data(self.bot, interaction.guild, self.org["org_id"])
        try:
            img = await organization_image.render_organization_card(data)
        except Exception as e:
            return await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)
        await interaction.followup.send(
            file=discord.File(fp=io.BytesIO(img), filename=f"org_{self.org['org_id']}.png")
        )


# ============================================================
# ACTION VIEWS
# ============================================================
class RequestActionView(discord.ui.View):
    def __init__(self, bot, org, req):
        super().__init__(timeout=180)
        self.bot = bot
        self.org = org
        self.req = req

    @discord.ui.button(label="✅ Принять", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not (interaction.user.id == self.org["leader_id"]
                or interaction.user.guild_permissions.administrator):
            return await interaction.response.send_message("❌ Только лидер.", ephemeral=True)

        if await db.get_user_org(self.req["user_id"]):
            await db.set_org_request_status(self.req["request_id"], "rejected")
            return await interaction.response.send_message("⚠️ Игрок уже в организации.", ephemeral=True)

        await db.add_org_member(self.req["user_id"], self.org["org_id"], role="member")
        await db.set_org_request_status(self.req["request_id"], "accepted")

        await interaction.response.send_message(
            f"✅ <@{self.req['user_id']}> принят в организацию.", ephemeral=True
        )
        member = interaction.guild.get_member(self.req["user_id"])
        if member:
            try:
                await member.send(f"🎉 Вы приняты в **{self.org['name']}**!")
            except Exception:
                pass
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

    @discord.ui.button(label="❌ Отклонить", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not (interaction.user.id == self.org["leader_id"]
                or interaction.user.guild_permissions.administrator):
            return await interaction.response.send_message("❌ Только лидер.", ephemeral=True)
        await db.set_org_request_status(self.req["request_id"], "rejected")
        await interaction.response.send_message("❌ Заявка отклонена.", ephemeral=True)
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass


class BudgetActionsView(discord.ui.View):
    def __init__(self, bot, org):
        super().__init__(timeout=180)
        self.bot = bot
        self.org = org

    @discord.ui.button(label="➕ Внести", style=discord.ButtonStyle.success)
    async def add_money(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BudgetAddModal(self.org))

    @discord.ui.button(label="💸 Снять лидеру", style=discord.ButtonStyle.danger)
    async def take_money(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.org["leader_id"] and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Только лидер.", ephemeral=True)
        await interaction.response.send_modal(BudgetTakeModal(self.org))


class BudgetAddModal(discord.ui.Modal, title="Пополнить бюджет"):
    amount = discord.ui.TextInput(label="Сумма", placeholder="1000", required=True)

    def __init__(self, org):
        super().__init__()
        self.org = org

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt = int(self.amount.value)
        except ValueError:
            return await interaction.response.send_message("❌ Число.", ephemeral=True)
        if amt <= 0:
            return await interaction.response.send_message("❌ Должно быть > 0.", ephemeral=True)
        user = await db.get_user(interaction.user.id)
        if user["wallet"] < amt:
            return await interaction.response.send_message("❌ Недостаточно монет.", ephemeral=True)
        await db.add_balance(interaction.user.id, -amt)
        await db.add_org_budget(self.org["org_id"], amt, "deposit", interaction.user.id, "Личный вклад")
        await interaction.response.send_message(
            f"💰 Внесено `{amt:,}` монет в бюджет **{self.org['name']}**.", ephemeral=True
        )


class BudgetTakeModal(discord.ui.Modal, title="Снять из бюджета"):
    amount = discord.ui.TextInput(label="Сумма", required=True)
    comment = discord.ui.TextInput(label="Комментарий", required=False, max_length=100)

    def __init__(self, org):
        super().__init__()
        self.org = org

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt = int(self.amount.value)
        except ValueError:
            return await interaction.response.send_message("❌ Число.", ephemeral=True)
        org = await db.get_org(self.org["org_id"])
        if amt <= 0 or org["budget"] < amt:
            return await interaction.response.send_message("❌ Недостаточно в бюджете.", ephemeral=True)
        await db.add_org_budget(org["org_id"], -amt, "withdraw", interaction.user.id,
                                self.comment.value or "Снятие лидером")
        await db.add_balance(interaction.user.id, amt)
        await interaction.response.send_message(
            f"💸 Снято `{amt:,}` монет из бюджета.", ephemeral=True
        )


class ManageActionsView(discord.ui.View):
    def __init__(self, bot, org):
        super().__init__(timeout=180)
        self.bot = bot
        self.org = org

    @discord.ui.button(label="👑 Назначить лидера", style=discord.ButtonStyle.primary)
    async def set_leader(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Введите команду: `/org setleader <название> @пользователь`", ephemeral=True
        )

    @discord.ui.button(label="🎖️ Офицер", style=discord.ButtonStyle.secondary)
    async def promote(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Введите команду: `/org promote @пользователь` (в ЛС панели)", ephemeral=True
        )

    @discord.ui.button(label="🔊 Объявление", style=discord.ButtonStyle.success)
    async def broadcast(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BroadcastModal(self.org))

    @discord.ui.button(label="🎨 Логотип", style=discord.ButtonStyle.secondary)
    async def setlogo(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Пришлите изображение командой `/org setlogo` (прикрепите файл).", ephemeral=True
        )


class BroadcastModal(discord.ui.Modal, title="Объявление"):
    text = discord.ui.TextInput(
        label="Текст", style=discord.TextStyle.paragraph,
        max_length=800, required=True,
    )

    def __init__(self, org):
        super().__init__()
        self.org = org

    async def on_submit(self, interaction: discord.Interaction):
        rows = await db.get_org_members(self.org["org_id"])
        sent = failed = 0
        for m in rows:
            member = interaction.guild.get_member(m["user_id"])
            if not member or member.bot:
                failed += 1
                continue
            try:
                embed = discord.Embed(
                    title=f"📢 {self.org['name']}",
                    description=self.text.value,
                    color=discord.Color.from_str(self.org["color"]),
                )
                embed.set_footer(text=f"От: {interaction.user.display_name}")
                await member.send(embed=embed)
                sent += 1
            except Exception:
                failed += 1
        await interaction.response.send_message(
            f"📨 Доставлено: {sent}, не доставлено: {failed}.", ephemeral=True
        )


# ============================================================
# COG
# ============================================================
class Organizations(commands.Cog):
    """Система организаций, министерств и компаний."""

    def __init__(self, bot):
        self.bot = bot

    org = app_commands.Group(name="org", description="Организации, министерства, компании")

    # ------- CREATE (через модальное окно) -------
    @org.command(name="create", description="[ADMIN] Создать организацию")
    @app_commands.describe(leader="Лидер", type="Тип", category="Категория")
    @app_commands.choices(
        type=[
            app_commands.Choice(name="Государственная", value="government"),
            app_commands.Choice(name="Частная", value="private"),
        ],
        category=[
            app_commands.Choice(name="Министерство", value="ministry"),
            app_commands.Choice(name="Организация", value="organization"),
            app_commands.Choice(name="Компания", value="company"),
            app_commands.Choice(name="Другое", value="other"),
        ],
    )
    async def create(self, interaction: discord.Interaction, leader: discord.Member,
                     type: app_commands.Choice[str], category: app_commands.Choice[str]):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Только администратор.", ephemeral=True)
        await interaction.response.send_modal(
            CreateOrgModal(self.bot, leader, type.value, category.value)
        )

    @org.command(name="delete", description="[ADMIN] Удалить организацию")
    async def delete(self, interaction: discord.Interaction, name: str):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Только администратор.", ephemeral=True)
        o = await db.get_org(name)
        if not o:
            return await interaction.response.send_message("❌ Не найдено.", ephemeral=True)
        await db.delete_org(o["org_id"])
        await interaction.response.send_message(f"🗑️ Организация **{o['name']}** удалена.", ephemeral=True)

    @org.command(name="setleader", description="[ADMIN] Назначить лидера")
    async def setleader(self, interaction: discord.Interaction, name: str, leader: discord.Member):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Только администратор.", ephemeral=True)
        o = await db.get_org(name)
        if not o:
            return await interaction.response.send_message("❌ Не найдено.", ephemeral=True)
        await db.remove_org_member(o["leader_id"], o["org_id"])
        await db.update_org(o["org_id"], leader_id=leader.id)
        await db.add_org_member(leader.id, o["org_id"], role="leader")
        await interaction.response.send_message(f"👑 Новый лидер **{o['name']}** — {leader.mention}.", ephemeral=True)

    @org.command(name="setbudget", description="[ADMIN] Установить бюджет")
    async def setbudget(self, interaction: discord.Interaction, name: str, amount: int):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Только администратор.", ephemeral=True)
        o = await db.get_org(name)
        if not o:
            return await interaction.response.send_message("❌ Не найдено.", ephemeral=True)
        delta = amount - o["budget"]
        await db.add_org_budget(o["org_id"], delta, "admin_set", interaction.user.id, "Установлено админом")
        await interaction.response.send_message(
            f"💰 Бюджет **{o['name']}** = `{amount:,}` монет.", ephemeral=True
        )

    @org.command(name="addbudget", description="[ADMIN] Добавить/снять из бюджета")
    async def addbudget(self, interaction: discord.Interaction, name: str, amount: int):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Только администратор.", ephemeral=True)
        o = await db.get_org(name)
        if not o:
            return await interaction.response.send_message("❌ Не найдено.", ephemeral=True)
        await db.add_org_budget(o["org_id"], amount, "admin_adjust", interaction.user.id, "Корректировка")
        await interaction.response.send_message(
            f"💰 Бюджет **{o['name']}** изменён на `{amount:+,}`.", ephemeral=True
        )

    @org.command(name="edit", description="[ADMIN/Лидер] Редактировать организацию")
    async def edit(self, interaction: discord.Interaction, name: str):
        o = await db.get_org(name)
        if not o:
            return await interaction.response.send_message("❌ Не найдено.", ephemeral=True)
        if not (interaction.user.id == o["leader_id"]
                or interaction.user.guild_permissions.administrator):
            return await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
        await interaction.response.send_modal(EditOrgModal(o))

    @org.command(name="setlogo", description="[Лидер] Загрузить логотип")
    async def setlogo(self, interaction: discord.Interaction, name: str,
                      file: discord.Attachment, mode: str = "emblem"):
        o = await db.get_org(name)
        if not o:
            return await interaction.response.send_message("❌ Не найдено.", ephemeral=True)
        if not (interaction.user.id == o["leader_id"]
                or interaction.user.guild_permissions.administrator):
            return await interaction.response.send_message("❌ Нет прав.", ephemeral=True)
        if not file.content_type or not file.content_type.startswith("image/"):
            return await interaction.response.send_message("❌ Нужно изображение.", ephemeral=True)
        content = await file.read()
        url = await storage.upload(content, file.filename, file.content_type or "image/png")
        await db.update_org(o["org_id"], logo_file=url, logo_mode=mode)
        await interaction.response.send_message("✅ Логотип обновлён.", ephemeral=True)

    # ------- VIEW -------
    @org.command(name="list", description="Список организаций")
    @app_commands.choices(
        category=[
            app_commands.Choice(name="Все", value="all"),
            app_commands.Choice(name="Министерства", value="ministry"),
            app_commands.Choice(name="Организации", value="organization"),
            app_commands.Choice(name="Компании", value="company"),
        ],
    )
    async def list_orgs(self, interaction: discord.Interaction,
                        category: app_commands.Choice[str] = None):
        cat = category.value if category and category.value != "all" else None
        rows = await db.all_orgs(category=cat)
        if not rows:
            return await interaction.response.send_message("Пусто.", ephemeral=True)

        embed = discord.Embed(title="🏛️ Организации", color=discord.Color.blurple())
        for o in rows:
            count = await db.count_org_members(o["org_id"])
            type_l = TYPE_LABEL.get(o["type"], o["type"])
            cat_l = CAT_LABEL.get(o["category"], o["category"])
            leader = interaction.guild.get_member(o["leader_id"])
            lname = leader.display_name if leader else "—"
            embed.add_field(
                name=f"{o['name']} (#{o['org_id']})",
                value=f"{type_l} · {cat_l}\n"
                      f"Лидер: **{lname}** · Участников: {count}\n"
                      f"Бюджет: `{o['budget']:,}` монет",
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    @org.command(name="info", description="Информация об организации")
    async def info(self, interaction: discord.Interaction, name: str = None):
        if name:
            o = await db.get_org(name)
        else:
            o = await db.get_user_org(interaction.user.id)
            if o:
                o = await db.get_org(o["org_id"])
            else:
                return await interaction.response.send_message("❌ Не найдено.", ephemeral=True)
        if not o:
            return await interaction.response.send_message("❌ Не найдено.", ephemeral=True)

        count = await db.count_org_members(o["org_id"])
        leader = interaction.guild.get_member(o["leader_id"])
        try:
            color = discord.Color.from_str(o["color"])
        except Exception:
            color = discord.Color.blurple()

        embed = discord.Embed(title=f"🏛️ {o['name']}", description=o["description"], color=color)
        if o["short_name"]:
            embed.add_field(name="Сокращение", value=o["short_name"], inline=True)
        embed.add_field(name="Тип", value=TYPE_LABEL.get(o["type"], o["type"]), inline=True)
        embed.add_field(name="Категория", value=CAT_LABEL.get(o["category"], o["category"]), inline=True)
        embed.add_field(name="Лидер", value=leader.mention if leader else "—", inline=True)
        embed.add_field(name="Участников", value=str(count), inline=True)
        embed.add_field(name="Бюджет", value=f"`{o['budget']:,}` монет", inline=True)
        if o["motto"] and o["motto"] != "—":
            embed.add_field(name="Девиз", value=f"«{o['motto']}»", inline=False)

        logo_url = storage.url(o["logo_file"])
        if logo_url:
            embed.set_thumbnail(url=logo_url)
        await interaction.response.send_message(embed=embed)

    # ------- PANEL -------
    @org.command(name="panel", description="Панель управления организацией")
    async def panel(self, interaction: discord.Interaction, name: str = None):
        if name:
            o = await db.get_org(name)
        else:
            o = await db.get_user_org(interaction.user.id)
            if o:
                o = await db.get_org(o["org_id"])
            else:
                return await interaction.response.send_message(
                    "❌ Вы не в организации. Укажите название.", ephemeral=True
                )
        if not o:
            return await interaction.response.send_message("❌ Не найдено.", ephemeral=True)

        is_leader = (interaction.user.id == o["leader_id"]
                     or interaction.user.guild_permissions.administrator)
        count = await db.count_org_members(o["org_id"])
        try:
            color = discord.Color.from_str(o["color"])
        except Exception:
            color = discord.Color.blurple()

        embed = discord.Embed(
            title=f"🛠️ Панель — {o['name']}",
            description=o["description"],
            color=color,
        )
        embed.add_field(name="Тип", value=TYPE_LABEL.get(o["type"], o["type"]), inline=True)
        embed.add_field(name="Категория", value=CAT_LABEL.get(o["category"], o["category"]), inline=True)
        embed.add_field(name="Участников", value=str(count), inline=True)
        embed.add_field(name="Бюджет", value=f"`{o['budget']:,}` монет", inline=True)
        embed.set_footer(text="Лидер/админ видят больше кнопок" if is_leader else "Просмотр")

        view = OrgPanelView(self.bot, o, is_leader)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ------- MEMBERS -------
    @org.command(name="invite", description="[Лидер] Пригласить игрока")
    async def invite(self, interaction: discord.Interaction, member: discord.Member):
        o = await db.get_user_org(interaction.user.id)
        if not o:
            return await interaction.response.send_message("❌ Вы не в организации.", ephemeral=True)
        if not (interaction.user.id == o["leader_id"]
                or interaction.user.guild_permissions.administrator
                or (await db.get_user_org(interaction.user.id))["role"] == "officer"):
            return await interaction.response.send_message("❌ Только лидер или офицер.", ephemeral=True)
        if await db.get_user_org(member.id):
            return await interaction.response.send_message("❌ Игрок уже в организации.", ephemeral=True)
        await db.add_org_member(member.id, o["org_id"], role="member")
        await interaction.response.send_message(f"✅ {member.mention} принят.", ephemeral=True)
        try:
            await member.send(f"🎉 Вы приняты в **{o['name']}**!")
        except Exception:
            pass

    @org.command(name="kick", description="[Лидер] Исключить участника")
    async def kick(self, interaction: discord.Interaction, member: discord.Member):
        o = await db.get_user_org(interaction.user.id)
        if not o or not (interaction.user.id == o["leader_id"]
                         or interaction.user.guild_permissions.administrator):
            return await interaction.response.send_message("❌ Только лидер.", ephemeral=True)
        if member.id == o["leader_id"]:
            return await interaction.response.send_message("❌ Нельзя исключить лидера.", ephemeral=True)
        await db.remove_org_member(member.id, o["org_id"])
        await interaction.response.send_message(f"👋 {member.mention} исключён.", ephemeral=True)

    @org.command(name="promote", description="[Лидер] Повысить до офицера")
    async def promote(self, interaction: discord.Interaction, member: discord.Member):
        o = await db.get_user_org(interaction.user.id)
        if not o or not (interaction.user.id == o["leader_id"]
                         or interaction.user.guild_permissions.administrator):
            return await interaction.response.send_message("❌ Только лидер.", ephemeral=True)
        await db.update_org_member(member.id, o["org_id"], role="officer")
        await interaction.response.send_message(f"🎖️ {member.mention} повышен.", ephemeral=True)

    @org.command(name="demote", description="[Лидер] Понизить до участника")
    async def demote(self, interaction: discord.Interaction, member: discord.Member):
        o = await db.get_user_org(interaction.user.id)
        if not o or not (interaction.user.id == o["leader_id"]
                         or interaction.user.guild_permissions.administrator):
            return await interaction.response.send_message("❌ Только лидер.", ephemeral=True)
        await db.update_org_member(member.id, o["org_id"], role="member")
        await interaction.response.send_message(f"👤 {member.mention} понижен.", ephemeral=True)

    @org.command(name="leave", description="Покинуть организацию")
    async def leave(self, interaction: discord.Interaction):
        o = await db.get_user_org(interaction.user.id)
        if not o:
            return await interaction.response.send_message("❌ Вы не в организации.", ephemeral=True)
        if o["role"] == "leader":
            return await interaction.response.send_message("❌ Лидер не может покинуть.", ephemeral=True)
        await db.remove_org_member(interaction.user.id, o["org_id"])
        await interaction.response.send_message(f"👋 Вы покинули **{o['name']}**.", ephemeral=True)

    # ------- APPLY -------
    @org.command(name="apply", description="Подать заявку на вступление")
    async def apply(self, interaction: discord.Interaction, name: str):
        o = await db.get_org(name)
        if not o:
            return await interaction.response.send_message("❌ Не найдено.", ephemeral=True)
        if not o["is_open"]:
            return await interaction.response.send_message("❌ Набор закрыт.", ephemeral=True)
        if await db.get_user_org(interaction.user.id):
            return await interaction.response.send_message("❌ Вы уже в организации.", ephemeral=True)
        await interaction.response.send_modal(ApplyModal(self.bot, o))

    # ------- CARD -------
    @org.command(name="card", description="Красивая карточка организации")
    async def card(self, interaction: discord.Interaction, name: str = None):
        if name:
            o = await db.get_org(name)
        else:
            o = await db.get_user_org(interaction.user.id)
            if o:
                o = await db.get_org(o["org_id"])
        if not o:
            return await interaction.response.send_message("❌ Не найдено.", ephemeral=True)
        await interaction.response.defer(thinking=True)
        data = await _build_org_card_data(self.bot, interaction.guild, o["org_id"])
        try:
            img = await organization_image.render_organization_card(data)
        except Exception as e:
            return await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)
        await interaction.followup.send(
            file=discord.File(fp=io.BytesIO(img), filename=f"org_{o['org_id']}.png")
        )

    # ------- TOP -------
    @org.command(name="top", description="Топ организаций по бюджету")
    async def top(self, interaction: discord.Interaction):
        rows = await db.all_orgs()
        if not rows:
            return await interaction.response.send_message("Пусто.", ephemeral=True)
        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, o in enumerate(rows[:10]):
            prefix = medals[i] if i < 3 else f"`{i+1}.`"
            lines.append(f"{prefix} **{o['name']}** — `{o['budget']:,}` монет")
        embed = discord.Embed(title="🏆 Топ организаций", description="\n".join(lines),
                              color=discord.Color.gold())
        await interaction.response.send_message(embed=embed)


# ============================================================
# ФУНКЦИЯ СБОРА ДАННЫХ ДЛЯ КАРТОЧКИ
# ============================================================
async def _build_org_card_data(bot, guild, org_id):
    o = await db.get_org(org_id)
    count = await db.count_org_members(org_id)
    leader = guild.get_member(o["leader_id"]) if guild else None
    leader_name = leader.display_name if leader else f"ID {o['leader_id']}"
    leader_avatar = leader.display_avatar.url if leader else None

    logo_data = storage.url(o["logo_file"])

    return {
        "org_id": o["org_id"],
        "name": o["name"],
        "short_name": o["short_name"] or "",
        "type": o["type"],
        "category": o["category"],
        "description": o["description"],
        "motto": o["motto"],
        "color": o["color"],
        "budget": int(o["budget"]),
        "members_count": int(count),
        "leader_name": leader_name,
        "leader_avatar": leader_avatar,
        "logo": logo_data,
        "logoMode": o["logo_mode"] or "emblem",
        "created_text": time.strftime("%d.%m.%Y", time.localtime(o["created_at"])) if o["created_at"] else "",
    }


async def setup(bot):
    await bot.add_cog(Organizations(bot))