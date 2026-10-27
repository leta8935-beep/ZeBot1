import io
import time
import discord
from discord import app_commands
from discord.ext import commands
from pathlib import Path
from storage import storage

from database import db
from utils import election_image



class Elections(commands.Cog):
    """Система выборов с полным контролем администрации."""

    def __init__(self, bot):
        self.bot = bot

    election = app_commands.Group(name="election", description="Управление выборами (ADMIN)")

    def _admin(self, interaction):
        if not interaction.user.guild_permissions.administrator:
            raise app_commands.CheckFailure("❌ Только администратор.")

    # ========== СОЗДАНИЕ ==========

    @election.command(name="create", description="[ADMIN] Создать выборы")
    @app_commands.describe(type="Тип: presidential или parliamentary",
                           title="Заголовок", channel="Канал для публикации результатов")
    async def create(self, interaction: discord.Interaction, type: str, title: str,
                     channel: discord.TextChannel):
        try:
            self._admin(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        if type not in ("presidential", "parliamentary"):
            return await interaction.response.send_message(
                "❌ Тип: `presidential` или `parliamentary`.", ephemeral=True)
        eid = await db.create_election(type, title, channel.id, interaction.user.id)
        await interaction.response.send_message(
            f"✅ Выборы **#{eid}** созданы.\n"
            f"**Тип:** {type}\n**Заголовок:** {title}\n**Канал:** {channel.mention}\n\n"
            f"Добавляйте кандидатов: `/election addpresident {eid} @user` или `/election addparty {eid} \"Название\"`.",
            ephemeral=True,
        )

    @election.command(name="edit", description="[ADMIN] Изменить параметр выборов")
    @app_commands.describe(field="Поле: title, date_text, turnout, total_seats, channel",
                           value="Значение")
    async def edit(self, interaction: discord.Interaction, eid: int, field: str, value: str):
        try:
            self._admin(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        e = await db.get_election(eid)
        if not e:
            return await interaction.response.send_message("❌ Выборы не найдены.", ephemeral=True)
        if field == "channel":
            try:
                cid = int(value.strip("<#>"))
                await db.update_election(eid, channel_id=cid)
                return await interaction.response.send_message("✅ Канал обновлён.", ephemeral=True)
            except ValueError:
                return await interaction.response.send_message("❌ Укажите ID канала.", ephemeral=True)
        if field in ("turnout", "total_seats"):
            try:
                v = int(value)
            except ValueError:
                return await interaction.response.send_message("❌ Нужно число.", ephemeral=True)
            await db.update_election(eid, **{field: v})
        elif field in ("title", "date_text"):
            await db.update_election(eid, **{field: value})
        else:
            return await interaction.response.send_message("❌ Неверное поле.", ephemeral=True)
        await interaction.response.send_message(f"✏️ Поле `{field}` обновлено.", ephemeral=True)

    # ========== КАНДИДАТЫ ==========

    @election.command(name="addpresident", description="[ADMIN] Добавить кандидата в президенты")
    async def addpresident(self, interaction: discord.Interaction, eid: int,
                           user: discord.Member, party: str = "—", ideology: str = "—",
                           color: str = "#1e3a8a"):
        try:
            self._admin(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        e = await db.get_election(eid)
        if not e or e["type"] != "presidential":
            return await interaction.response.send_message("❌ Не presidential выборы.", ephemeral=True)
        cands = await db.get_candidates(eid)
        await db.add_candidate(eid,
            user_id=user.id,
            display_name=user.display_name,
            party_name=party,
            ideology=ideology,
            color=color,
            votes=0,
            order_idx=len(cands),
        )
        await interaction.response.send_message(
            f"✅ {user.mention} добавлен кандидатом (#{len(cands) + 1}).\n"
            f"Голоса: `/election setvotes {eid} {len(cands) + 1} <percent>`",
            ephemeral=True,
        )

    @election.command(name="addparty", description="[ADMIN] Добавить партию в парламентские выборы")
    async def addparty(self, interaction: discord.Interaction, eid: int, party_name: str):
        try:
            self._admin(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        e = await db.get_election(eid)
        if not e or e["type"] != "parliamentary":
            return await interaction.response.send_message("❌ Не parliamentary выборы.", ephemeral=True)
        p = await db.get_party(party_name)
        if not p:
            return await interaction.response.send_message("❌ Партия не найдена.", ephemeral=True)
        cands = await db.get_candidates(eid)
        await db.add_candidate(eid,
            user_id=p["leader_id"],
            party_id=p["party_id"],
            display_name=p["name"],
            party_name=p["name"],
            ideology=p["ideology"],
            color=p["color"],
            flag_file=p["flag_file"],
            flag_mode=p["flag_mode"],
            votes=0,
            seats=0,
            order_idx=len(cands),
        )
        await interaction.response.send_message(
            f"✅ Партия **{p['name']}** добавлена (#{len(cands) + 1}).\n"
            f"Голоса: `/election setvotes {eid} {len(cands) + 1} <percent>`\n"
            f"Места: `/election setseats {eid} {len(cands) + 1} <int>`",
            ephemeral=True,
        )

    @election.command(name="setvotes", description="[ADMIN] Установить % голосов")
    async def setvotes(self, interaction: discord.Interaction, eid: int, num: int, percent: float):
        try:
            self._admin(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        cands = await db.get_candidates(eid)
        if num < 1 or num > len(cands):
            return await interaction.response.send_message("❌ Неверный номер.", ephemeral=True)
        await db.update_candidate(cands[num - 1]["candidate_id"], votes=percent)
        await interaction.response.send_message(
            f"✅ {cands[num - 1]['display_name']}: **{percent}%**", ephemeral=True
        )

    @election.command(name="setseats", description="[ADMIN] Установить число мест (parliamentary)")
    async def setseats(self, interaction: discord.Interaction, eid: int, num: int, seats: int):
        try:
            self._admin(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        cands = await db.get_candidates(eid)
        if num < 1 or num > len(cands):
            return await interaction.response.send_message("❌ Неверный номер.", ephemeral=True)
        await db.update_candidate(cands[num - 1]["candidate_id"], seats=seats)
        await interaction.response.send_message(
            f"✅ {cands[num - 1]['display_name']}: **{seats} мест**", ephemeral=True
        )

    @election.command(name="setphoto", description="[ADMIN] Загрузить фото кандидата")
    async def setphoto(self, interaction: discord.Interaction, eid: int, num: int,
                       file: discord.Attachment):
        try:
            self._admin(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        cands = await db.get_candidates(eid)
        if num < 1 or num > len(cands):
            return await interaction.response.send_message("❌ Неверный номер.", ephemeral=True)
        content = await file.read()
        url = await storage.upload(content, file.filename, file.content_type or "image/png")
        await db.update_candidate(cands[num - 1]["candidate_id"], photo_file=url)
        await interaction.response.send_message("✅ Фото установлено.", ephemeral=True)

    @election.command(name="removecand", description="[ADMIN] Удалить кандидата по номеру")
    async def removecand(self, interaction: discord.Interaction, eid: int, num: int):
        try:
            self._admin(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        cands = await db.get_candidates(eid)
        if num < 1 or num > len(cands):
            return await interaction.response.send_message("❌ Неверный номер.", ephemeral=True)
        await db.delete_candidate(cands[num - 1]["candidate_id"])
        await interaction.response.send_message("🗑️ Кандидат удалён.", ephemeral=True)

    # ========== ПРОСМОТР И ПУБЛИКАЦИЯ ==========

    @election.command(name="list", description="[ADMIN] Список выборов")
    async def list_elections(self, interaction: discord.Interaction):
        rows = await db.all_elections()
        if not rows:
            return await interaction.response.send_message("Выборов нет.", ephemeral=True)
        embed = discord.Embed(title="🗳️ Выборы", color=discord.Color.blurple())
        for e in rows:
            cands = await db.get_candidates(e["election_id"])
            embed.add_field(
                name=f"#{e['election_id']} — {e['title']}",
                value=f"**Тип:** {e['type']}\n**Статус:** {e['status']}\n"
                      f"**Кандидатов:** {len(cands)}\n**Канал:** <#{e['channel_id']}>",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @election.command(name="show", description="[ADMIN] Показать текущий состав выборов")
    async def show(self, interaction: discord.Interaction, eid: int):
        try:
            self._admin(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        e = await db.get_election(eid)
        if not e:
            return await interaction.response.send_message("❌ Не найдено.", ephemeral=True)
        cands = await db.get_candidates(eid)
        lines = []
        for i, c in enumerate(cands, 1):
            extra = f" ({c['seats']} мест)" if e["type"] == "parliamentary" else ""
            lines.append(f"**{i}. {c['display_name']}** — {c['votes']}%{extra}")
        embed = discord.Embed(
            title=f"#{eid} — {e['title']}",
            description="\n".join(lines) or "Пусто",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Явка", value=f"{e['turnout']}%", inline=True)
        if e["type"] == "parliamentary":
            embed.add_field(name="Мест всего", value=e["total_seats"], inline=True)
        embed.add_field(name="Канал", value=f"<#{e['channel_id']}>", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _build_image_data(self, e):
        cands = await db.get_candidates(e["election_id"])
        if e["type"] == "presidential":
            data = {
                "type": "presidential",
                "title": e["title"],
                "date": e["date_text"],
                "turnout": e["turnout"],
                "candidates": [],
            }
            for c in cands:
                data["candidates"].append({
                    "name": c["display_name"],
                    "party": c["party_name"] or "—",
                    "ideology": c["ideology"] or "—",
                    "color": c["color"],
                    "votes": float(c["votes"]),
                    "photo": storage.url(c["photo_file"]),
                    "flag": storage.url(c["flag_file"]),
                    "flagMode": c["flag_mode"] or "flag",
                })
        else:
            data = {
                "type": "parliamentary",
                "title": e["title"],
                "date": e["date_text"],
                "turnout": e["turnout"],
                "totalSeats": e["total_seats"],
                "parties": [],
            }
            for c in cands:
                data["parties"].append({
                    "name": c["display_name"],
                    "color": c["color"],
                    "votes": float(c["votes"]),
                    "seats": int(c["seats"]),
                    "flag": storage.url(c["flag_file"]),
                    "flagMode": c["flag_mode"] or "flag",
                })
        return data

    @election.command(name="preview", description="[ADMIN] Предпросмотр картинки (без публикации)")
    async def preview(self, interaction: discord.Interaction, eid: int):
        try:
            self._admin(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        e = await db.get_election(eid)
        if not e:
            return await interaction.response.send_message("❌ Не найдено.", ephemeral=True)
        await interaction.response.defer(thinking=True)
        data = await self._build_image_data(e)
        try:
            img = await election_image.render_election_image(data)
        except Exception as ex:
            return await interaction.followup.send(f"❌ Ошибка рендера: {ex}", ephemeral=True)
        await interaction.followup.send(
            file=discord.File(fp=io.BytesIO(img), filename=f"election_{eid}.png")
        )

    @election.command(name="publish", description="[ADMIN] Опубликовать результаты в канал")
    @app_commands.describe(result_text="Текст под картинкой (опционально)")
    async def publish(self, interaction: discord.Interaction, eid: int, result_text: str = None):
        try:
            self._admin(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        e = await db.get_election(eid)
        if not e:
            return await interaction.response.send_message("❌ Не найдено.", ephemeral=True)
        channel = interaction.guild.get_channel(e["channel_id"])
        if not channel:
            return await interaction.response.send_message(
                "❌ Канал не найден. Обновите: `/election edit` field=channel", ephemeral=True)

        await interaction.response.defer(thinking=True)
        data = await self._build_image_data(e)
        try:
            img = await election_image.render_election_image(data)
        except Exception as ex:
            return await interaction.followup.send(f"❌ Ошибка рендера: {ex}", ephemeral=True)

        file = discord.File(fp=io.BytesIO(img), filename=f"election_{eid}.png")

        cands = await db.get_candidates(eid)
        if e["type"] == "presidential" and cands:
            winner = max(cands, key=lambda c: c["votes"])
            try:
                color = discord.Color.from_str(winner["color"])
            except Exception:
                color = discord.Color.gold()
            embed = discord.Embed(
                title=f"🗳️ {e['title']}",
                description=result_text or f"**Победитель:** {winner['display_name']} ({winner['votes']}%)",
                color=color,
            )
        elif e["type"] == "parliamentary" and cands:
            winner = max(cands, key=lambda c: c["seats"])
            try:
                color = discord.Color.from_str(winner["color"])
            except Exception:
                color = discord.Color.gold()
            embed = discord.Embed(
                title=f"🗳️ {e['title']}",
                description=result_text or f"**Крупнейшая фракция:** {winner['display_name']} ({winner['seats']} мест)",
                color=color,
            )
        else:
            embed = discord.Embed(
                title=f"🗳️ {e['title']}",
                description=result_text or "—",
                color=discord.Color.gold(),
            )

        embed.set_image(url=f"attachment://election_{eid}.png")
        embed.set_footer(text=f"Явка: {e['turnout']}% · {e['date_text']}")

        await channel.send(embed=embed, file=file)
        await db.update_election(eid, status="published", posted_at=time.time())
        await interaction.followup.send(f"✅ Результаты опубликованы в {channel.mention}.", ephemeral=True)

    @election.command(name="delete", description="[ADMIN] Удалить выборы")
    async def delete(self, interaction: discord.Interaction, eid: int):
        try:
            self._admin(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        await db.delete_election(eid)
        await interaction.response.send_message("🗑️ Удалено.", ephemeral=True)

    async def cog_app_command_error(self, interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            if not interaction.response.is_done():
                await interaction.response.send_message(str(error), ephemeral=True)
        else:
            raise error


async def setup(bot):
    await bot.add_cog(Elections(bot))