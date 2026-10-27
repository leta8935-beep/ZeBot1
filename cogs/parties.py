import time
import discord
from discord import app_commands
from discord.ext import commands
from pathlib import Path
from storage import storage

from database import db



class Parties(commands.Cog):
    """Система политических партий."""

    def __init__(self, bot):
        self.bot = bot

    party = app_commands.Group(name="party", description="Политические партии")

    # ========== ADMIN ==========

    @party.command(name="create", description="[ADMIN] Создать партию")
    @app_commands.describe(name="Название", leader="Лидер (игрок)", ideology="Идеология",
                           color="HEX-цвет (например #1e3a8a)", description="Описание")
    async def create(self, interaction: discord.Interaction, name: str,
                     leader: discord.Member, ideology: str = "Не указана",
                     color: str = "#1e3a8a", description: str = "—"):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Только администратор.", ephemeral=True)
        if await db.get_party(name):
            return await interaction.response.send_message("❌ Партия с таким названием уже существует.", ephemeral=True)
        if not color.startswith("#") or len(color) not in (4, 7):
            color = "#1e3a8a"
        pid = await db.create_party(name, leader.id, ideology, color, description)
        await interaction.response.send_message(
            f"✅ Партия **{name}** (#{pid}) создана. Лидер — {leader.mention}.", ephemeral=True
        )

    @party.command(name="delete", description="[ADMIN] Удалить партию")
    async def delete(self, interaction: discord.Interaction, name: str):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Только администратор.", ephemeral=True)
        p = await db.get_party(name)
        if not p:
            return await interaction.response.send_message("❌ Партия не найдена.", ephemeral=True)
        await db.delete_party(p["party_id"])
        await interaction.response.send_message(f"🗑️ Партия **{name}** удалена.", ephemeral=True)

    @party.command(name="setleader", description="[ADMIN] Сменить лидера партии")
    async def setleader(self, interaction: discord.Interaction, name: str, leader: discord.Member):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Только администратор.", ephemeral=True)
        p = await db.get_party(name)
        if not p:
            return await interaction.response.send_message("❌ Партия не найдена.", ephemeral=True)
        await db.remove_party_member(p["leader_id"], p["party_id"])
        await db.update_party(p["party_id"], leader_id=leader.id)
        await db.add_party_member(leader.id, p["party_id"], role="leader")
        await interaction.response.send_message(
            f"👑 Лидер партии **{name}** — теперь {leader.mention}.", ephemeral=True
        )

    @party.command(name="edit", description="[ADMIN] Изменить поле партии")
    @app_commands.describe(field="Поле: ideology, color, description, slogan, flag_mode",
                           value="Новое значение")
    async def edit(self, interaction: discord.Interaction, name: str, field: str, value: str):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Только администратор.", ephemeral=True)
        if field not in ("ideology", "color", "description", "slogan", "flag_mode"):
            return await interaction.response.send_message("❌ Недопустимое поле.", ephemeral=True)
        p = await db.get_party(name)
        if not p:
            return await interaction.response.send_message("❌ Партия не найдена.", ephemeral=True)
        await db.update_party(p["party_id"], **{field: value})
        await interaction.response.send_message(f"✏️ Поле **{field}** обновлено.", ephemeral=True)

    # ========== ВСЕ ==========

    @party.command(name="list", description="Список всех партий")
    async def list_parties(self, interaction: discord.Interaction):
        rows = await db.all_parties()
        if not rows:
            return await interaction.response.send_message("Партий пока нет.", ephemeral=True)
        embed = discord.Embed(title="🏛️ Политические партии", color=discord.Color.blurple())
        for p in rows:
            leader = interaction.guild.get_member(p["leader_id"])
            lname = leader.display_name if leader else f"ID {p['leader_id']}"
            embed.add_field(
                name=f"{p['name']} (#{p['party_id']})",
                value=f"**Лидер:** {lname}\n**Идеология:** {p['ideology']}\n**Казна:** `{p['treasury']:,}` монет",
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    @party.command(name="info", description="Информация о партии")
    async def info(self, interaction: discord.Interaction, name: str = None):
        if name:
            p = await db.get_party(name)
        else:
            p = await db.get_user_party(interaction.user.id)
            if not p:
                return await interaction.response.send_message("❌ Вы не состоите в партии.", ephemeral=True)
        if not p:
            return await interaction.response.send_message("❌ Партия не найдена.", ephemeral=True)

        members = await db.get_party_members(p["party_id"])
        leader = interaction.guild.get_member(p["leader_id"])
        try:
            color = discord.Color.from_str(p["color"])
        except Exception:
            color = discord.Color.blurple()

        embed = discord.Embed(title=f"🏛️ {p['name']}", description=p["description"], color=color)
        embed.add_field(name="Идеология", value=p["ideology"], inline=True)
        embed.add_field(name="Слоган", value=p["slogan"], inline=True)
        embed.add_field(name="Лидер", value=leader.mention if leader else "—", inline=True)
        embed.add_field(name="Участников", value=str(len(members)), inline=True)
        embed.add_field(name="Казна", value=f"`{p['treasury']:,}` монет", inline=True)
        flag_url = storage.url(p["flag_file"])
        if flag_url:
            embed.set_thumbnail(url=flag_url)
        await interaction.response.send_message(embed=embed)

    @party.command(name="members", description="Состав партии")
    async def members(self, interaction: discord.Interaction, name: str = None):
        if name:
            p = await db.get_party(name)
        else:
            p = await db.get_user_party(interaction.user.id)
        if not p:
            return await interaction.response.send_message("❌ Партия не найдена.", ephemeral=True)
        rows = await db.get_party_members(p["party_id"])
        lines = []
        for m in rows:
            user = interaction.guild.get_member(m["user_id"])
            name_str = user.mention if user else f"ID {m['user_id']}"
            role = "👑 Лидер" if m["role"] == "leader" else "🎖️ Офицер" if m["role"] == "officer" else "👤 Участник"
            lines.append(f"{role} — {name_str}")
        embed = discord.Embed(
            title=f"Участники партии «{p['name']}»",
            description="\n".join(lines) or "Пусто",
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed)

    # ========== ЛИДЕР / УЧАСТНИК ==========

    def _is_leader_or_admin(interaction, party):
        return (interaction.user.id == party["leader_id"]
                or interaction.user.guild_permissions.administrator)

    @party.command(name="setflag", description="[Лидер] Загрузить флаг/эмблему партии")
    async def setflag(self, interaction: discord.Interaction, file: discord.Attachment,
                      mode: str = "flag"):
        p = await db.get_user_party(interaction.user.id)
        if not p or not self._is_leader_or_admin(interaction, p):
            return await interaction.response.send_message("❌ Только лидер партии.", ephemeral=True)
        if mode not in ("flag", "emblem"):
            mode = "flag"
        if not file.content_type or not file.content_type.startswith("image/"):
            return await interaction.response.send_message("❌ Нужно изображение.", ephemeral=True)
        content = await file.read()
        url = await storage.upload(content, file.filename, file.content_type or "image/png")
        await db.update_party(p["party_id"], flag_file=url, flag_mode=mode)
        await interaction.response.send_message("✅ Флаг обновлён.", ephemeral=True)

    @party.command(name="setcolor", description="[Лидер] Установить цвет партии")
    async def setcolor(self, interaction: discord.Interaction, color: str):
        p = await db.get_user_party(interaction.user.id)
        if not p or not self._is_leader_or_admin(interaction, p):
            return await interaction.response.send_message("❌ Только лидер партии.", ephemeral=True)
        if not color.startswith("#") or len(color) not in (4, 7):
            return await interaction.response.send_message("❌ Формат: #RRGGBB", ephemeral=True)
        await db.update_party(p["party_id"], color=color)
        await interaction.response.send_message(f"🎨 Цвет обновлён: `{color}`", ephemeral=True)

    @party.command(name="setideology", description="[Лидер] Идеология партии")
    async def setideology(self, interaction: discord.Interaction, text: str):
        p = await db.get_user_party(interaction.user.id)
        if not p or not self._is_leader_or_admin(interaction, p):
            return await interaction.response.send_message("❌ Только лидер.", ephemeral=True)
        await db.update_party(p["party_id"], ideology=text)
        await interaction.response.send_message("✅ Обновлено.", ephemeral=True)

    @party.command(name="setdescription", description="[Лидер] Описание партии")
    async def setdescription(self, interaction: discord.Interaction, text: str):
        p = await db.get_user_party(interaction.user.id)
        if not p or not self._is_leader_or_admin(interaction, p):
            return await interaction.response.send_message("❌ Только лидер.", ephemeral=True)
        await db.update_party(p["party_id"], description=text)
        await interaction.response.send_message("✅ Обновлено.", ephemeral=True)

    @party.command(name="setslogan", description="[Лидер] Слоган партии")
    async def setslogan(self, interaction: discord.Interaction, text: str):
        p = await db.get_user_party(interaction.user.id)
        if not p or not self._is_leader_or_admin(interaction, p):
            return await interaction.response.send_message("❌ Только лидер.", ephemeral=True)
        await db.update_party(p["party_id"], slogan=text)
        await interaction.response.send_message("✅ Обновлено.", ephemeral=True)

    @party.command(name="invite", description="[Лидер] Пригласить игрока в партию")
    async def invite(self, interaction: discord.Interaction, member: discord.Member):
        p = await db.get_user_party(interaction.user.id)
        if not p or not self._is_leader_or_admin(interaction, p):
            return await interaction.response.send_message("❌ Только лидер.", ephemeral=True)
        if await db.get_user_party(member.id):
            return await interaction.response.send_message("❌ Игрок уже в партии.", ephemeral=True)
        await db.add_party_member(member.id, p["party_id"], role="member")
        await interaction.response.send_message(
            f"✅ {member.mention} принят в партию **{p['name']}**.", ephemeral=True
        )
        try:
            await member.send(f"🏛️ Вас приняли в партию **{p['name']}**! Лидер — {interaction.user.mention}.")
        except Exception:
            pass

    @party.command(name="kick", description="[Лидер] Исключить из партии")
    async def kick(self, interaction: discord.Interaction, member: discord.Member):
        p = await db.get_user_party(interaction.user.id)
        if not p or not self._is_leader_or_admin(interaction, p):
            return await interaction.response.send_message("❌ Только лидер.", ephemeral=True)
        if member.id == p["leader_id"]:
            return await interaction.response.send_message("❌ Нельзя исключить лидера.", ephemeral=True)
        await db.remove_party_member(member.id, p["party_id"])
        await interaction.response.send_message(f"👋 {member.mention} исключён.", ephemeral=True)

    @party.command(name="leave", description="Покинуть партию")
    async def leave(self, interaction: discord.Interaction):
        p = await db.get_user_party(interaction.user.id)
        if not p:
            return await interaction.response.send_message("❌ Вы не в партии.", ephemeral=True)
        if p["role"] == "leader":
            return await interaction.response.send_message("❌ Лидер не может покинуть партию.", ephemeral=True)
        await db.remove_party_member(interaction.user.id, p["party_id"])
        await interaction.response.send_message(f"👋 Вы покинули **{p['name']}**.", ephemeral=True)

    @party.command(name="deposit", description="Пополнить казну партии")
    async def deposit(self, interaction: discord.Interaction, amount: int):
        if amount <= 0:
            return await interaction.response.send_message("❌ Сумма > 0.", ephemeral=True)
        p = await db.get_user_party(interaction.user.id)
        if not p:
            return await interaction.response.send_message("❌ Вы не в партии.", ephemeral=True)
        user = await db.get_user(interaction.user.id)
        if user["wallet"] < amount:
            return await interaction.response.send_message("❌ Недостаточно монет.", ephemeral=True)
        await db.add_balance(interaction.user.id, -amount)
        await db.add_party_treasury(p["party_id"], amount)
        await db.log_transaction(interaction.user.id, None, amount, f"party_deposit:{p['party_id']}")
        await interaction.response.send_message(
            f"💰 В казну **{p['name']}** внесено `{amount:,}` монет."
        )

    @party.command(name="withdraw", description="[Лидер] Снять из казны партии")
    async def withdraw(self, interaction: discord.Interaction, amount: int):
        p = await db.get_user_party(interaction.user.id)
        if not p or not self._is_leader_or_admin(interaction, p):
            return await interaction.response.send_message("❌ Только лидер.", ephemeral=True)
        if amount <= 0 or p["treasury"] < amount:
            return await interaction.response.send_message("❌ Недостаточно средств в казне.", ephemeral=True)
        await db.add_party_treasury(p["party_id"], -amount)
        await db.add_balance(interaction.user.id, amount)
        await db.log_transaction(None, interaction.user.id, amount, f"party_withdraw:{p['party_id']}")
        await interaction.response.send_message(
            f"💸 Из казны **{p['name']}** снято `{amount:,}` монет."
        )

    # ========== ФИШКИ ==========

    @party.command(name="broadcast", description="[Лидер] Отправить сообщение всем членам партии (в ЛС)")
    async def broadcast(self, interaction: discord.Interaction, message: str):
        p = await db.get_user_party(interaction.user.id)
        if not p or not self._is_leader_or_admin(interaction, p):
            return await interaction.response.send_message("❌ Только лидер.", ephemeral=True)
        rows = await db.get_party_members(p["party_id"])
        sent, failed = 0, 0
        for m in rows:
            member = interaction.guild.get_member(m["user_id"])
            if not member or member.bot:
                failed += 1
                continue
            try:
                try:
                    color = discord.Color.from_str(p["color"])
                except Exception:
                    color = discord.Color.blurple()
                embed = discord.Embed(
                    title=f"📢 Обращение лидера партии «{p['name']}»",
                    description=message,
                    color=color,
                )
                embed.set_footer(text=f"Лидер: {interaction.user.display_name}")
                await member.send(embed=embed)
                sent += 1
            except Exception:
                failed += 1
        await interaction.response.send_message(
            f"📨 Отправлено: **{sent}**, не доставлено: **{failed}**.", ephemeral=True
        )

    @party.command(name="rally", description="[Лидер] Организовать митинг — всем членам +XP")
    async def rally(self, interaction: discord.Interaction):
        p = await db.get_user_party(interaction.user.id)
        if not p or not self._is_leader_or_admin(interaction, p):
            return await interaction.response.send_message("❌ Только лидер.", ephemeral=True)
        rows = await db.get_party_members(p["party_id"])
        profile = self.bot.get_cog("Profile")
        count = 0
        for m in rows:
            member = interaction.guild.get_member(m["user_id"])
            if not member or member.bot:
                continue
            if profile:
                await profile.add_xp(member.id, 50)
            count += 1
            try:
                await member.send(f"📣 Митинг партии **{p['name']}**! Лидер зовёт вас. +50 XP.")
            except Exception:
                pass
        try:
            color = discord.Color.from_str(p["color"])
        except Exception:
            color = discord.Color.gold()
        embed = discord.Embed(
            title="📣 Митинг!",
            description=f"Партия **{p['name']}** провела митинг.\nПриглашено участников: **{count}**.",
            color=color,
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Parties(bot))