import discord
import io
from discord.ext import commands
from discord import app_commands
from utils.checks import is_staff
from utils.render import render_template

# ═══════════════════════════════════════════════════
# 1. РЕГИСТРАЦИЯ ГРАЖДАН
# ═══════════════════════════════════════════════════
class RegModalStep1(discord.ui.Modal, title="Регистрация (Шаг 1 из 2)"):
    surname = discord.ui.TextInput(label="Фамилия", placeholder="Иванов", max_length=50)
    name = discord.ui.TextInput(label="Имя", placeholder="Иван", max_length=50)
    patronymic = discord.ui.TextInput(label="Отчество", placeholder="Иванович", max_length=50)
    dob = discord.ui.TextInput(label="Дата рождения", placeholder="01.01.1990", max_length=20)
    pob = discord.ui.TextInput(label="Место рождения", placeholder="г. Москва", max_length=100)

    async def on_submit(self, interaction: discord.Interaction):
        interaction.client.temp_reg_data[interaction.user.id] = {
            "surname": self.surname.value, "name": self.name.value,
            "patronymic": self.patronymic.value, "dob": self.dob.value, "pob": self.pob.value,
        }
        await interaction.response.send_message("Шаг 1 из 2 завершен. Нажмите кнопку ниже.", ephemeral=True, view=NextStepView())

class RegModalStep2(discord.ui.Modal, title="Регистрация (Шаг 2 из 2)"):
    bio = discord.ui.TextInput(label="Биография", style=discord.TextStyle.paragraph, max_length=1000)
    photo_url = discord.ui.TextInput(label="Ссылка на фото", placeholder="https://...", max_length=200)

    async def on_submit(self, interaction: discord.Interaction):
        data = interaction.client.temp_reg_data.get(interaction.user.id)
        if not data: return await interaction.response.send_message("Ошибка. Начните заново.", ephemeral=True)

        await interaction.client.db.save_passport(interaction.user.id, data["surname"], data["name"], data["patronymic"], data["dob"], data["pob"], self.bio.value, self.photo_url.value)
        del interaction.client.temp_reg_data[interaction.user.id]

        settings = await interaction.client.db.get_guild_settings(interaction.guild_id)
        if not settings or not settings["review_channel_id"]:
            return await interaction.response.send_message("❌ Канал проверки не настроен.", ephemeral=True)

        review_channel = interaction.guild.get_channel(int(settings["review_channel_id"]))
        
        embed = discord.Embed(title="Новая анкета", color=discord.Color.yellow())
        embed.add_field(name="Участник", value=f"{interaction.user.mention} (`{interaction.user.id}`)")
        embed.add_field(name="ФИО", value=f"{data['surname']} {data['name']} {data['patronymic']}")
        embed.add_field(name="Дата рожд.", value=data["dob"])
        embed.add_field(name="Место рожд.", value=data["pob"])
        embed.add_field(name="Биография", value=self.bio.value, inline=False)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_image(url=self.photo_url.value)

        view = ReviewView(target_user=interaction.user)
        await review_channel.send(content=f"🔔 Проверка для {interaction.user.mention}", embed=embed, view=view)

        try: await interaction.user.send("📝 **Копия вашей анкеты:**", embed=embed)
        except: pass

        await interaction.response.send_message("✅ Анкета отправлена!", ephemeral=True)

class NextStepView(discord.ui.View):
    @discord.ui.button(label="Заполнить биографию и фото", style=discord.ButtonStyle.primary)
    async def next_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RegModalStep2())

class RegistrationView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Заполнить анкету", style=discord.ButtonStyle.green, custom_id="start_registration")
    async def start_reg(self, interaction: discord.Interaction, button: discord.ui.Button):
        passport = await interaction.client.db.get_passport(interaction.user.id)
        if passport: return await interaction.response.send_message("❌ Вы уже зарегистрированы!", ephemeral=True)
        await interaction.response.send_modal(RegModalStep1())

