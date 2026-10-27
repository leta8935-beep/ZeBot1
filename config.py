
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

STARTING_BALANCE = int(os.getenv("STARTING_BALANCE", "500"))
DAILY_REWARD = int(os.getenv("DAILY_REWARD", "1000"))
WORK_COOLDOWN = int(os.getenv("WORK_COOLDOWN", "3600"))
WORK_MIN = int(os.getenv("WORK_MIN", "100"))
WORK_MAX = int(os.getenv("WORK_MAX", "350"))
TRANSFER_TAX = float(os.getenv("TRANSFER_TAX", "0.05"))
MARKET_COMMISSION = float(os.getenv("MARKET_COMMISSION", "0.07"))
BANK_INTEREST = float(os.getenv("BANK_INTEREST", "0.02"))
XP_PER_MESSAGE = int(os.getenv("XP_PER_MESSAGE", "5"))
XP_COOLDOWN = int(os.getenv("XP_COOLDOWN", "60"))

MEDIA_STORAGE_URL = os.getenv('MEDIA_STORAGE_URL', '')
MEDIA_STORAGE_TOKEN = os.getenv('MEDIA_STORAGE_TOKEN', '')
