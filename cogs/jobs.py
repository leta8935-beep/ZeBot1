import random
import time

import discord
from discord import app_commands
from discord.ext import commands

import config
from database import db

JOBS = {
    "Грузчик": (150, 300),
    "Курьер": (180, 350),
    "Программист": (300, 600),
    "Дизайнер": (280, 550),
    "Врач": (400, 700),
    "Полицейский": (350, 600),
    "Учитель": (250, 500),
    "Инженер": (400, 650),
    "Банкир": (500, 900),
    "Таксист": (200, 400),
}


class Jobs(commands.Cog):
    """Работа, дейли, преступность."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="work", description="Устроиться на работу и заработать")
    async def work(self, interaction: discord.Interaction):
        user = await db.get_user(interaction.user.id)
        now = time.time()

        if now - user["last_work"] < config.WORK_COOLDOWN:
            left = int(config.WORK_COOLDOWN - (now - user["last_work"]))
            m, s = divmod(left, 60)
            return await interaction.response.send_message(
                f"⏳ Отдохните ещё **{m} мин {s} сек** перед следующей сменой.",
                ephemeral=True,
            )

        current_job = user["job"]
        if not current_job or current_job not in JOBS:
            current_job = random.choice(list(JOBS.keys()))
            await db.update_user(interaction.user.id, job=current_job)

        low, high = JOBS[current_job]
        salary = random.randint(low, high)

        await db.add_balance(interaction.user.id, salary)
        await db.update_user(interaction.user.id, last_work=now)
        await db.log_transaction(None, interaction.user.id, salary, "work")

        profile_cog = self.bot.get_cog("Profile")
        if profile_cog:
            await profile_cog.add_xp(interaction.user.id, 20)

        embed = discord.Embed(
            title="💼 Рабочий день окончен",
            description=f"Вы работали **{current_job.lower()}** и заработали `{salary:,}` монет!",
            color=discord.Color.green(),
        )
        embed.set_footer(text="Кулдаун: 1 час")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="resign", description="Уволиться с текущей работы")
    async def resign(self, interaction: discord.Interaction):
        user = await db.get_user(interaction.user.id)
        if not user["job"]:
            return await interaction.response.send_message(
                "❌ Вы и так безработный.", ephemeral=True
            )
        await db.update_user(interaction.user.id, job=None)
        await interaction.response.send_message(
            f"📄 Вы уволились с должности **{user['job']}**.", ephemeral=True
        )

    @app_commands.command(name="daily", description="Получить ежедневную награду")
    async def daily(self, interaction: discord.Interaction):
        user = await db.get_user(interaction.user.id)
        now = time.time()
        cooldown = 24 * 3600

        if now - user["last_daily"] < cooldown:
            left = int(cooldown - (now - user["last_daily"]))
            h, rem = divmod(left, 3600)
            m, s = divmod(rem, 60)
            return await interaction.response.send_message(
                f"⏳ Награда доступна через **{h}ч {m}м {s}с**.", ephemeral=True
            )

        reward = config.DAILY_REWARD
        interest = int(user["bank"] * config.BANK_INTEREST)
        total = reward + interest

        await db.add_balance(interaction.user.id, total)
        await db.update_user(interaction.user.id, last_daily=now)
        await db.log_transaction(None, interaction.user.id, total, "daily")

        embed = discord.Embed(
            title="🎁 Ежедневная награда",
            color=discord.Color.green(),
        )
        embed.add_field(name="Базовая награда", value=f"`{reward:,}`", inline=True)
        embed.add_field(name="Проценты на вклад", value=f"`{interest:,}`", inline=True)
        embed.add_field(name="Итого", value=f"`{total:,}` монет", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="crime", description="Совершить преступление (рискованно!)")
    async def crime(self, interaction: discord.Interaction):
        user = await db.get_user(interaction.user.id)
        now = time.time()
        if now - user["last_work"] < 1800:
            return await interaction.response.send_message(
                "⏳ Вы слишком на виду. Подождите 30 минут.", ephemeral=True
            )

        success = random.random() < 0.6
        if success:
            gain = random.randint(300, 900)
            await db.add_balance(interaction.user.id, gain)
            await db.update_user(interaction.user.id, last_work=now)
            await db.log_transaction(None, interaction.user.id, gain, "crime")
            await interaction.response.send_message(
                f"🕵️ Успех! Вы украли `{gain:,}` монет и скрылись."
            )
        else:
            loss = min(user["wallet"], random.randint(200, 700))
            await db.add_balance(interaction.user.id, -loss)
            await db.update_user(interaction.user.id, last_work=now)
            await interaction.response.send_message(
                f"🚔 Вас поймали! Штраф: `{loss:,}` монет."
            )


async def setup(bot):
    await bot.add_cog(Jobs(bot))