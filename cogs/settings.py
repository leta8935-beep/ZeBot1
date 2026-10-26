import discord
from discord.ext import commands
from discord import app_commands
from utils.checks import is_staff

STATE_TRANSLATIONS = {
    "РОССИЯ": "RUSSIAN FEDERATION", "РОССИЙСКАЯ ФЕДЕРАЦИЯ": "RUSSIAN FEDERATION",
    "ГЕРМАНИЯ": "GERMANY", "США": "UNITED STATES OF AMERICA", "ФРАНЦИЯ": "FRANCE",
    "ВЕЛИКОБРИТАНИЯ": "UNITED KINGDOM", "ИТАЛИЯ": "ITALY", "ЯПОНИЯ": "JAPAN",
    "КИТАЙ": "CHINA", "УКРАИНА": "UKRAINE", "КАЗАХСТАН": "KAZAKHSTAN",
}

class StateModal(discord.ui.Modal, title="Настройка государства"):
    ru = discord.ui.TextInput(label="Название (Рус.)", placeholder="РОССИЙСКАЯ ФЕДЕРАЦИЯ", max_length=50)
    code = discord.ui.TextInput(label="Код (3 буквы)", placeholder="RUS", max_length=3, min_length=3)
    en = discord.ui.TextInput(label="Название (Англ., опционально)", required=False, max_length=50)

    def __init__(self, bot, guild_id):
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        ru_name = self.ru.value.strip().upper()
        code = self.code.value.strip().upper()
        en_name = self.en.value.strip().upper() or STATE_TRANSLATIONS.get(ru_name, "UNKNOWN")
        
        await self.bot.db.set_guild_setting(self.guild_id, "state_name", ru_name)
        await self.bot.db.set_guild_setting(self.guild_id, "state_code", code)
        await self.bot.db.set_guild_setting(self.guild_id, "state_name_en", en_name)
        
        embed = discord.Embed(title="✅ Государство обновлено", color=0x57F287)
        embed.add_field(name="Название", value=f"{ru_name} / {en_name}", inline=False)
        embed.add_field(name="Код", value=code, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class CurrencyModal(discord.ui.Modal, title="Настройка валюты"):
    currency = discord.ui.TextInput(label="Символ или название валюты", placeholder="RUB или ₽", max_length=10)

    def __init__(self, bot, guild_id):
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        await self.bot.db.set_guild_setting(self.guild_id, "currency", self.currency.value.strip())
        await interaction.response.send_message(f"✅ Валюта изменена на **{self.currency.value.strip()}**", ephemeral=True)

class ChannelSelect(discord.ui.Select):
    def __init__(self, bot, guild_id, channels):
        options = [discord.SelectOption(label=f"#{ch.name}", value=str(ch.id)) for ch in channels[:25]]
        super().__init__(placeholder="Выберите канал проверки...", options=options)
        self.bot = bot
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        await self.bot.db.set_guild_setting(self.guild_id, "review_channel_id", int(self.values[0]))
        await interaction.response.send_message(f"✅ Канал проверки установлен: <#{self.values[0]}>", ephemeral=True)

class RolesModal(discord.ui.Modal, title="Настройка ролей"):
    citizen = discord.ui.TextInput(label="ID ролей граждан (через запятую)", required=False)
    curator = discord.ui.TextInput(label="ID Куратора", required=False)
    mod = discord.ui.TextInput(label="ID Модератора", required=False)
    admin = discord.ui.TextInput(label="ID Администратора", required=False)
    pr = discord.ui.TextInput(label="ID Пиар-менеджера", required=False)

    def __init__(self, bot, guild_id):
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        if self.citizen.value: await self.bot.db.set_guild_setting(self.guild_id, "start_roles", self.citizen.value.replace(" ", ""))
        for field, col in [(self.curator, "curator_role"), (self.mod, "mod_role"), (self.admin, "admin_role"), (self.pr, "pr_role")]:
            if field.value: await self.bot.db.set_guild_setting(self.guild_id, col, int(field.value))
        await interaction.response.send_message("✅ Роли сохранены!", ephemeral=True)

class SetupView(discord.ui.View):
    def __init__(self, bot, guild_id, settings):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.settings = settings

    @discord.ui.button(label="Государство", style=discord.ButtonStyle.primary, emoji="🌍")
    async def state_btn(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.send_modal(StateModal(self.bot, self.guild_id))

    @discord.ui.button(label="Валюта", style=discord.ButtonStyle.primary, emoji="💵")
    async def currency_btn(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.send_modal(CurrencyModal(self.bot, self.guild_id))

    @discord.ui.button(label="Канал проверки", style=discord.ButtonStyle.secondary, emoji="📢")
    async def channel_btn(self, i: discord.Interaction, b: discord.ui.Button):
        view = discord.ui.View()
        view.add_item(ChannelSelect(self.bot, self.guild_id, i.guild.text_channels))
        await i.response.send_message("Выберите канал:", view=view, ephemeral=True)

    @discord.ui.button(label="Роли", style=discord.ButtonStyle.secondary, emoji="🎭")
    async def roles_btn(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.send_modal(RolesModal(self.bot, self.guild_id))

    @discord.ui.button(label="Закрыть", style=discord.ButtonStyle.danger, emoji="✖️")
    async def close_btn(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.edit_message(content="Настройка завершена.", view=None)

class Settings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup", description="[STAFF] Настройка сервера")
    @is_staff()
    async def setup_cmd(self, i: discord.Interaction):
        s = await self.bot.db.get_guild_settings(i.guild.id)
        ru = s["state_name"] if s else "Не задано"
        code = s["state_code"] if s else "Не задано"
        curr = s["currency"] if s else "RUB"
        ch = f"<#{s['review_channel_id']}>" if s and s["review_channel_id"] else "Не задано"
        
        embed = discord.Embed(title="⚙️ Настройка сервера", color=0x5865F2)
        embed.description = "Нажмите на кнопку ниже, чтобы изменить параметр."
        embed.add_field(name="🌍 Государство", value=f"{ru} ({code})", inline=False)
        embed.add_field(name="💵 Валюта", value=curr, inline=False)
        embed.add_field(name="📢 Канал проверки", value=ch, inline=False)
        embed.set_footer(text="Все изменения применяются сразу.")
        
        await i.response.send_message(embed=embed, view=SetupView(self.bot, i.guild.id, s), ephemeral=True)

    @app_commands.command(name="set_manager", description="[OWNER] Назначить менеджера")
    async def set_manager(self, i: discord.Interaction, member: discord.Member):
        if i.user.id != i.guild.owner_id:
            return await i.response.send_message("Только владелец сервера.", ephemeral=True)
        await self.bot.db.set_guild_setting(i.guild.id, "manager_id", member.id)
        await i.response.send_message(f"{member.mention} теперь менеджер бота.", ephemeral=True)

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
        elif image_url: embed.set_image(url=image_url)

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
        await i.response.send_message("✅ Отправлено!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Settings(bot))
