
import asyncio
import logging
import discord
from discord.ext import commands
from database import db
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("zebot")

COGS = [
    # Ядро и сохранённый паспорт
    "cogs.economy",
    "cogs.profile",
    "cogs.jobs",
    "cogs.shop",
    "cogs.market",
    "cogs.parties",
    "cogs.elections",
    "cogs.organizations",
    "cogs.tuppers",
    "cogs.purge",
    # Первый проект: регистрация, staff/setup и паспорт
    "cogs.registration",
    "cogs.settings",
    "cogs.admin",
    # Новый модуль приветствий
    "cogs.welcome",
]


class ZeBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.db = db
        self.temp_reg_data = {}

    async def setup_hook(self):
        await self.db.connect()
        for cog in COGS:
            try:
                await self.load_extension(cog)
                log.info("✅ Загружен %s", cog)
            except Exception:
                log.exception("❌ Ошибка загрузки %s", cog)
        try:
            synced = await self.tree.sync()
            log.info("🔁 Синхронизировано %s команд", len(synced))
        except Exception:
            log.exception("Ошибка синхронизации команд")

    async def on_ready(self):
        log.info("🤖 Бот запущен как %s (%s)", self.user, self.user.id)
        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name="за экономикой государства")
        )

    async def close(self):
        try:
            from utils import election_image, organization_image
            await election_image.shutdown()
            await organization_image.shutdown()
        except Exception:
            pass
        await self.db.close()
        await super().close()


async def main():
    if not config.TOKEN or not config.DATABASE_URL:
        raise RuntimeError("Заполни DISCORD_TOKEN и DATABASE_URL в .env")
    bot = ZeBot()
    async with bot:
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Бот остановлен")
