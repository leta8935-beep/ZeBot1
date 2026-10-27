import discord
from discord import app_commands
from discord.ext import commands

import config
from database import db


class Market(commands.Cog):
    """Игрок-игрок торговля."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="market", description="Все активные лоты на рынке")
    async def market(self, interaction: discord.Interaction):
        listings = await db.market_listings()
        if not listings:
            return await interaction.response.send_message(
                "📭 Рынок пуст. Выставите товар через `/list`."
            )

        embed = discord.Embed(
            title="🏛️ Рынок государства",
            description="Купить: `/take <id>`",
            color=discord.Color.purple(),
        )
        for l in listings:
            try:
                seller = self.bot.get_user(l["seller_id"]) or await self.bot.fetch_user(l["seller_id"])
                seller_name = seller.display_name
            except Exception:
                seller_name = f"ID {l['seller_id']}"
            embed.add_field(
                name=f"#{l['listing_id']} — {l['name']} x{l['quantity']}",
                value=f"Цена: `{l['price']:,}` монет | Продавец: **{seller_name}**",
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="list", description="Выставить предмет из инвентаря на рынок")
    @app_commands.describe(name="Название предмета", quantity="Количество", price="Цена за всё")
    async def list_item(
        self, interaction: discord.Interaction, name: str, quantity: int, price: int
    ):
        if quantity <= 0 or price <= 0:
            return await interaction.response.send_message(
                "❌ Некорректные параметры.", ephemeral=True
            )

        item = await db.get_item(name)
        if not item:
            return await interaction.response.send_message(
                "❌ Товар не найден.", ephemeral=True
            )

        ok = await db.remove_item_from_inventory(
            interaction.user.id, item["item_id"], quantity
        )
        if not ok:
            return await interaction.response.send_message(
                "❌ У вас нет столько предметов.", ephemeral=True
            )

        await db.create_listing(interaction.user.id, item["item_id"], quantity, price)
        await interaction.response.send_message(
            f"📦 Лот выставлен: **{item['name']}** x{quantity} за `{price:,}` монет."
        )

    @app_commands.command(name="unlist", description="Снять свой лот с рынка")
    @app_commands.describe(listing_id="ID лота")
    async def unlist(self, interaction: discord.Interaction, listing_id: int):
        listing = await db.get_listing(listing_id)
        if not listing:
            return await interaction.response.send_message("❌ Лот не найден.", ephemeral=True)
        if listing["seller_id"] != interaction.user.id:
            return await interaction.response.send_message(
                "❌ Это не ваш лот.", ephemeral=True
            )

        await db.add_item_to_inventory(
            interaction.user.id, listing["item_id"], listing["quantity"]
        )
        await db.delete_listing(listing_id)
        await interaction.response.send_message("✅ Лот снят с продажи.")

    @app_commands.command(name="take", description="Купить лот на рынке")
    @app_commands.describe(listing_id="ID лота")
    async def take(self, interaction: discord.Interaction, listing_id: int):
        listing = await db.get_listing(listing_id)
        if not listing:
            return await interaction.response.send_message("❌ Лот не найден.", ephemeral=True)
        if listing["seller_id"] == interaction.user.id:
            return await interaction.response.send_message(
                "❌ Нельзя покупать свой лот.", ephemeral=True
            )

        buyer = await db.get_user(interaction.user.id)
        if buyer["wallet"] < listing["price"]:
            return await interaction.response.send_message(
                "❌ Недостаточно монет.", ephemeral=True
            )

        commission = int(listing["price"] * config.MARKET_COMMISSION)
        net = listing["price"] - commission

        await db.add_balance(interaction.user.id, -listing["price"])
        await db.get_user(listing["seller_id"])
        await db.add_balance(listing["seller_id"], net)
        await db.add_item_to_inventory(
            interaction.user.id, listing["item_id"], listing["quantity"]
        )
        await db.delete_listing(listing_id)
        await db.log_transaction(interaction.user.id, listing["seller_id"], listing["price"], "market")

        await interaction.response.send_message(
            f"✅ Куплено! Продавец получил `{net:,}` (комиссия `{commission:,}`)."
        )


async def setup(bot):
    await bot.add_cog(Market(bot))