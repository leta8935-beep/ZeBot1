import discord
from discord import app_commands
from discord.ext import commands

from database import db


class Shop(commands.Cog):
    """Магазин государства и инвентарь."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="shop", description="Показать товары магазина")
    async def shop(self, interaction: discord.Interaction):
        items = await db.shop_list()
        if not items:
            return await interaction.response.send_message("Магазин пуст.")

        embed = discord.Embed(
            title="🏪 Государственный магазин",
            description="Купить: `/buy <название> [количество]`",
            color=discord.Color.teal(),
        )
        for it in items:
            embed.add_field(
                name=f"• {it['name']} — `{it['price']:,}` монет",
                value=it["description"] or "—",
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="buy", description="Купить товар из магазина")
    @app_commands.describe(name="Название товара", quantity="Количество (по умолчанию 1)")
    async def buy(self, interaction: discord.Interaction, name: str, quantity: int = 1):
        if quantity <= 0:
            return await interaction.response.send_message("❌ Неверное количество.", ephemeral=True)

        item = await db.get_item(name)
        if not item:
            return await interaction.response.send_message(
                f"❌ Товар **{name}** не найден.", ephemeral=True
            )

        total = item["price"] * quantity
        user = await db.get_user(interaction.user.id)
        if user["wallet"] < total:
            return await interaction.response.send_message(
                f"❌ Нужно `{total:,}` монет, у вас `{user['wallet']:,}`.", ephemeral=True
            )

        await db.add_balance(interaction.user.id, -total)
        await db.add_item_to_inventory(interaction.user.id, item["item_id"], quantity)
        await db.log_transaction(interaction.user.id, None, total, "shop_buy")

        if item["role_id"]:
            role = interaction.guild.get_role(item["role_id"])
            if role:
                try:
                    await interaction.user.add_roles(role)
                except discord.Forbidden:
                    pass

        await interaction.response.send_message(
            f"✅ Куплено **{item['name']}** x{quantity} за `{total:,}` монет."
        )

    @app_commands.command(name="inventory", description="Ваш инвентарь")
    @app_commands.describe(member="Чей инвентарь (по умолчанию — ваш)")
    async def inventory(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        rows = await db.get_inventory(member.id)
        if not rows:
            return await interaction.response.send_message(
                f"🎒 Инвентарь {member.display_name} пуст."
            )

        embed = discord.Embed(
            title=f"🎒 Инвентарь — {member.display_name}",
            color=discord.Color.orange(),
        )
        for row in rows:
            embed.add_field(
                name=row["name"], value=f"Количество: **{row['quantity']}**", inline=True
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="sell", description="Продать предмет государству (за 50% цены)")
    @app_commands.describe(name="Название предмета", quantity="Количество")
    async def sell(self, interaction: discord.Interaction, name: str, quantity: int = 1):
        item = await db.get_item(name)
        if not item:
            return await interaction.response.send_message("❌ Товар не найден.", ephemeral=True)

        ok = await db.remove_item_from_inventory(interaction.user.id, item["item_id"], quantity)
        if not ok:
            return await interaction.response.send_message(
                "❌ У вас нет столько предметов.", ephemeral=True
            )

        payout = int(item["price"] * 0.5) * quantity
        await db.add_balance(interaction.user.id, payout)
        await db.log_transaction(None, interaction.user.id, payout, "shop_sell")
        await interaction.response.send_message(
            f"💵 Вы продали **{item['name']}** x{quantity} за `{payout:,}` монет."
        )


async def setup(bot):
    await bot.add_cog(Shop(bot))