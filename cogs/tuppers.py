import re
import discord
from discord import app_commands
from discord.ext import commands

from database import db

TUPPER_NAME_LIMIT = 80
AVATAR_URL_RE = re.compile(r"^https?://.+\.(png|jpg|jpeg|gif|webp)$", re.IGNORECASE)


class TupperCreateModal(discord.ui.Modal, title="Создание персонажа"):
    name = discord.ui.TextInput(
        label="Имя персонажа",
        placeholder="Например: Виктор Янукович",
        max_length=TUPPER_NAME_LIMIT,
        required=True,
    )
    avatar = discord.ui.TextInput(
        label="Ссылка на аватар (необязательно)",
        placeholder="https://example.com/avatar.png",
        required=False,
        max_length=512,
    )

    async def on_submit(self, interaction: discord.Interaction):
        avatar_url = self.avatar.value.strip() if self.avatar.value else None
        if avatar_url and not AVATAR_URL_RE.match(avatar_url):
            return await interaction.response.send_message(
                "❌ Ссылка на аватар должна быть прямой ссылкой (.png, .jpg, .gif, .webp).",
                ephemeral=True,
            )

        tupper_id = await db.create_tupper(interaction.user.id, self.name.value.strip(), avatar_url)
        if tupper_id is None:
            return await interaction.response.send_message(
                "❌ Персонаж с таким именем уже существует.", ephemeral=True
            )

        embed = discord.Embed(
            title="✅ Персонаж создан",
            description=f"**{self.name.value}** (ID: `{tupper_id}`)\n"
                        f"Аватар: {'✅' if avatar_url else '❌ (по умолчанию)'}",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class TupperEmbedModal(discord.ui.Modal, title="Отправка эмбеда от имени персонажа"):
    title_text = discord.ui.TextInput(
        label="Заголовок эмбеда",
        placeholder="Например: Официальное заявление",
        max_length=256,
        required=True,
    )
    description = discord.ui.TextInput(
        label="Описание",
        style=discord.TextStyle.paragraph,
        max_length=4000,
        required=True,
    )
    color_hex = discord.ui.TextInput(
        label="Цвет (HEX)",
        placeholder="#1e3a8a",
        default="#1e3a8a",
        max_length=7,
        required=False,
    )
    footer = discord.ui.TextInput(
        label="Подвал (необязательно)",
        max_length=2048,
        required=False,
    )
    image_url = discord.ui.TextInput(
        label="Ссылка на картинку (необязательно)",
        placeholder="https://example.com/image.png",
        max_length=512,
        required=False,
    )

    def __init__(self, bot, tupper, channel):
        super().__init__()
        self.bot = bot
        self.tupper = tupper
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        color = discord.Color.blurple()
        try:
            hex_str = self.color_hex.value.strip().lstrip("#")
            if len(hex_str) in (3, 6):
                color = discord.Color(int(hex_str, 16))
        except Exception:
            pass

        embed = discord.Embed(
            title=self.title_text.value,
            description=self.description.value,
            color=color,
        )
        if self.footer.value:
            embed.set_footer(text=self.footer.value)
        if self.image_url.value:
            embed.set_image(url=self.image_url.value)

        webhook = await self._get_or_create_webhook(self.channel)
        if not webhook:
            return await interaction.response.send_message(
                "❌ Не удалось создать вебхук. Проверьте право «Управление вебхуками».",
                ephemeral=True,
            )

        try:
            await webhook.send(
                embed=embed,
                username=self.tupper["name"],
                avatar_url=self.tupper["avatar_url"] or None,
            )
        except Exception as e:
            return await interaction.response.send_message(
                f"❌ Ошибка отправки: {e}", ephemeral=True
            )

        await interaction.response.send_message("✅ Эмбед отправлен.", ephemeral=True)

    async def _get_or_create_webhook(self, channel):
        try:
            webhooks = await channel.webhooks()
            for wh in webhooks:
                if wh.name == f"Tupper-{self.tupper['tupper_id']}":
                    return wh
            return await channel.create_webhook(name=f"Tupper-{self.tupper['tupper_id']}")
        except Exception:
            return None


class Tuppers(commands.Cog):
    """Система персонажей (аналог TupperBox)."""

    def __init__(self, bot):
        self.bot = bot

    tupper = app_commands.Group(name="tupper", description="Управление персонажами")

    @tupper.command(name="create", description="Создать нового персонажа")
    async def create(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TupperCreateModal())

    @tupper.command(name="list", description="Список ваших персонажей")
    async def list_tuppers(self, interaction: discord.Interaction):
        rows = await db.list_tuppers(interaction.user.id)
        if not rows:
            return await interaction.response.send_message(
                "📭 У вас нет персонажей. Создайте командой `/tupper create`.",
                ephemeral=True,
            )

        embed = discord.Embed(title="🎭 Ваши персонажи", color=discord.Color.blurple())
        for t in rows:
            avatar_status = "✅" if t["avatar_url"] else "❌"
            embed.add_field(
                name=f"#{t['tupper_id']} — {t['name']}",
                value=f"Аватар: {avatar_status}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tupper.command(name="switch", description="Переключиться на персонажа (авторежим)")
    @app_commands.describe(name="Имя персонажа")
    async def switch(self, interaction: discord.Interaction, name: str):
        tupper = await db.get_tupper_by_name(interaction.user.id, name)
        if not tupper:
            return await interaction.response.send_message(
                f"❌ Персонаж **{name}** не найден. Создайте: `/tupper create`.",
                ephemeral=True,
            )

        webhook = await self._get_or_create_webhook(interaction.channel, tupper["tupper_id"])
        if not webhook:
            return await interaction.response.send_message(
                "❌ Не удалось создать вебхук. Проверьте право «Управление вебхуками».",
                ephemeral=True,
            )

        await db.set_tupper_session(
            interaction.user.id,
            tupper["tupper_id"],
            interaction.channel.id,
            webhook.id,
            webhook.token,
        )

        embed = discord.Embed(
            title="🎭 Режим персонажа активирован",
            description=f"Теперь все ваши сообщения в этом канале будут отправляться от имени "
                        f"**{tupper['name']}**.\n\nЧтобы отключить: `/tupper off`",
            color=discord.Color.green(),
        )
        embed.set_thumbnail(url=tupper["avatar_url"] or interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tupper.command(name="off", description="Отключить режим персонажа")
    async def off(self, interaction: discord.Interaction):
        session = await db.get_tupper_session(interaction.user.id)
        if not session or not session["enabled"]:
            return await interaction.response.send_message(
                "❌ У вас нет активного персонажа.", ephemeral=True
            )
        await db.disable_tupper_session(interaction.user.id)
        await interaction.response.send_message(
            "🔕 Режим персонажа отключён.", ephemeral=True
        )

    @tupper.command(name="embed", description="Отправить эмбед от имени персонажа")
    @app_commands.describe(name="Имя персонажа (если не указано — активный)")
    async def embed(self, interaction: discord.Interaction, name: str = None):
        if name:
            tupper = await db.get_tupper_by_name(interaction.user.id, name)
        else:
            session = await db.get_tupper_session(interaction.user.id)
            if not session or not session["enabled"]:
                return await interaction.response.send_message(
                    "❌ Нет активного персонажа.", ephemeral=True
                )
            tupper = await db.get_tupper(session["tupper_id"])

        if not tupper:
            return await interaction.response.send_message("❌ Персонаж не найден.", ephemeral=True)

        await interaction.response.send_modal(TupperEmbedModal(self.bot, tupper, interaction.channel))

    @tupper.command(name="delete", description="Удалить персонажа")
    @app_commands.describe(name="Имя персонажа")
    async def delete(self, interaction: discord.Interaction, name: str):
        tupper = await db.get_tupper_by_name(interaction.user.id, name)
        if not tupper:
            return await interaction.response.send_message("❌ Персонаж не найден.", ephemeral=True)

        session = await db.get_tupper_session(interaction.user.id)
        if session and session["tupper_id"] == tupper["tupper_id"]:
            await db.disable_tupper_session(interaction.user.id)

        await db.delete_tupper(tupper["tupper_id"])
        await interaction.response.send_message(
            f"🗑️ Персонаж **{name}** удалён.", ephemeral=True
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if message.content.startswith("/"):
            return

        session = await db.get_tupper_session(message.author.id)
        if not session or not session["enabled"]:
            return
        if session["channel_id"] != message.channel.id:
            return

        tupper = await db.get_tupper(session["tupper_id"])
        if not tupper:
            return

        webhook = None
        try:
            webhook = await self.bot.fetch_webhook(session["webhook_id"])
        except Exception:
            webhook = await self._get_or_create_webhook(message.channel, tupper["tupper_id"])
            if webhook:
                await db.update_tupper_session_webhook(
                    message.author.id, webhook.id, webhook.token
                )

        if not webhook:
            return

        try:
            files = [await a.to_file() for a in message.attachments] if message.attachments else []
            await webhook.send(
                content=message.content or None,
                username=tupper["name"],
                avatar_url=tupper["avatar_url"] or None,
                files=files,
            )
            await message.delete()
        except Exception:
            pass

    async def _get_or_create_webhook(self, channel, tupper_id):
        try:
            webhooks = await channel.webhooks()
            for wh in webhooks:
                if wh.name == f"Tupper-{tupper_id}":
                    return wh
            return await channel.create_webhook(name=f"Tupper-{tupper_id}")
        except Exception:
            return None


async def setup(bot):
    await bot.add_cog(Tuppers(bot))