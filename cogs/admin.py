import io
import time
import discord
from discord import app_commands
from discord.ext import commands

from database import db


class Admin(commands.Cog):
    """Административные команды. Требуют прав управления сервером."""

    def __init__(self, bot):
        self.bot = bot

    adm = app_commands.Group(name="adm", description="Админ-команды",
                             default_permissions=discord.Permissions(administrator=True))

    def _check(interaction):
        if not interaction.user.guild_permissions.administrator:
            raise app_commands.CheckFailure("❌ Только администратор.")

    # ================== ДЕНЬГИ ==================
    @adm.command(name="addmoney", description="Выдать монеты игроку")
    @app_commands.describe(member="Кому", amount="Сколько", to_bank="В банк? (иначе в кошелёк)")
    async def addmoney(self, interaction: discord.Interaction, member: discord.Member,
                       amount: int, to_bank: bool = False):
        try: self._check(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        await db.get_user(member.id)
        await db.add_balance(member.id, amount, to_bank=to_bank)
        await db.log_transaction(None, member.id, amount, "admin_addmoney")
        await interaction.response.send_message(
            f"✅ {member.mention} получил `{amount:,}` ({'банк' if to_bank else 'кошелёк'}).",
            ephemeral=True,
        )

    @adm.command(name="removemoney", description="Забрать монеты у игрока")
    async def removemoney(self, interaction: discord.Interaction, member: discord.Member,
                          amount: int, from_bank: bool = False):
        try: self._check(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        u = await db.get_user(member.id)
        pool = u["bank"] if from_bank else u["wallet"]
        actual = min(amount, pool)
        await db.add_balance(member.id, -actual, to_bank=from_bank)
        await db.log_transaction(member.id, None, actual, "admin_removemoney")
        await interaction.response.send_message(
            f"✅ У {member.mention} снято `{actual:,}` ({'банк' if from_bank else 'кошелёк'}).",
            ephemeral=True,
        )

    @adm.command(name="setmoney", description="Установить точный баланс игрока")
    @app_commands.describe(wallet="Кошелёк", bank="Банк")
    async def setmoney(self, interaction: discord.Interaction, member: discord.Member,
                       wallet: int = None, bank: int = None):
        try: self._check(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        u = await db.get_user(member.id)
        fields = {}
        if wallet is not None: fields["wallet"] = wallet
        if bank is not None: fields["bank"] = bank
        if not fields:
            return await interaction.response.send_message("❌ Укажите wallet и/или bank.", ephemeral=True)
        await db.update_user(member.id, **fields)
        await interaction.response.send_message(
            f"✅ Баланс {member.mention}: кошелёк `{fields.get('wallet', u['wallet']):,}`, "
            f"банк `{fields.get('bank', u['bank']):,}`.",
            ephemeral=True,
        )

    @adm.command(name="resetuser", description="Полный сброс экономики игрока")
    async def resetuser(self, interaction: discord.Interaction, member: discord.Member):
        try: self._check(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        await db.update_user(member.id, wallet=500, bank=0, level=1, xp=0, job=None,
                             last_daily=0, last_work=0)
        await interaction.response.send_message(f"♻️ Экономика {member.mention} сброшена.", ephemeral=True)

    @adm.command(name="giveall", description="Выдать монеты всем зарегистрированным игрокам")
    async def giveall(self, interaction: discord.Interaction, amount: int, to_bank: bool = False):
        try: self._check(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        users = await db.all_users()
        for u in users:
            await db.add_balance(u["user_id"], amount, to_bank=to_bank)
        await interaction.response.send_message(
            f"✅ Выдано `{amount:,}` монет всем ({len(users)} чел.).", ephemeral=True
        )

    # ================== ПРЕДМЕТЫ ==================
    @adm.command(name="additem", description="Добавить товар в магазин")
    async def additem(self, interaction: discord.Interaction, name: str, price: int,
                      description: str = "—", role_id: str = None):
        try: self._check(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        rid = int(role_id) if role_id and role_id.isdigit() else None
        try:
            await db.add_shop_item(name, description, price, rid)
        except Exception as e:
            return await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)
        await interaction.response.send_message(
            f"✅ Товар **{name}** добавлен за `{price:,}`.", ephemeral=True
        )

    @adm.command(name="delitem", description="Удалить товар из магазина")
    async def delitem(self, interaction: discord.Interaction, name: str):
        try: self._check(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        it = await db.get_item(name)
        if not it:
            return await interaction.response.send_message("❌ Не найден.", ephemeral=True)
        await db.delete_shop_item(it["item_id"])
        await interaction.response.send_message(f"🗑️ Товар **{name}** удалён.", ephemeral=True)

    @adm.command(name="giveitem", description="Выдать предмет игроку")
    async def giveitem(self, interaction: discord.Interaction, member: discord.Member,
                       item_name: str, quantity: int = 1):
        try: self._check(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        it = await db.get_item(item_name)
        if not it:
            return await interaction.response.send_message("❌ Товар не найден.", ephemeral=True)
        await db.get_user(member.id)
        await db.add_item_to_inventory(member.id, it["item_id"], quantity)
        await interaction.response.send_message(
            f"✅ {member.mention} выдан **{it['name']}** x{quantity}.", ephemeral=True
        )

    @adm.command(name="takeitem", description="Забрать предмет у игрока")
    async def takeitem(self, interaction: discord.Interaction, member: discord.Member,
                       item_name: str, quantity: int = 1):
        try: self._check(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        it = await db.get_item(item_name)
        if not it:
            return await interaction.response.send_message("❌ Товар не найден.", ephemeral=True)
        ok = await db.remove_item_from_inventory(member.id, it["item_id"], quantity)
        if not ok:
            return await interaction.response.send_message("❌ У игрока нет столько.", ephemeral=True)
        await interaction.response.send_message(
            f"✅ У {member.mention} изъято **{it['name']}** x{quantity}.", ephemeral=True
        )

    @adm.command(name="clearinventory", description="Очистить весь инвентарь игрока")
    async def clearinventory(self, interaction: discord.Interaction, member: discord.Member):
        try: self._check(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        await db.clear_inventory(member.id)
        await interaction.response.send_message(f"🗑️ Инвентарь {member.mention} очищен.", ephemeral=True)

    @adm.command(name="inv", description="Посмотреть инвентарь игрока")
    async def inv(self, interaction: discord.Interaction, member: discord.Member):
        try: self._check(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        rows = await db.get_inventory(member.id)
        if not rows:
            return await interaction.response.send_message(f"🎒 {member.mention} пусто.", ephemeral=True)
        lines = [f"**{r['name']}** x{r['quantity']}" for r in rows]
        embed = discord.Embed(
            title=f"🎒 Инвентарь {member.display_name}",
            description="\n".join(lines),
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ================== ОТЧЁТЫ ==================
    @adm.command(name="taxreport", description="Отчёт по транзакциям")
    async def taxreport(self, interaction: discord.Interaction):
        try: self._check(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        rows = await db.transaction_report()
        if not rows:
            return await interaction.response.send_message("Транзакций нет.", ephemeral=True)
        embed = discord.Embed(title="📊 Отчёт по экономике", color=discord.Color.dark_gold())
        for r in rows:
            embed.add_field(
                name=r["kind"],
                value=f"Операций: `{r['c']}` | Оборот: `{r['total']:,}`",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @adm.command(name="userinfo", description="Информация об игроке")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member):
        try: self._check(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        u = await db.get_user(member.id)
        org = await db.get_user_org(member.id)
        party = await db.get_user_party(member.id)
        embed = discord.Embed(title=f"👤 {member}", color=discord.Color.blurple())
        embed.add_field(name="Кошелёк", value=f"`{u['wallet']:,}`", inline=True)
        embed.add_field(name="Банк", value=f"`{u['bank']:,}`", inline=True)
        embed.add_field(name="Уровень/XP", value=f"{u['level']} / {u['xp']}", inline=True)
        embed.add_field(name="Работа", value=u["job"] or "—", inline=True)
        embed.add_field(name="Организация", value=org["name"] if org else "—", inline=True)
        embed.add_field(name="Партия", value=party["name"] if party else "—", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ================== ОРГАНИЗАЦИИ ==================
    @adm.command(name="orgbudget", description="Работа с бюджетом организации")
    @app_commands.describe(name="Организация", action="set/add/sub", amount="Сумма")
    @app_commands.choices(action=[
        app_commands.Choice(name="Установить", value="set"),
        app_commands.Choice(name="Добавить", value="add"),
        app_commands.Choice(name="Вычесть", value="sub"),
    ])
    async def orgbudget(self, interaction: discord.Interaction, name: str,
                        action: app_commands.Choice[str], amount: int):
        try: self._check(interaction)
        except app_commands.CheckFailure as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        o = await db.get_org(name)
        if not o:
            return await interaction.response.send_message("❌ Не найдено.", ephemeral=True)
        if action.value == "set":
            delta = amount - o["budget"]
        elif action.value == "add":
            delta = amount
        else:
            delta = -amount
        await db.add_org_budget(o["org_id"], delta, "admin_budget", interaction.user.id, "Админ-операция")
        new = o["budget"] + delta
        await interaction.response.send_message(
            f"💰 Бюджет **{o['name']}** = `{new:,}`.", ephemeral=True
        )

    async def cog_app_command_error(self, interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            if not interaction.response.is_done():
                await interaction.response.send_message(str(error), ephemeral=True)
        else:
            raise error


async def setup(bot):
    await bot.add_cog(Admin(bot))