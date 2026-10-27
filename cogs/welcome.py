
import io
from pathlib import Path

import discord
from discord.ext import commands
from utils.render import render_template


class Welcome(commands.Cog):
    """Красивые HTML-приветствия новых участников."""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return

        settings = await self.bot.db.get_guild_settings(member.guild.id)
        if not settings:
            return

        enabled = bool(settings["welcome_enabled"]) if settings["welcome_enabled"] is not None else False
        channel_id = settings["welcome_channel_id"]

        if not enabled or not channel_id:
            return

        channel = member.guild.get_channel(int(channel_id))
        if not isinstance(channel, discord.TextChannel):
            return

        data = {
            "server_name": member.guild.name,
            "server_icon": str(member.guild.icon.url) if member.guild.icon else "",
            "member_name": member.display_name,
            "avatar": str(member.display_avatar.url),
            "member_count": member.guild.member_count or 0,
        }

        try:
            png = await render_template("welcome.html", data)
            file = discord.File(io.BytesIO(png), filename="welcome.png")
            embed = discord.Embed(color=0x7C6CFF)
            embed.set_image(url="attachment://welcome.png")
            embed.set_footer(text=f"Добро пожаловать на {member.guild.name}")
            await channel.send(content=member.mention, embed=embed, file=file)
        except Exception:
            # Надёжный fallback, если Chromium/рендер временно недоступен.
            try:
                await channel.send(
                    content=f"👋 Добро пожаловать, {member.mention}! Рады видеть тебя на **{member.guild.name}**."
                )
            except Exception:
                pass


async def setup(bot):
    await bot.add_cog(Welcome(bot))
