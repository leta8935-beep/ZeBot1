import discord
from discord.ext import commands
from discord import app_commands

from utils.checks import is_staff


def fmt(n: int) -> str:
    return f"{int(n):,}".replace(",", " ")


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="admin", description="[STAFF] Управление балансом игроков")
    @app_commands.choices(action=[
        app_commands.Choice(name="➕ Добавить", value="add"),
        app_commands.Choice(name="➖ Убрать", value="remove"),
        app_commands.Choice(name="🔄 Обновить", value="update"),
    ])
    @is_staff()
    async def admin(self, i: discord.Interaction, action: app_commands.Choice[str],
                    member: discord.Member, amount: int):
        if amount < 0:
            return await i.response.send_message("❌ Сумма должна быть неотрицательной.", ephemeral=True)

        await self.bot.db.get_user(member.id)
        if action.value == "add":
            await self.bot.db.update_wallet(member.id, amount)
        elif action.value == "remove":
            await self.bot.db.update_wallet(member.id, -amount)
        else:
            await self.bot.db.set_wallet(member.id, amount)

        u = await self.bot.db.get_user(member.id)
        embed = discord.Embed(
            title="Баланс изменён",
            color=0xEB459E,
            description=f"**Игрок:** {member.mention}\n**Новый баланс:** {fmt(u['wallet'])} 💰",
        )
        await i.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="create_org", description="[STAFF] Создать организацию для игрока")
    @is_staff()
    async def create_org(self, i: discord.Interaction, member: discord.Member,
                         name: str, org_type: str = "Бизнес"):
        await self.bot.db.create_organization(
            member.id, name.strip(), org_type.strip(), "Не указана", ""
        )
        await i.response.send_message(
            f"✅ Организация **{name}** создана для {member.mention}.", ephemeral=True
        )

    @app_commands.command(name="edit_org", description="[STAFF] Изменить данные организации")
    @is_staff()
    async def edit_org(
        self,
        i: discord.Interaction,
        organization: str,
        name: str | None = None,
        org_type: str | None = None,
        sphere: str | None = None,
        logo_url: str | None = None,
    ):
        org = await self.bot.db.get_organization_by_name(organization)
        if not org:
            return await i.response.send_message("Организация не найдена.", ephemeral=True)

        await self.bot.db.update_organization(
            org["org_id"],
            name=name.strip() if name else None,
            org_type=org_type.strip() if org_type else None,
            sphere=sphere.strip() if sphere else None,
            logo_url=logo_url.strip() if logo_url else None,
        )
        await i.response.send_message(
            f"✅ Организация **{org['name']}** изменена.", ephemeral=True
        )

    @app_commands.command(name="delete_org", description="[STAFF] Удалить организацию")
    @is_staff()
    async def delete_org(self, i: discord.Interaction, organization: str):
        org = await self.bot.db.get_organization_by_name(organization)
        if not org:
            return await i.response.send_message("Организация не найдена.", ephemeral=True)

        await self.bot.db.delete_organization(org["org_id"])
        await i.response.send_message(
            f"🗑️ Организация **{org['name']}** удалена.", ephemeral=True
        )

    @app_commands.command(name="org_balance", description="[STAFF] Изменить бюджет организации")
    @app_commands.choices(action=[
        app_commands.Choice(name="➕ Пополнить", value="add"),
        app_commands.Choice(name="➖ Списать", value="remove"),
        app_commands.Choice(name="🔄 Установить", value="set"),
    ])
    @is_staff()
    async def org_balance(self, i: discord.Interaction, organization: str,
                          action: app_commands.Choice[str], amount: int):
        if amount < 0:
            return await i.response.send_message("Сумма не может быть отрицательной.", ephemeral=True)

        org = await self.bot.db.get_organization_by_name(organization)
        if not org:
            return await i.response.send_message("Организация не найдена.", ephemeral=True)

        if action.value == "add":
            new_balance = org["balance"] + amount
            await self.bot.db.add_to_org_balance(org["org_id"], amount)
        elif action.value == "remove":
            new_balance = max(0, org["balance"] - amount)
            await self.bot.db.remove_from_org_balance(org["org_id"], amount)
        else:
            new_balance = amount
            await self.bot.db.update_organization(org["org_id"], balance=amount)

        await i.response.send_message(
            f"✅ Бюджет **{org['name']}**: **{fmt(new_balance)}** RUB.",
            ephemeral=True,
        )

    @app_commands.command(name="org_owner", description="[STAFF] Передать организацию другому владельцу")
    @is_staff()
    async def org_owner(self, i: discord.Interaction, organization: str,
                        member: discord.Member):
        org = await self.bot.db.get_organization_by_name(organization)
        if not org:
            return await i.response.send_message("Организация не найдена.", ephemeral=True)

        await self.bot.db.transfer_organization(org["org_id"], member.id)
        await i.response.send_message(
            f"👑 Организация **{org['name']}** теперь принадлежит {member.mention}.",
            ephemeral=True,
        )

    @app_commands.command(name="org_member", description="[STAFF] Добавить участника в организацию")
    @is_staff()
    async def org_member(self, i: discord.Interaction, organization: str,
                         member: discord.Member, rank: str = "Сотрудник"):
        org = await self.bot.db.get_organization_by_name(organization)
        if not org:
            return await i.response.send_message("Организация не найдена.", ephemeral=True)

        await self.bot.db.add_org_member(org["org_id"], member.id, rank.strip() or "Сотрудник")
        await i.response.send_message(
            f"✅ {member.mention} добавлен в **{org['name']}** как **{rank}**.",
            ephemeral=True,
        )

    @app_commands.command(name="org_remove_member", description="[STAFF] Удалить участника из организации")
    @is_staff()
    async def org_remove_member(self, i: discord.Interaction, organization: str,
                                member: discord.Member):
        org = await self.bot.db.get_organization_by_name(organization)
        if not org:
            return await i.response.send_message("Организация не найдена.", ephemeral=True)

        await self.bot.db.remove_org_member(org["org_id"], member.id)
        await i.response.send_message(
            f"✅ {member.mention} удалён из **{org['name']}**.",
            ephemeral=True,
        )

    async def cog_app_command_error(self, i, error):
        if isinstance(error, app_commands.CheckFailure):
            if not i.response.is_done():
                await i.response.send_message(f"🚫 {error}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Admin(bot))
