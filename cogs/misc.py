import logging
import asyncio
import base64
import os
import re
import unicodedata
import psutil
import platform

import discord
from discord import app_commands, ui
from discord.ext import commands, tasks

from .utils import checks
from .utils.emojis import tick
from .utils.common import trim_str, plur
from .utils.context import Context
from .utils.views import GlobalGuildSwitchView, GuildInfoView, handle_view_edit
from .utils.emojis import Emojis
from bot import Woolinator


log = logging.getLogger(__name__)


GITHUB_URL = "https://github.com/Woolyenough/The-Woolinator"
PRIVACY_POLICY_URL = f"{GITHUB_URL}/blob/main/PRIVACY.md"


# Public flag (badge) -> (emoji, display name). Ordered as they should appear next to a user.
USER_FLAGS = {
    "staff": (Emojis.Flags.staff, "Discord Staff"),
    "partner": (Emojis.Flags.partner, "Partnered Server Owner"),
    "hypesquad": (Emojis.Flags.hypesquad, "HypeSquad Events"),
    "hypesquad_bravery": (Emojis.Flags.hypesquad_bravery, "HypeSquad Bravery"),
    "hypesquad_brilliance": (Emojis.Flags.hypesquad_brilliance, "HypeSquad Brilliance"),
    "hypesquad_balance": (Emojis.Flags.hypesquad_balance, "HypeSquad Balance"),
    "bug_hunter": (Emojis.Flags.bug_hunter, "Bug Hunter"),
    "bug_hunter_level_2": (Emojis.Flags.bug_hunter_level_2, "Bug Hunter Level 2"),
    "early_supporter": (Emojis.Flags.early_supporter, "Early Supporter"),
    "verified_bot_developer": (Emojis.Flags.verified_bot_developer, "Early Verified Bot Developer"),
    "discord_certified_moderator": (Emojis.Flags.discord_certified_moderator, "Moderator Programs Alumni"),
}

# Presence status -> (emoji, label). Only resolvable for members (Users carry no presence).
STATUS_DISPLAY = {
    discord.Status.online: (Emojis.Presence.online, "Online"),
    discord.Status.idle: (Emojis.Presence.idle, "Idle"),
    discord.Status.dnd: (Emojis.Presence.dnd, "Do Not Disturb"),
    discord.Status.offline: (Emojis.Presence.offline, "Offline"),
}