class ReviewView(discord.ui.View):
    def __init__(self, target_user: discord.Member):
        super().__init__(timeout=None)
        self.target_user = target_user

    @discord.ui.button(label="Принять", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children: child.disabled = True
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.set_footer(text=f"Одобрено | Проверяющий: {interaction.user.name}")

        settings = await interaction.client.db.get_guild_settings(interaction.guild_id)
        if settings and settings["start_roles"]:
            role_ids = settings["start_roles"].split(",")
            roles = [interaction.guild.get_role(int(r)) for r in role_ids if r]
            roles = [r for r in roles if r]
            try: await self.target_user.add_roles(*roles)
            except: pass

        try: await self.target_user.send("✅ Ваша анкета была **одобрена**! Добро пожаловать.")
        except: pass
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        try: await self.target_user.send("❌ Ваша анкета была **отклонена**.")
        except: pass
        await interaction.message.delete()

# ═══════════════════════════════════════════════════
# 2. НАБОР В СТАФФ
# ═══════════════════════════════════════════════════
class StaffModal(discord.ui.Modal, title="Анкета в Администрацию"):
    name = discord.ui.TextInput(label="Имя/Ник", placeholder="Иван", max_length=50)
    age = discord.ui.TextInput(label="Возраст", placeholder="18", max_length=2)
    position = discord.ui.TextInput(label="Должность", placeholder="Куратор / Модератор / Администратор / Пиар-менеджер", max_length=30)
    experience = discord.ui.TextInput(label="Опыт", style=discord.TextStyle.paragraph, max_length=1000)
    motivation = discord.ui.TextInput(label="Почему именно вы?", style=discord.TextStyle.paragraph, max_length=1000)

    async def on_submit(self, interaction: discord.Interaction):
        pos_text = self.position.value.lower()
        valid_positions = {"куратор": "curator_role", "модератор": "mod_role", "администратор": "admin_role", "пиар": "pr_role"}
        
        matched = next((v for k, v in valid_positions.items() if k in pos_text), None)
        if not matched: return await interaction.response.send_message("❌ Неверная должность. Проверьте название.", ephemeral=True)

        settings = await interaction.client.db.get_guild_settings(interaction.guild_id)
        if not settings or not settings["review_channel_id"]:
             return await interaction.response.send_message("❌ Канал проверки не настроен.", ephemeral=True)

        review_channel = interaction.guild.get_channel(int(settings["review_channel_id"]))
        
        embed = discord.Embed(title="Заявка в Стафф", color=discord.Color.purple())
        embed.add_field(name="Кандидат", value=f"{interaction.user.mention} (`{interaction.user.id}`)")
        embed.add_field(name="Имя", value=self.name.value, inline=True)
        embed.add_field(name="Возраст", value=self.age.value, inline=True)
        embed.add_field(name="Должность", value=self.position.value, inline=True)
        embed.add_field(name="Опыт", value=self.experience.value, inline=False)
        embed.add_field(name="Мотивация", value=self.motivation.value, inline=False)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        view = StaffReviewView(target_user=interaction.user, role_column=matched, pos_name=self.position.value)
        await review_channel.send(content=f"🔔 Новая заявка от {interaction.user.mention}", embed=embed, view=view)
        
        try: await interaction.user.send("📝 **Копия вашей заявки в стафф:**", embed=embed)
        except: pass
        
        await interaction.response.send_message("✅ Заявка отправлена!", ephemeral=True)

class StaffRegistrationView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Подать заявку в стафф", style=discord.ButtonStyle.blurple, custom_id="staff_reg_btn")
    async def start_staff_reg(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(StaffModal())

class StaffReviewView(discord.ui.View):
    def __init__(self, target_user: discord.Member, role_column: str, pos_name: str):
        super().__init__(timeout=None)
        self.target_user = target_user
        self.role_column = role_column 
        self.pos_name = pos_name

    @discord.ui.button(label="Принять", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children: child.disabled = True
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.set_footer(text=f"Одобрено | {interaction.user.name}")

        settings = await interaction.client.db.get_guild_settings(interaction.guild_id)
        if settings and settings[self.role_column]:
            role = interaction.guild.get_role(int(settings[self.role_column]))
            if role:
                try: await self.target_user.add_roles(role)
                except: pass

        try: await self.target_user.send(f"✅ Ваша заявка на **{self.pos_name}** одобрена!")
        except: pass
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        try: await self.target_user.send(f"❌ Ваша заявка на **{self.pos_name}** отклонена.")
        except: pass
        await interaction.message.delete()

# ═══════════════════════════════════════════════════
# 3. ЗАЯВКА НА ОРГАНИЗАЦИЮ (2 шага)
# ═══════════════════════════════════════════════════
class OrgModalStep1(discord.ui.Modal, title="Заявка на организацию (Шаг 1 из 2)"):
    name = discord.ui.TextInput(label="Название организации", placeholder="ООО 'Ромашка'", max_length=50)
    org_type = discord.ui.TextInput(label="Тип (СМИ, Бизнес, НКО...)", placeholder="СМИ", max_length=50)
    sphere = discord.ui.TextInput(label="Сфера деятельности", placeholder="IT, Торговля, Развлечения...", max_length=100)
    mission = discord.ui.TextInput(label="Миссия / Цель", style=discord.TextStyle.paragraph, max_length=500)
    staff = discord.ui.TextInput(label="Состав (участники, роли)", style=discord.TextStyle.paragraph, max_length=500)

    async def on_submit(self, interaction: discord.Interaction):
        interaction.client.temp_reg_data[f"org_{interaction.user.id}"] = {
            "name": self.name.value, "org_type": self.org_type.value,
            "sphere": self.sphere.value, "mission": self.mission.value, "staff": self.staff.value,
        }
        await interaction.response.send_message("Шаг 1 из 2 завершен. Нажмите кнопку ниже.", ephemeral=True, view=OrgNextStepView())

class OrgModalStep2(discord.ui.Modal, title="Заявка на организацию (Шаг 2 из 2)"):
    products = discord.ui.TextInput(label="Продукция / Услуги", style=discord.TextStyle.paragraph, max_length=500)
    partners = discord.ui.TextInput(label="Партнёры / Конкуренты", style=discord.TextStyle.paragraph, max_length=500)
    branding = discord.ui.TextInput(label="Символика / Основные цвета", placeholder="Логотип, цвета", max_length=200)
    ownership = discord.ui.TextInput(label="Форма собственности", placeholder="Частная, государственная...", max_length=100)
    funding = discord.ui.TextInput(label="Источники финансирования", placeholder="Инвестиции, бюджет...", max_length=200)

    async def on_submit(self, interaction: discord.Interaction):
        data = interaction.client.temp_reg_data.get(f"org_{interaction.user.id}")
        if not data: return await interaction.response.send_message("Ошибка. Начните заново.", ephemeral=True)

        settings = await interaction.client.db.get_guild_settings(interaction.guild_id)
        if not settings or not settings["review_channel_id"]:
            return await interaction.response.send_message("❌ Канал проверки не настроен.", ephemeral=True)

        review_channel = interaction.guild.get_channel(int(settings["review_channel_id"]))
        
        embed = discord.Embed(title="Заявка на создание организации", color=discord.Color.blue())
        embed.add_field(name="Владелец", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
        embed.add_field(name="Название", value=data["name"], inline=True)
        embed.add_field(name="Тип", value=data["org_type"], inline=True)
        embed.add_field(name="Сфера", value=data["sphere"], inline=True)
        embed.add_field(name="Миссия", value=data["mission"], inline=False)
        embed.add_field(name="Состав", value=data["staff"], inline=False)
        embed.add_field(name="Услуги", value=self.products.value, inline=False)
        embed.add_field(name="Партнёры", value=self.partners.value, inline=False)
        embed.add_field(name="Символика", value=self.branding.value, inline=True)
        embed.add_field(name="Собственность", value=self.ownership.value, inline=True)
        embed.add_field(name="Финансирование", value=self.funding.value, inline=True)

        view = OrgReviewView(target_user=interaction.user, data=data)
        await review_channel.send(content=f"🏢 Заявка от {interaction.user.mention}", embed=embed, view=view)

        try: await interaction.user.send("📝 **Копия вашей заявки на организацию:**", embed=embed)
        except: pass
        
        del interaction.client.temp_reg_data[f"org_{interaction.user.id}"]
        await interaction.response.send_message("✅ Заявка на организацию отправлена!", ephemeral=True)

class OrgNextStepView(discord.ui.View):
    @discord.ui.button(label="Заполнить остальные данные", style=discord.ButtonStyle.primary)
    async def next_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(OrgModalStep2())

class OrgRegistrationView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Подать заявку на организацию", style=discord.ButtonStyle.green, custom_id="start_org_registration")
    async def start_org_reg(self, interaction: discord.Interaction, button: discord.ui.Button):
        biz = await interaction.client.db.get_business(interaction.user.id)
        if biz: return await interaction.response.send_message("❌ У вас уже есть организация!", ephemeral=True)
        await interaction.response.send_modal(OrgModalStep1())

class OrgReviewView(discord.ui.View):
    def __init__(self, target_user: discord.Member, data: dict):
        super().__init__(timeout=None)
        self.target_user = target_user
        self.data = data

    @discord.ui.button(label="Принять", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children: child.disabled = True
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.set_footer(text=f"Одобрено | Проверяющий: {interaction.user.name}")

        await interaction.client.db.create_business(self.target_user.id, self.data["name"], self.data["org_type"])

        try: await self.target_user.send(f"✅ Ваша заявка на организацию **{self.data['name']}** одобрена!")
        except: pass
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        try: await self.target_user.send(f"❌ Ваша заявка на организацию **{self.data['name']}** отклонена.")
        except: pass
        await interaction.message.delete()

# ═══════════════════════════════════════════════════
# 4. КОМАНДЫ И РЕДАКТИРОВАНИЕ
# ═══════════════════════════════════════════════════
class Registration(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="passport", description="Посмотреть свой паспорт")
    async def passport(self, i: discord.Interaction, member: discord.Member = None):
        member = member or i.user
        p = await self.bot.db.get_passport(member.id)
        if not p: return await i.response.send_message("❌ Паспорт не найден.", ephemeral=True)

        settings = await self.bot.db.get_guild_settings(i.guild.id)
        state_ru = settings["state_name"] if settings and settings["state_name"] else "РОССИЙСКАЯ ФЕДЕРАЦИЯ"
        state_en = settings["state_name_en"] if settings and settings["state_name_en"] else "RUSSIAN FEDERATION"
        state_code = settings["state_code"] if settings and settings["state_code"] else "RUS"

        await i.response.defer()
        
        data = {
            "photo_url": p["photo_url"], 
            "surname": p["surname"], 
            "name": p["name"], 
            "patronymic": p["patronymic"], 
            "dob": p["dob"], 
            "pob": p["pob"],
            "state_name": f"{state_ru.upper()} / {state_en.upper()}",
            "state_code": state_code.upper(),
            "passport_number": str(member.id).zfill(10)[:10],
            "discord_id": str(member.id)
        }
        
        try:
            png = await render_template("passport.html", data)
            file = discord.File(fp=io.BytesIO(png), filename="passport.png")
            await i.followup.send(file=file)
        except Exception as e:
            await i.followup.send(f"Ошибка рендера: {e}")

    @app_commands.command(name="edit_passport", description="[STAFF] Изменить паспорт")
    @is_staff()
    async def edit_passport(self, i: discord.Interaction, member: discord.Member):
        p = await self.bot.db.get_passport(member.id)
        if not p: return await i.response.send_message("❌ Нет паспорта.", ephemeral=True)
        await i.response.send_message(f"Что изменить у {member.mention}?", view=EditSelectView(member), ephemeral=True)

    @app_commands.command(name="register", description="[STAFF] Зарегистрировать вручную")
    @is_staff()
    async def register_admin(self, i: discord.Interaction, member: discord.Member, surname: str, name: str, patronymic: str, dob: str, pob: str, bio: str, photo_url: str):
        await self.bot.db.save_passport(member.id, surname, name, patronymic, dob, pob, bio, photo_url)
        settings = await self.bot.db.get_guild_settings(i.guild.id)
        roles_text = "Нет"
        if settings and settings["start_roles"]:
            role_ids = settings["start_roles"].split(",")
            roles = [i.guild.get_role(int(r)) for r in role_ids if r]
            roles = [r for r in roles if r]
            if roles:
                try:
                    await member.add_roles(*roles)
                    roles_text = ", ".join([r.mention for r in roles])
                except: roles_text = "Ошибка"
        
        await i.response.send_message(f"✅ {member.mention} зарегистрирован. Роли: {roles_text}", ephemeral=True)

class EditSelectView(discord.ui.View):
    def __init__(self, member: discord.Member):
        super().__init__(timeout=60)
        self.member = member

    @discord.ui.select(placeholder="Поле...", options=[
        discord.SelectOption(label="Фамилия", value="surname"), discord.SelectOption(label="Имя", value="name"),
        discord.SelectOption(label="Отчество", value="patronymic"), discord.SelectOption(label="Дата", value="dob"),
        discord.SelectOption(label="Место", value="pob"), discord.SelectOption(label="Био", value="bio"),
        discord.SelectOption(label="Фото", value="photo_url"),
    ])
    async def select_field(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.send_modal(EditModal(self.member, select.values[0]))

class EditModal(discord.ui.Modal, title="Изменение"):
    value = discord.ui.TextInput(label="Новое значение", style=discord.TextStyle.paragraph)
    def __init__(self, member: discord.Member, field: str):
        super().__init__()
        self.member = member
        self.field = field

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.client.db.update_passport_field(self.member.id, self.field, self.value.value)
        await interaction.response.send_message("✅ Обновлено!", ephemeral=True)

async def setup(bot): 
    await bot.add_cog(Registration(bot))
