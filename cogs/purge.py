import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime


class Purge(commands.Cog):
    """Гибкая очистка сообщений."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="purge", description="[ADMIN] Удалить сообщения с фильтрами")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(
        amount="Сколько сообщений проверить (макс. 1000)",
        user="Удалить только сообщения этого пользователя",
        contains="Удалить сообщения, содержащие текст",
        starts_with="Удалить сообщения, начинающиеся с текста",
        ends_with="Удалить сообщения, заканчивающиеся текстом",
        has_image="Удалить только сообщения с изображениями/файлами",
        has_link="Удалить только сообщения со ссылками",
        bots_only="Удалить только сообщения ботов",
        humans_only="Удалить только сообщения людей",
        before="Удалить сообщения до этой даты (ГГГГ-ММ-ДД)",
        after="Удалить сообщения после этой даты (ГГГГ-ММ-ДД)",
    )
    async def purge(
        self,
        interaction: discord.Interaction,
        amount: int = 100,
        user: discord.Member = None,
        contains: str = None,
        starts_with: str = None,
        ends_with: str = None,
        has_image: bool = False,
        has_link: bool = False,
        bots_only: bool = False,
        humans_only: bool = False,
        before: str = None,
        after: str = None,
    ):
        if amount > 1000:
            return await interaction.response.send_message(
                "❌ Максимум 1000 сообщений.", ephemeral=True
            )
        if amount < 1:
            return await interaction.response.send_message(
                "❌ Минимум 1 сообщение.", ephemeral=True
            )

        before_dt = None
        after_dt = None
        try:
            if before:
                before_dt = datetime.strptime(before, "%Y-%m-%d")
            if after:
                after_dt = datetime.strptime(after, "%Y-%m-%d")
        except ValueError:
            return await interaction.response.send_message(
                "❌ Неверный формат даты. Используйте ГГГГ-ММ-ДД.", ephemeral=True
            )

        await interaction.response.defer(thinking=True, ephemeral=True)

        def check(message: discord.Message) -> bool:
            if user and message.author.id != user.id:
                return False
            if contains and contains.lower() not in message.content.lower():
                return False
            if starts_with and not message.content.lower().startswith(starts_with.lower()):
                return False
            if ends_with and not message.content.lower().endswith(ends_with.lower()):
                return False
            if has_image and not message.attachments:
                return False
            if has_link:
                if not (("http://" in message.content or "https://" in message.content)
                        or message.embeds):
                    return False
            if bots_only and not message.author.bot:
                return False
            if humans_only and message.author.bot:
                return False
            if before_dt and message.created_at >= before_dt:
                return False
            if after_dt and message.created_at <= after_dt:
                return False
            return True

        try:
            deleted = await interaction.channel.purge(limit=amount, check=check)
            await interaction.followup.send(
                f"🗑️ Удалено **{len(deleted)}** сообщений.", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Нет прав на удаление сообщений.", ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Purge(bot))