import discord
from discord.ext import commands
from discord import app_commands
from utils.checks import is_staff

# Словарь для перевода названий стран (пополняй по необходимости)
STATE_TRANSLATIONS = {
    "РОССИЯ": "RUSSIAN FEDERATION",
    "РОССИЙСКАЯ ФЕДЕРАЦИЯ": "RUSSIAN FEDERATION",
    "ГЕРМАНИЯ": "GERMANY",
    "США": "UNITED STATES OF AMERICA",
    "СОЕДИНЕННЫЕ ШТАТЫ АМЕРИКИ": "UNITED STATES OF AMERICA",
    "ФРАНЦИЯ": "FRANCE",
    "ВЕЛИКОБРИТАНИЯ": "UNITED KINGDOM",
    "ИТАЛИЯ": "ITALY",
    "ЯПОНИЯ": "JAPAN",
    "КИТАЙ": "CHINA",
    "УКРАИНА": "UKRAINE",
    "КАЗАХСТАН": "KAZAKHSTAN",
}

class SettingsModal(discord.ui.Modal, title="Настройка государства"):
    state_name_ru = discord.ui.TextInput(label="Название страны (Рус.)", placeholder="РОССИЙСКАЯ ФЕДЕРАЦИЯ", max_length=50)
    state_code = discord.ui.TextInput(label="Код страны (3 буквы)", placeholder="RUS", max_length=3, min_length=3)
    state_name_en = discord.ui.TextInput(label="Название страны (Англ.)", placeholder="RUSSIAN FEDERATION (опционально)", required=False, max_length=50)

    def __init__(self, bot, guild_id, channel_id=None):
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction):
        ru_name = self.state_name_ru.value.strip().upper()
        code = self.state_code.value.strip().upper()
        en_name = self.state_name_en.value.strip().upper()

        # Если английское название не указано, пытаемся найти в словаре
        if not en_name:
            en_name = STATE_TRANSLATIONS.get(ru_name, ru_name)
            if en_name == ru_name:
                en_name = "UNKNOWN" # Если не нашли, ставим заглушку

        # Сохраняем в БД
        await self.bot.db.set_guild_setting(self.guild_id, "state_name", ru_name)
        await self.bot.db.set_guild_setting(self.guild_id, "state_code", code)
        await self.bot.db.set_guild_setting(self.guild_id, "state_name_en", en_name)

        embed = discord.Embed(title="✅ Государство обновлено", color=0x57F287)
        embed.add_field(name="Русское название", value=ru_name, inline=True)
        embed.add_field(name="Английское название", value=en_name, inline=True)
        embed.add_field(name="Код", value=code, inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class SetupView(discord.ui.View):
    def __init__(self, bot, guild_id, current_settings):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.current_settings = current_settings

    @discord.ui.button(label="Изменить государство", style=discord.ButtonStyle.primary, emoji="🌍")
    async def set_state(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SettingsModal(self.bot, self.guild_id))

    @discord.ui.button(label="Установить канал проверки", style=discord.ButtonStyle.secondary, emoji="📢")
    async def set_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Создаем View с выпадающим списком каналов
        class ChannelSelect(discord.ui.Select):
            def __init__(self, bot, guild_id):
                self.bot = bot
                self.guild_id = guild_id
                # Берем все текстовые каналы сервера
                options = [discord.SelectOption(label=f"#{ch.name}", value=str(ch.id)) for ch in interaction.guild.text_channels[:25]]
                super().__init__(placeholder="Выберите канал...", options=options)

            async def callback(self, select_interaction: discord.Interaction):
                channel_id = int(self.values[0])
                await self.bot.db.set_guild_setting(self.guild_id, "review_channel_id", channel_id)
                await select_interaction.response.send_message(f"✅ Канал проверки установлен: <#{channel_id}>", ephemeral=True)

        view = discord.ui.View()
        view.add_item(ChannelSelect(self.bot, self.guild_id))
        await interaction.response.send_message("Выберите канал для проверки анкет:", view=view, ephemeral=True)

    @discord.ui.button(label="Настроить роли", style=discord.ButtonStyle.secondary, emoji="🎭")
    async def set_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Открываем модалку для ввода ID ролей (через запятую)
        class RolesModal(discord.ui.Modal, title="Настройка ролей"):
            citizen_roles = discord.ui.TextInput(label="ID ролей граждан (через запятую)", placeholder="123456789,987654321", required=False)
            curator_role = discord.ui.TextInput(label="ID роли Куратора", placeholder="123456789", required=False)
            mod_role = discord.ui.TextInput(label="ID роли Модератора", placeholder="123456789", required=False)
            admin_role = discord.ui.TextInput(label="ID роли Администратора", placeholder="123456789", required=False)
            pr_role = discord.ui.TextInput(label="ID роли Пиар-менеджера", placeholder="123456789", required=False)

            def __init__(self, bot, guild_id):
                super().__init__()
                self.bot = bot
                self.guild_id = guild_id

            async def on_submit(self, modal_interaction: discord.Interaction):
                if self.citizen_roles.value:
                    await self.bot.db.set_guild_setting(self.guild_id, "start_roles", self.citizen_roles.value.replace(" ", ""))
                if self.curator_role.value:
                    await self.bot.db.set_guild_setting(self.guild_id, "curator_role", int(self.curator_role.value))
                if self.mod_role.value:
                    await self.bot.db.set_guild_setting(self.guild_id, "mod_role", int(self.mod_role.value))
                if self.admin_role.value:
                    await self.bot.db.set_guild_setting(self.guild_id, "admin_role", int(self.admin_role.value))
                if self.pr_role.value:
                    await self.bot.db.set_guild_setting(self.guild_id, "pr_role", int(self.pr_role.value))
                
                await modal_interaction.response.send_message("✅ Роли сохранены!", ephemeral=True)

        await interaction.response.send_modal(RolesModal(self.bot, self.guild_id))

    @discord.ui.button(label="Готово", style=discord.ButtonStyle.success, emoji="✅")
    async def finish(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="✅ Настройка завершена. Меню закрыто.", view=None)

class Settings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup", description="[STAFF] Интерактивное меню настройки сервера")
    @is_staff()
    async def setup_cmd(self, i: discord.Interaction):
        # Получаем текущие настройки
        settings = await self.bot.db.get_guild_settings(i.guild.id)
        
        # Формируем информацию о текущем состоянии
        state_ru = settings["state_name"] if settings and settings["state_name"] else "Не установлено"
        state_en = settings["state_name_en"] if settings and settings["state_name_en"] else "Не установлено"
        state_code = settings["state_code"] if settings and settings["state_code"] else "Не установлено"
        review_channel = f"<#{settings['review_channel_id']}>" if settings and settings["review_channel_id"] else "Не установлен"
        start_roles = f"`{settings['start_roles']}`" if settings and settings["start_roles"] else "Не установлены"

        embed = discord.Embed(title="⚙️ Меню настройки", color=0x5865F2)
        embed.description = "Выберите, что вы хотите изменить:"
        embed.add_field(name="🌍 Государство", value=f"{state_ru} / {state_en} ({state_code})", inline=False)
        embed.add_field(name="📢 Канал проверки", value=review_channel, inline=False)
        embed.add_field(name="🎭 Роли граждан", value=start_roles, inline=False)
        embed.set_footer(text="Все изменения сохраняются в базе данных автоматически.")

        view = SetupView(self.bot, i.guild.id, settings)
        await i.response.send_message(embed=embed, view=view, ephemeral=True)

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
