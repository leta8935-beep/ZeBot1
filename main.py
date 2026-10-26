import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from database import Database

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

COGS = [
    "cogs.economy", 
    "cogs.organization",  # <-- Убедись, что файл в папке cogs называется organization.py
    "cogs.admin", 
    "cogs.settings",
    "cogs.registration"
]

class Zebot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.db = Database(DATABASE_URL)
        self.temp_reg_data = {}

    async def setup_hook(self):
        await self.db.connect()
        print("База данных подключена.")
        for cog in COGS:
            try:
                await self.load_extension(cog)
                print(f"Модуль {cog} загружен.")
            except Exception as e:
                print(f"Ошибка при загрузке {cog}: {e}")
        
        await self.tree.sync()
        print("Бот запущен, команды синхронизированы!")

if __name__ == "__main__":
    if not TOKEN or not DATABASE_URL:
        raise RuntimeError("Заполни DISCORD_TOKEN и DATABASE_URL")
    bot = Zebot()
    bot.run(TOKEN)
