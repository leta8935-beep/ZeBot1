import time

import discord
from discord import app_commands
from discord.ext import commands

import config
from database import db


def xp_needed(level: int) -> int:
    return int(50 * (level ** 1.5))


def level_from_xp(xp: int) -> int:
    level = 1
    while xp >= xp_needed(level):
        xp -= xp_needed(level)
        level += 1
    return level


class Profile(commands.Cog):
    """Профиль, уровни, XP."""

    def __init__(self, bot):
        self.bot = bot

    async def add_xp(self, user_id: int, amount: int):
        user = await db.get_user(user_id)
        new_xp = user["xp"] + amount
        new_level = level_from_xp(new_xp)
        await db.update_user(user_id, xp=new_xp, level=new_level)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        user = await db.get_user(message.author.id)
        now = time.time()
        if now - user["last_xp"] >= config.XP_COOLDOWN:
            await self.add_xp(message.author.id, config.XP_PER_MESSAGE)
            await db.update_user(message.author.id, last_xp=now)

    @app_commands.command(name="profile", description="Ваш профиль")
    @app_commands.describe(member="Чей профиль (по умолчанию — ваш)")
    async def profile(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        user = await db.get_user(member.id)

        xp = user["xp"]
        level = user["level"]
        next_xp = xp_needed(level)
        total_before = sum(xp_needed(l) for l in range(1, level))
        progress_xp = xp - total_before
        progress = min(progress_xp / next_xp, 1.0) if next_xp > 0 else 0
        bar_len = 15
        filled = int(progress * bar_len)
        bar = "▰" * filled + "▱" * (bar_len - filled)

        job = user["job"] or "Безработный"
        balance = user["wallet"] + user["bank"]

        embed = discord.Embed(
            title=f"👤 Профиль — {member.display_name}",
            color=discord.Color.blurple(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="🏅 Уровень", value=f"`{level}`", inline=True)
        embed.add_field(name="💼 Профессия", value=job, inline=True)
        embed.add_field(name="💵 Капитал", value=f"`{balance:,}` монет", inline=True)
        embed.add_field(
            name="📈 Прогресс",
            value=f"`{bar}` {progress_xp}/{next_xp} XP",
            inline=False,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard", description="Топ-10 по уровню")
    async def leaderboard(self, interaction: discord.Interaction):
        rows = await db.top_level(10)
        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, row in enumerate(rows):
            try:
                user = self.bot.get_user(row["user_id"]) or await self.bot.fetch_user(row["user_id"])
                name = user.display_name
            except Exception:
                name = f"ID {row['user_id']}"
            prefix = medals[i] if i < 3 else f"`{i + 1}.`"
            lines.append(f"{prefix} **{name}** — ур. `{row['level']}` ({row['xp']} XP)")

        embed = discord.Embed(
            title="🏅 Топ по уровню",
            description="\n".join(lines) or "Пусто",
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Profile(bot))