class DataReviewView(ui.View):
    """ Attached to `/data-review`; offers a one-click wipe of everything the bot stores about the user. """

    def __init__(self, cog: "Misc", author_id: int, has_data: bool, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.author_id = author_id
        self.message = None
        self.delete_all.disabled = not has_data

    @ui.button(label="Delete all my data", emoji="\U0001f5d1", style=discord.ButtonStyle.danger)
    async def delete_all(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(
            title="Delete everything?",
            description=(
                f"{Emojis.warn} This permanently deletes **all** the forementioned data the bot stores about you across **every** server. This cannot be undone."
            ),
            colour=discord.Colour.red(),
        )
        confirm = ConfirmWipeView(self.cog, self.author_id)
        confirm.message = self.message
        await interaction.response.edit_message(embed=embed, view=confirm)
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author_id and interaction.user.id != self.author_id:
            await interaction.response.send_message("not your button to press ,-,", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await handle_view_edit(self.message, view=self)


class ConfirmWipeView(ui.View):
    """ Final yes/no confirmation before wiping a user's data from `/data-review`. """

    def __init__(self, cog: "Misc", author_id: int, timeout: int = 60):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.author_id = author_id
        self.message = None

    @ui.button(label="Yes, delete everything", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        await self.cog._delete_user_data(interaction.user.id)
        embed = discord.Embed(
            description=f"{tick(True)} All your stored data has been deleted.",
            colour=discord.Colour.green(),
        )
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()

    @ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        embed, has_data = await self.cog._build_data_embed(interaction.user)
        view = DataReviewView(self.cog, self.author_id, has_data=has_data)
        view.message = self.message
        await interaction.response.edit_message(embed=embed, view=view)
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author_id and interaction.user.id != self.author_id:
            await interaction.response.send_message("not your button to press ,-,", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await handle_view_edit(self.message, view=self)


class Misc(commands.Cog, name="Miscellaneous", description="Uncategorised stuff"):

    def __init__(self, bot: Woolinator) -> None:
        self.bot: Woolinator = bot
        self._last_member = None

        self.process = psutil.Process()

        # Built-in logo names from `fastfetch --list-logos autocompletion`, stored one per line
        with open("resources/os-logos.txt", 'r') as f:
            self.available_os_ascii = f.read().splitlines()

        self.ctx_count = app_commands.ContextMenu(name="Word & Character Count", callback=self.ctx_menu_count)
        self.bot.tree.add_command(self.ctx_count)

        self.deleted_messages: dict[int, discord.Message] = {}
        self.edited_messages: dict[int, tuple[discord.Message, discord.Message]] = {}

    async def cog_load(self):
        if not self.rotate_status.is_running(): self.rotate_status.start()

    async def cog_unload(self):
        self.rotate_status.cancel()
        self.bot.tree.remove_command(self.ctx_count.name, type=self.ctx_count.type)

    @property
    def emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name="misc", id=1337679601522049054)

    # --- Tasks ---

    @tasks.loop(minutes=5)
    async def rotate_status(self):
        """ A task to change the bot status at intervals. """

        await self.bot.wait_until_ready()
        await self.bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(self.bot.users):,} users in {len(self.bot.guilds):,} guilds 🤙😎"
            )
        )

    # --- Listeners ---

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild:
            self.deleted_messages[message.channel.id] = message

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if after.guild and before.content != after.content:
            self.edited_messages[before.channel.id] = (before, after)

    # --- Commands ---

    @commands.hybrid_command(name="about", description="About myself!")
    async def about(self, ctx: Context):
        total_lines, total_chars, total_files = [0] * 3

        for dirpath, dirnames, filenames in os.walk('.'):
            dirnames[:] = [d for d in dirnames if d not in {".venv", "__pycache__"}]

            for file in filenames:
                if file.endswith('.py'):
                    file_path = os.path.join(dirpath, file)

                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        total_lines += content.count('\n') + 1  # +1 for last line without \n
                        total_chars += len(content)
                        total_files += 1
        
        memory_usage = self.process.memory_full_info().uss / 1024**2
        #total_memory = psutil.virtual_memory().total / 1024**2
        #mem_pc = (memory_usage / total_memory) * 100
        cpu_usage = self.process.cpu_percent() / psutil.cpu_count()

        description = [
            f":wave: Hi! I am a private, open source bot made by [**`@woolyenough`**](https://discord.com/users/{self.bot.owner.id}).",
            "",
            f"**Uptime:** <t:{round(self.bot.uptime.timestamp())}:R>", 
            f"**Code:** {total_lines:,} lines / {total_chars:,} chars / {total_files} .py files",
            f"**Created:** <t:{round(self.bot.user.created_at.timestamp())}:R>",
            "",
        ]

        embed = discord.Embed(title=str(self.bot.user), description='\n'.join(description), colour=0xffe3be)
        embed.set_author(name=f"@{self.bot.owner.name}", icon_url=self.bot.owner.display_avatar.url)
        embed.add_field(name="**Exposure:**", value=f"> {len(self.bot.guilds)} Guilds\n> {len(self.bot.users):,} Users")
        embed.add_field(name="**Process:**", value=f"> {cpu_usage:.2f}% CPU\n> {memory_usage:.2f} MiB Mem")
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text=f"Python {platform.python_version()}  ▪  discord.py v{discord.__version__}", icon_url="https://wooly.wtf/files/The-Woolinator/python.png")

        view = ui.View()\
            .add_item(ui.Button(style=discord.ButtonStyle.link, label="GitHub repository", url=GITHUB_URL))\
            .add_item(ui.Button(style=discord.ButtonStyle.link, label="Privacy Policy", url=PRIVACY_POLICY_URL))
        await ctx.reply(embed=embed, view=view)

    @commands.hybrid_command(name="privacy", description="How the bot handles your data")
    async def privacy(self, ctx: Context):
        description = [
            "I only store data for features you choose to use, and I never store your messages or ask for credentials. The Woolinator adheres to Discord's Developer Terms & Policy.",
            "",
            f"You can view and remove most of your data yourself, at any time, with the command: {self.bot.cmd_mention('data-review')}",
            "",
            f"For any questions, contact `@{self.bot.owner.name}`.",
        ]
        embed = discord.Embed(title="Privacy", description='\n'.join(description), colour=0xffe3be)
        view = ui.View()\
            .add_item(ui.Button(style=discord.ButtonStyle.link, label="Privacy Policy", url=PRIVACY_POLICY_URL))
        await ctx.reply(embed=embed, view=view, ephemeral=True)

    def _guild_label(self, guild_id: int) -> str:
        """ Resolve a guild ID to its name, falling back to the raw ID when the bot has left it. """
        guild = self.bot.get_guild(guild_id)
        return guild.name if guild else f"Unknown server (`{guild_id}`)"

    async def _build_data_embed(self, user: discord.User|discord.Member) -> tuple[discord.Embed, bool]:
        """ Summarise everything stored about `user`; returns the embed and whether any data exists. """
        async with self.bot.get_cursor() as cursor:
            await cursor.execute("SELECT COUNT(*) FROM reminders WHERE user_id = %s", (user.id,))
            reminder_count = (await cursor.fetchone())[0]

            await cursor.execute("SELECT guild_id FROM birthdays WHERE user_id = %s", (user.id,))
            birthday_guilds = [row[0] for row in await cursor.fetchall()]

            await cursor.execute("SELECT guild_id, COUNT(*) FROM tags WHERE user_id = %s GROUP BY guild_id", (user.id,))
            tag_guilds = await cursor.fetchall()

            await cursor.execute("SELECT prefix FROM prefixes WHERE entity_id = %s AND is_guild = 0", (user.id,))
            prefix_row = await cursor.fetchone()

        tag_total = sum(count for _, count in tag_guilds)
        has_data = bool(reminder_count or birthday_guilds or tag_guilds or (prefix_row and prefix_row[0]))

        lines = []

        # Reminders are global (not tied to a server)
        if reminder_count:
            lines.append(f"⏰ You have **{reminder_count}** reminder{plur(reminder_count)} saved: {self.bot.cmd_mention('reminders')}")
        else:
            lines.append("⏰ You have no reminders saved.")

        # Birthdays are stored per-server
        if birthday_guilds:
            names = '\n'.join(f"> {self._guild_label(gid)}" for gid in birthday_guilds)
            lines.append(f"🎂 Your birthday is stored in **{len(birthday_guilds)}** server{plur(len(birthday_guilds))}:\n{names}")
        else:
            lines.append("🎂 Your birthday isn't stored anywhere.")

        # Tags are owned per-server
        if tag_guilds:
            names = '\n'.join(f"> {self._guild_label(gid)} - {count} tag{plur(count)}" for gid, count in tag_guilds)
            lines.append(f"🏷️ You own **{tag_total}** tag{plur(tag_total)} across **{len(tag_guilds)}** server{plur(len(tag_guilds))}:\n{names}")
        else:
            lines.append("🏷️ You don't own any tags.")

        # Personal prefix
        if prefix_row and prefix_row[0]:
            lines.append(f"⌨️ Your personal prefix is `{prefix_row[0]}`: {self.bot.cmd_mention('prefix')}")


        embed = discord.Embed(title="Your data", description='\n\n'.join(lines), colour=0xffe3be)
        embed.set_author(name=f"@{user.name}", icon_url=user.display_avatar.url)
        embed.set_footer(text="Use the button below to delete everything." if has_data
                         else "The bot has no personal data stored about you.")
        return embed, has_data

    async def _delete_user_data(self, user_id: int) -> None:
        """ Remove all personal data of a user from the database. """
        async with self.bot.get_cursor() as cursor:
            await cursor.execute("SELECT id FROM reminders WHERE user_id = %s", (user_id,))
            reminder_ids = [row[0] for row in await cursor.fetchall()]

            await cursor.execute("DELETE FROM reminders WHERE user_id = %s", (user_id,))
            await cursor.execute("DELETE FROM birthdays WHERE user_id = %s", (user_id,))
            await cursor.execute("DELETE FROM tags WHERE user_id = %s", (user_id,))
            await cursor.execute("DELETE FROM prefixes WHERE entity_id = %s AND is_guild = 0", (user_id,))

        # Cancel any pending in-memory reminder timers so deleted reminders don't still fire
        reminder_cog = self.bot.get_cog("Reminders")
        if reminder_cog is not None:
            for rid in reminder_ids:
                task = reminder_cog.asyncio_timers.pop(rid, None)
                if task is not None:
                    task.cancel()

        # Drop the cached personal prefix so it stops applying immediately
        self.bot.user_prefixes.pop(user_id, None)

    @commands.hybrid_command(name="data-review", description="Review and delete the data stored about you")
    async def data_review(self, ctx: Context):
        embed, has_data = await self._build_data_embed(ctx.author)
        view = DataReviewView(self, ctx.author.id, has_data=has_data)
        view.message = await ctx.reply(embed=embed, view=view, ephemeral=True)

    @commands.hybrid_command(name="snipe", description="Check the last deleted message in the current channel")
    @commands.guild_only()
    async def snipe(self, ctx: Context):
        m = self.deleted_messages.get(ctx.channel.id, None)

        if m is None:
            embed = discord.Embed(description="*There is nothing to snipe!*", colour=0xe6c4f5)
            await ctx.reply(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(description=m.content, timestamp=m.created_at, colour=0xf93838)
        embed.set_author(name=f"@{m.author.name}", icon_url=m.author.display_avatar.url)

        if m.stickers:
            embed.set_image(url=m.stickers[0].url)

        if m.attachments:
            a = [f"- [{a.filename}]({a.proxy_url})" for a in m.attachments]
            embed.add_field(name="Attachments", value='\n'.join(a))

        await ctx.reply(embed=embed)

    @commands.hybrid_command(name="esnipe", aliases=["editsnipe"], description="Check the last edited message in the current channel")
    @commands.guild_only()
    async def esnipe(self, ctx: Context):
        before, after = self.edited_messages.get(ctx.channel.id, (None, None))

        if after is None:
            embed = discord.Embed(description="*There is nothing to edit snipe!*", colour=0xe6c4f5)
            await ctx.reply(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(timestamp=after.created_at, colour=0xff8d42)
        embed.add_field(name="Before:", value=trim_str(before.content, 1024), inline=False)
        embed.add_field(name="After:", value=trim_str(after.content, 1024), inline=False)
        embed.set_author(name=f"@{after.author.name}", icon_url=after.author.display_avatar.url)

        view = ui.View()\
            .add_item(ui.Button(style=discord.ButtonStyle.link, label="Jump to Message", url=after.jump_url))
        await ctx.reply(embed=embed, view=view)

    @commands.hybrid_command(name="hello", description="Says hello")
    async def hello(self, ctx: Context):
        if self._last_member is None or self._last_member.id != ctx.author.id:
            await ctx.reply(f"Hello, {ctx.author.name}! :wave:")
        else:
            await ctx.reply(f"Hello, {ctx.author.name}... again :face_with_raised_eyebrow:")
        self._last_member = ctx.author

    @commands.hybrid_command(name="charinfo", description="Get information about entered characters")
    @app_commands.describe(characters="The characters you want to get info about (max: 25)")
    async def charinfo(self, ctx: Context, *, characters: commands.Range[str, 1, 25]):

        def to_string(c):
            digit = f"{ord(c):x}"
            name = unicodedata.name(c, "Name not found.")
            c = '\\`' if c == '`' else c
            return f"{c} **\N{EM DASH}** [`\\U{digit:>08}`](http://www.fileformat.info/info/unicode/char/{digit}): {name}"

        msg = '\n'.join(map(to_string, characters))
        await ctx.send(embed=discord.Embed(description=trim_str(msg, 4096), colour=discord.Colour.random()))

    @commands.hybrid_command(name="user", aliases=["member", "whois"], description="Get information about a user")
    @app_commands.describe(user="The user you want to get the info of")
    async def user(self, ctx: Context, user: discord.Member|discord.User = commands.Author):

        # --- Global embed ---
        global_avatar = user.avatar or user.display_avatar
        global_embed = discord.Embed(title=user.display_name, colour=discord.Colour.blurple())
        global_embed.set_author(name=f"@{user.name}", icon_url=global_avatar.url)

        global_lines = [
            f"**Mention:** {user.mention}",
            f"**Created:** <t:{round(user.created_at.timestamp())}:f> (<t:{round(user.created_at.timestamp())}:R>)",
        ]

        # Public flags (badges): "<emoji> Name", comma-separated
        badges = ', '.join(f"{emoji} {name}" for flag, (emoji, name) in USER_FLAGS.items() if getattr(user.public_flags, flag, False))
        if badges:
            global_lines.append(f"**Flags:** {badges}")

        # Visibility (presence) - only available for members
        if isinstance(user, discord.Member):
            emoji, label = STATUS_DISPLAY.get(user.status, (Emojis.Presence.offline, "Offline"))
            platforms = []
            if user.desktop_status != discord.Status.offline: platforms.append("Desktop")
            if user.mobile_status != discord.Status.offline: platforms.append("Mobile")
            if user.web_status != discord.Status.offline: platforms.append("Web")
            visibility = f"{emoji} {label}" + (f" ({', '.join(platforms)})" if platforms else "")
            global_lines.append(f"**Visibility:** {visibility}")

        if user.public_flags.spammer:
            global_lines.append(f"\n{Emojis.warn} This account is flagged as a spammer by Discord.")

        global_embed.description = '\n'.join(global_lines)

        # Activity (presence) - only available for members
        if isinstance(user, discord.Member) and user.activities:
            activities = []
            for activity in user.activities:
                if isinstance(activity, discord.Spotify):
                    activities.append(f"🎵 Listening to **{activity.title}** by {activity.artist}")
                elif isinstance(activity, discord.Streaming):
                    activities.append(f"📺 Streaming **[{activity.name}]({activity.url})**")
                elif isinstance(activity, discord.Game):
                    activities.append(f"🎮 Playing **{activity.name}**")
                elif isinstance(activity, discord.CustomActivity):
                    emoji = str(activity.emoji) + " " if activity.emoji else ""
                    activities.append(f"{emoji}{activity.name or 'Custom Status'}")
                elif activity.name:
                    activities.append(f"**{activity.name}**")
            if activities:
                global_embed.add_field(name="Activity", value='\n'.join(activities[:3]), inline=False)

        global_embed.set_footer(text=f"User ID: {user.id}")

        # --- Guild embed (member only) ---
        guild_embed = None
        if isinstance(user, discord.Member) and ctx.guild:
            guild_embed = discord.Embed(title=user.display_name, colour=user.color if user.color.value != 0 else discord.Colour.blurple())
            guild_embed.set_author(name=f"@{user.name}", icon_url=user.display_avatar.url)
            # Only show a thumbnail when the member has a guild-specific avatar (differs from global)
            if user.guild_avatar:
                guild_embed.set_thumbnail(url=user.guild_avatar.url)

            member_lines = [
                f"**Joined Server:** <t:{round(user.joined_at.timestamp())}:f> (<t:{round(user.joined_at.timestamp())}:R>)",
                f"**Join Position:** #{sorted(ctx.guild.members, key=lambda m: m.joined_at).index(user) + 1} / {ctx.guild.member_count}"
            ]
            if user.premium_since:
                member_lines.append(f"**Boosting Since:** <t:{round(user.premium_since.timestamp())}:R>")
            if user.timed_out_until:
                member_lines.append(f"**Timed Out Until:** <t:{round(user.timed_out_until.timestamp())}:R>")
            guild_embed.description = '\n'.join(member_lines)

            if len(user.roles) > 1:
                roles = [role.mention for role in reversed(user.roles[1:])]
                roles_text = ', '.join(roles) if len(', '.join(roles)) <= 1024 else f"{len(roles)} roles"
                guild_embed.add_field(name=f"Roles [{len(user.roles) - 1}]:", value=roles_text, inline=False)

            if ctx.guild.owner == user:
                perms_text = "Owner - has all permissions"
            elif user.guild_permissions.administrator:
                perms_text = "Administrator - has all permissions"
            else:
                perms = [f'`{perm}`' for perm, value in iter(user.guild_permissions) if value]
                perms_text = ', '.join(perms) if perms else "None..."
            guild_embed.add_field(name="Permissions:", value=perms_text, inline=False)
            guild_embed.set_footer(text=f"User ID: {user.id}")

        default_guild = ctx.invoked_with == "member" and guild_embed is not None
        default_embed = guild_embed if default_guild else global_embed

        view = GlobalGuildSwitchView(ctx.author.id, global_embed, guild_embed, default_guild=default_guild)
        view.message = await ctx.reply(embed=default_embed, view=view)


    @commands.hybrid_command(name="guild", aliases=["server"], description="Get information about this server")
    @commands.guild_only()
    async def guild(self, ctx: Context):
        guild = ctx.guild
        embed = discord.Embed(title=guild.name, color=discord.Color.blurple())
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        # Basic Info
        owner = await self.bot.get_or_fetch_member(guild, guild.owner_id)
        info_lines = [
            f"**Owner:** {owner.mention if owner else 'Unknown'} (`{guild.owner_id}`)",
            f"**Created:** <t:{round(guild.created_at.timestamp())}:f> (<t:{round(guild.created_at.timestamp())}:R>)",
            f"**Verification Level:** {guild.verification_level.name.replace('_', ' ').title()}",
        ]
        
        if guild.description:
            info_lines.insert(0, f"*{guild.description}*\n")
        
        embed.add_field(name="Server Information", value='\n'.join(info_lines), inline=False)
        
        # Statistics
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)

        # Member statistics
        total_members = guild.member_count
        bots = sum(1 for m in guild.members if m.bot)
        humans = total_members - bots
        
        # Status count (only if members are cached)
        online = sum(1 for m in guild.members if m.status == discord.Status.online)
        idle = sum(1 for m in guild.members if m.status == discord.Status.idle)
        dnd = sum(1 for m in guild.members if m.status == discord.Status.dnd)
        offline = sum(1 for m in guild.members if m.status == discord.Status.offline)
        
        stats_lines = [
            f"**Members:** {humans:,} (+{bots:,} bots)",
            f"**Online:** {Emojis.Presence.online} {online:,} / {Emojis.Presence.idle} {idle:,} / {Emojis.Presence.dnd} {dnd:,} / {Emojis.Presence.offline} {offline:,}",
            f"**Channels:** {text_channels} text, {voice_channels} voice ({text_channels + voice_channels})",
            f"**Roles:** {len(guild.roles) - 1}",  # Exclude @everyone
            f"**Emojis:** {len(guild.emojis)} / {guild.emoji_limit}",
            f"**Stickers:** {len(guild.stickers)} / {guild.sticker_limit}",
        ]
        embed.description = '\n'.join(stats_lines)
        
        # Boost info
        boost_lines = [
            f"**Level:** {guild.premium_tier} {'⭐' * guild.premium_tier}",
            f"**Boosts:** {guild.premium_subscription_count or 0}" + (f" ({len(guild.premium_subscribers)} boosters)" if guild.premium_subscribers else ""),
        ]

        embed.add_field(name="Boosts", value='\n'.join(boost_lines), inline=False)
        
        # Links
        links = []
        if guild.icon:
            links.append(f"[Icon]({guild.icon.replace(size=4096).url})")
        if guild.banner:
            links.append(f"[Banner]({guild.banner.replace(size=4096).url})")
            embed.set_image(url=guild.banner.replace(size=4096).url)
        if guild.splash:
            links.append(f"[Splash]({guild.splash.replace(size=4096).url})")
        if guild.vanity_url:
            links.append(f"[Vanity URL]({guild.vanity_url})")
        
        if links:
            embed.add_field(name="Links", value=" • ".join(links), inline=False)
        
        embed.set_footer(text=f"Server ID: {guild.id}")

        view = GuildInfoView(guild)
        view.message = await ctx.reply(embed=embed, view=view)

    @commands.hybrid_command(name="transcode", description="Convert between different number systems and encodings", extras={
        "examples": ["dec hex 255", "str base64 hello world", "binary decimal 1010"],
    })
    @app_commands.describe(
        from_format="The format of the input",
        to_format="The format you want to convert to",
        value="The value to convert"
    )
    async def transcode(self, ctx: Context, from_format: str, to_format: str, *, value: commands.Range[str, 1, 2000]):
        """*Supported formats:*
        - **binary**: Binary numbers (e.g., 1010, 0b1010)
        - **decimal**: Decimal numbers (e.g., 42)
        - **hex**: Hexadecimal numbers (e.g., 2A, 0x2A)
        - **base64**: Base64 encoded text
        - **string**: Plain text/ASCII string
        """
        
        from_format = from_format.lower()
        to_format = to_format.lower()
        
        valid_formats = ["binary", "decimal", "hex", "base64", "string"]

        if from_format not in valid_formats:
            matches = [fmt for fmt in valid_formats if fmt.startswith(from_format)]
            if matches:
                from_format = matches[0]
            else:
                await ctx.reply(f"Invalid format! Valid formats are: {', '.join(valid_formats)}", ephemeral=True)
                return
        
        if to_format not in valid_formats:
            matches = [fmt for fmt in valid_formats if fmt.startswith(to_format)]
            if matches:
                to_format = matches[0]
            else:
                await ctx.reply(f"Invalid format! Valid formats are: {', '.join(valid_formats)}", ephemeral=True)
                return

        try:
            intermediate_bytes = None
            
            if from_format == "binary":
                # Remove optional 0b prefix and spaces
                binary_str = value.replace("0b", "").replace(" ", "")
                if not all(c in "01" for c in binary_str):
                    raise ValueError("Binary string must only contain 0s and 1s")
                # Pad to make it byte-aligned
                if len(binary_str) % 8 != 0:
                    binary_str = binary_str.zfill((len(binary_str) // 8 + 1) * 8)
                intermediate_bytes = int(binary_str, 2).to_bytes(len(binary_str) // 8, byteorder='big')
                
            elif from_format == "decimal":
                num = int(value)
                if num < 0:
                    raise ValueError("Negative numbers are not supported")
                # Calculate bytes needed
                byte_length = (num.bit_length() + 7) // 8 or 1
                intermediate_bytes = num.to_bytes(byte_length, byteorder='big')
                
            elif from_format == "hex":
                # Remove optional 0x prefix and spaces
                hex_str = value.replace("0x", "").replace(" ", "")
                if not all(c in "0123456789abcdefABCDEF" for c in hex_str):
                    raise ValueError("Hex string must only contain hexadecimal characters")
                # Pad to even length
                if len(hex_str) % 2 != 0:
                    hex_str = "0" + hex_str
                intermediate_bytes = bytes.fromhex(hex_str)
                
            elif from_format == "base64":
                intermediate_bytes = base64.b64decode(value)
                
            elif from_format == "string":
                intermediate_bytes = value.encode('utf-8')
            
            result = None
            
            if to_format == "binary":
                result = ' '.join(format(byte, '08b') for byte in intermediate_bytes)
                
            elif to_format == "decimal":
                result = str(int.from_bytes(intermediate_bytes, byteorder='big'))
                
            elif to_format == "hex":
                result = intermediate_bytes.hex().upper()
                # Add 0x prefix and space every 2 chars for readability
                result = "0x" + ' '.join(result[i:i+2] for i in range(0, len(result), 2))
                
            elif to_format == "base64":
                result = base64.b64encode(intermediate_bytes).decode('utf-8')
                
            elif to_format == "string":
                result = intermediate_bytes.decode('utf-8', errors='replace')
            
            # Maximise embed description space (4096 characters)
            to_display = f"**Original ({from_format})**\n```\n{trim_str(value, 500)}```\n**Result ({to_format})**\n```\n"
            space_left = 4096 - len(to_display)
            to_display += trim_str(result, space_left - 3) + "```"
            
            embed = discord.Embed(
                description=to_display,
                colour=discord.Colour.green()
            )
            embed.set_footer(text=f"@{ctx.author.name}  |  Bytes processed: {len(intermediate_bytes)}", icon_url=ctx.author.display_avatar.url)
            await ctx.reply(embed=embed)
            
        except ValueError as e:
            await ctx.reply(f"{tick(False)} {str(e)}", ephemeral=True)

    @transcode.autocomplete(name="from_format")
    @transcode.autocomplete(name="to_format")
    async def binary_format_autocomplete(self, interaction: discord.Interaction, current: str):
        formats = ["binary", "decimal", "hex", "base64", "string"]
        return [
            app_commands.Choice(name=fmt.capitalize(), value=fmt) 
            for fmt in formats 
            if fmt.startswith(current.lower())
        ]

    @commands.hybrid_command(name="prefix", description="View or set bot prefixes")
    @app_commands.describe(new_prefix="The new prefix (applies everywhere just for you)")
    @app_commands.rename(new_prefix="new-prefix")
    async def prefix(self, ctx: Context, new_prefix: commands.Range[str, 1, 4] = ''):
        if new_prefix:
            previous_prefix = self.bot.user_prefixes.get(ctx.author.id, self.bot.default_prefix)
            if new_prefix == previous_prefix:
                await ctx.reply("Your personal prefix is already that!", ephemeral=True)
                return

            async with self.bot.get_cursor() as cursor:
                await cursor.execute('''
                        INSERT INTO prefixes (entity_id, is_guild, prefix)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE prefix = VALUES(prefix)
                    ''', (ctx.author.id, False, new_prefix))

            self.bot.user_prefixes[ctx.author.id] = new_prefix

            await ctx.reply(f"Personal prefix changed to `{new_prefix}`\n> Previous prefix: `{previous_prefix}`", ephemeral=True)
        else:
            if ctx.guild: guild_prefix = self.bot.guild_prefixes.get(ctx.guild.id, "None set")
            else: guild_prefix = "N/A"

            personal_prefix = self.bot.user_prefixes.get(ctx.author.id, None)
            if personal_prefix is None: personal_prefix = prefix if (prefix := guild_prefix) != "None set" else self.bot.default_prefix


            embed = discord.Embed(title="Prefixes", description=f"**Personal:** `{personal_prefix}`\n**Guild:** `{guild_prefix}`\n**Additional:** {self.bot.user.mention}", color=discord.Color.blurple())
            await ctx.reply(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="prefix-guild", description="Set the guild prefix")
    @app_commands.describe(new_prefix="The new prefix for everybody to be able to use in the guild")
    @app_commands.rename(new_prefix="new-prefix")
    @commands.guild_only()
    @checks.hybrid_has_permissions(manage_guild=True)
    async def prefix_guild(self, ctx: Context, new_prefix: commands.Range[str, 1, 4]):
        previous_prefix = self.bot.guild_prefixes.get(ctx.guild.id, self.bot.default_prefix)

        if new_prefix == previous_prefix:
            await ctx.reply("The guild prefix is already that!", ephemeral=True)
            return

        async with self.bot.get_cursor() as cursor:
            await cursor.execute('''
                    INSERT INTO prefixes (entity_id, is_guild, prefix)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE prefix = VALUES(prefix)
                ''', (ctx.guild.id, True, new_prefix))

        self.bot.guild_prefixes[ctx.guild.id] = new_prefix

        await ctx.reply(f"Guild prefix changed to `{new_prefix}`\n> Previous prefix: `{previous_prefix}`", ephemeral=True)

    async def ctx_menu_count(self, interaction: discord.Interaction, message: discord.Message):
        content = message.content

        await interaction.response.send_message(
            f"Characters: `{len(content):,}`\n"
            f"Words: `{len(content.split()):,}`\n"
            f"New lines: `{len(content.split('\n')):,}`"
        )

    async def os_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return [app_commands.Choice(name=o, value=o) for o in self.available_os_ascii if current.lower() in o.lower()][:25]

    @commands.hybrid_command(name="distro", description="Colourful render of an OS logo in an ANSI codeblock")
    @app_commands.describe(os="The OS' icon you want to use")
    @app_commands.autocomplete(os=os_autocomplete)
    async def distro(self, ctx: Context, *, os: commands.Range[str, 1, 50]):

        # Resolve the input to a known logo (case-insensitive), keeping fastfetch's canonical casing
        logo = next((o for o in self.available_os_ascii if o.lower() == os.lower()), None)
        if logo is None:
            await ctx.reply(f"{tick(False)} That isn't a recognised logo (use the autocomplete with the slash command)", ephemeral=True)
            return

        # Render just the logo (`-s none`), forcing colours through the pipe (`--pipe false`)
        process = await asyncio.create_subprocess_exec(
            "fastfetch", "--logo", logo, "-s", "none", "--pipe", "false",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await process.communicate()

        # Strip fastfetch's cursor-repositioning escapes, keeping colour/SGR (`…m`) codes
        art = re.sub(r'\x1b\[[\d;?]*[A-Za-ln-z]', '', stdout.decode())
        # fastfetch resets colour with an empty-param `\x1b[m`, which Discord renders literally; normalise it to the explicit `\x1b[0m` it understands, then drop the redundant trailing reset(s)
        art = re.sub(r'(?:\x1b\[0m)+$', '', art.replace('\x1b[m', '\x1b[0m').strip())
        # Neutralise backticks so they can't break out of the code block
        art = art.replace('`', '´').strip()

        warning = ''
        if isinstance(ctx.author, discord.Member) and ctx.author.is_on_mobile():
            warning = ":warning: **You appear to be on Discord mobile**\n> - Colours are not displayed\n> - The logo might be too wide for your screen\n"

        heading = f"## {logo}\n"
        block = f"```ansi\n{art}```"

        # Keep the code block in the message content so it renders full-width; only the rare logo that overflows the 2000-char content limit falls back into the embed
        if len(heading) + len(warning) + len(block) <= 2000:
            await ctx.reply(content=f"{heading}{warning}{block}")
        else:
            embed = discord.Embed(title=logo, description=f"{warning}{block}", color=discord.Colour.greyple())
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            await ctx.reply(embed=embed)


async def setup(bot: Woolinator) -> None:
    await bot.add_cog(Misc(bot))
