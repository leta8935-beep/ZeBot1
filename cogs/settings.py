import discord
from discord.ext import commands
from discord import app_commands
from utils.checks import is_staff

class Settings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup", description="[STAFF] Настроить сервер, государство и роли")
    @is_staff()
    async def setup_cmd(
        self, i: discord.Interaction, 
        review_channel: discord.TextChannel, 
        citizen_roles: str, 
        state_name_ru: str = "РОССИЙСКАЯ ФЕДЕРАЦИЯ",
        state_name_en: str = "RUSSIAN FEDERATION",
        state_code: str = "RUS",
        curator_role: discord.Role = None, 
        mod_role: discord.Role = None, 
        admin_role: discord.Role = None, 
        pr_role: discord.Role = None
    ):
        # Настройки канала и ролей
        await self.bot.db.set_guild_setting(i.guild.id, "review_channel_id", review_channel.id)
        await self.bot.db.set_guild_setting(i.guild.id, "start_roles", citizen_roles.replace(" ", ""))
        
        if curator_role: await self.bot.db.set_guild_setting(i.guild.id, "curator_role", curator_role.id)
        if mod_role: await self.bot.db.set_guild_setting(i.guild.id, "mod_role", mod_role.id)
        if admin_role: await self.bot.db.set_guild_setting(i.guild.id, "admin_role", admin_role.id)
        if pr_role: await self.bot.db.set_guild_setting(i.guild.id, "pr_role", pr_role.id)

        # Настройки государства
        await self.bot.db.set_guild_setting(i.guild.id, "state_name", state_name_ru.upper())
        await self.bot.db.set_guild_setting(i.guild.id, "state_name_en", state_name_en.upper())
        await self.bot.db.set_guild_setting(i.guild.id, "state_code", state_code.upper())

        embed = discord.Embed(title="✅ Настройки сохранены", color=0x57F287)
        embed.add_field(name="Канал проверки", value=review_channel.mention, inline=False)
        embed.add_field(name="Роли граждан", value=f"`{citizen_roles}`", inline=False)
        embed.add_field(name="Государство", value=f"{state_name_ru.upper()} / {state_name_en.upper()} ({state_code.upper()})", inline=False)
        
        roles_msg = []
        if curator_role: roles_msg.append(f"👑 Куратор: {curator_role.mention}")
        if mod_role: roles_msg.append(f"🛡️ Модератор: {mod_role.mention}")
        if admin_role: roles_msg.append(f"⚙️ Администратор: {admin_role.mention}")
        if pr_role: roles_msg.append(f"📢 Пиар-менеджер: {pr_role.mention}")
        if roles_msg:
            embed.add_field(name="Роли стаффа", value="\n".join(roles_msg), inline=False)

        await i.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="set_manager", description="[OWNER] Назначить менеджера бота")
    async def set_manager(self, i: discord.Interaction, member: discord.Member):
        if i.user.id != i.guild.owner_id: 
            return await i.response.send_message("❌ Только владелец сервера может это сделать.", ephemeral=True)
        await self.bot.db.set_guild_setting(i.guild.id, "manager_id", member.id)
        await i.response.send_message(f"👑 {member.mention} теперь менеджер бота (доступ к админ-командам).")

    @app_commands.command(name="idtext", description="[STAFF] Отправить панель")
    @is_staff()
    @app_commands.choices(message_type=[
        app_commands.Choice(name="Регистрация", value="registration"),
        app_commands.Choice(name="Набор в Стафф", value="staff_registration"),
        app_commands.Choice(name="Заявка на Организацию", value="org_registration")
    ])
    async def idtext(self, i: discord.Interaction, channel: discord.TextChannel, message_type: app_commands.Choice[str], text: str = "Нажмите кнопку ниже.", image_file: discord.Attachment = None, image_url: str = None):
        embed = discord.Embed(title="📋 Заявка", description=text, color=discord.Color.blue())
        file = None
        if image_file:
            file = await image_file.to_file()
            embed.set_image(url=f"attachment://{file.filename}")
        elif image_url: 
            embed.set_image(url=image_url)

        from cogs.registration import RegistrationView, StaffRegistrationView, OrgRegistrationView
        
        if message_type.value == "registration":
            embed.title = "📋 Регистрация Гражданина"
            view = RegistrationView()
        elif message_type.value == "staff_registration":
            embed.title = "👑 Набор в Администрацию"
            view = StaffRegistrationView()
        else:
            embed.title = "🏢 Открытие Организации"
            view = OrgRegistrationView()
        
        await channel.send(embed=embed, view=view, file=file)
        await i.response.send_message("✅ Панель отправлена!", ephemeral=True)

async def setup(bot): 
    await bot.add_cog(Settings(bot))
