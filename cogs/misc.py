import logging
import base64
import os
import subprocess
import unicodedata
import psutil
import platform

import discord
from discord import app_commands, ui
from discord.ext import commands, tasks

from .utils import checks
from .utils.emojis import tick
from .utils.common import trim_str
from .utils.context import Context
from .utils.views import GlobalGuildSwitchView, GuildInfoView
from .utils.emojis import Emojis
from bot import Woolinator


log = logging.getLogger(__name__)



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


class Misc(commands.Cog, name="Miscellaneous", description="Uncategorised stuff"):

    def __init__(self, bot: Woolinator) -> None:
        self.bot: Woolinator = bot
        self._last_member = None

        self.process = psutil.Process()

        # Available list obtained from `neofetch --help`, and then '--ascii_distro' flag info
        with open("resources/os-logos.txt", 'r') as f:
            self.available_os_ascii = f.read().strip('"').split(', ')

        self.ctx_count = app_commands.ContextMenu(name="Word & Character Count", callback=self.ctx_menu_count)
        self.bot.tree.add_command(self.ctx_count)

        self.deleted_messages: dict[int, discord.Message] = {}
        self.edited_messages: dict[int, tuple[discord.Message, discord.Message]] = {}

    async def cog_load(self):
        if not self.rotate_status.is_running(): self.rotate_status.start()

    async def cog_unload(self):
        self.rotate_status.cancel()

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
            .add_item(ui.Button(style=discord.ButtonStyle.link, label="GitHub repository", url="https://github.com/Woolyenough/The-Woolinator"))
        await ctx.reply(embed=embed, view=view)

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
        before, after = self.edited_messages.get(ctx.channel.id, None)

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
        categories = len(guild.categories)
        
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
            f"**Online:** {Emojis.Presence.online} {online:,}, {Emojis.Presence.idle} {idle:,}, {Emojis.Presence.dnd} {dnd:,}, {Emojis.Presence.offline} {offline:,}",
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
                res = await cursor.execute("UPDATE prefixes SET prefix = %s WHERE is_guild = FALSE AND entity_id = %s", (new_prefix, ctx.author.id,))

                if res == 0:
                    await cursor.execute("INSERT INTO prefixes (entity_id,is_guild,prefix) VALUES (%s, %s, %s)", (ctx.author.id, False, new_prefix,))

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
            res = await cursor.execute("UPDATE prefixes SET prefix = %s WHERE is_guild = TRUE AND entity_id = %s", (new_prefix, ctx.guild.id,))

            if res == 0:
                await cursor.execute("INSERT INTO prefixes (entity_id, is_guild, prefix) VALUES (%s, %s, %s)", (ctx.guild.id, True, new_prefix,))

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
        return [app_commands.Choice(name=o.replace('"', ''), value=o.replace('"', '')) for o in self.available_os_ascii if o.lower().startswith(current.lower())][:25]

    @commands.hybrid_command(name="distro", description="Colourful render of an OS logo in an ANSI codeblock")
    @app_commands.describe(os="The OS' icon you want to use")
    @app_commands.autocomplete(os=os_autocomplete)
    async def distro(self, ctx: Context, os: commands.Range[str, 1, 50]):

        found = False
        for os_name in self.available_os_ascii:
            if os_name.lower().replace('"', '') == os.lower():
                os = os_name
                found = True

        os = os if found else "Invalid distro"

        def remove_cursor_moving_ansi(text):
            # Discord ANSI code blocks don't look forward slash, for some reason
            text = text.replace('/', '\\')

            # I'm assuming these are escape sequences to move the cursor, I had no idea how else to get rid of these...
            return text.replace("[16A[9999999D", '').replace("[27A[9999999D", '').replace("[23A[9999999D", '').replace("[15A[9999999D", '').replace("[21A[9999999D", '').replace("[17A[9999999D", '').replace("[13A[9999999D", '').replace("[12A[9999999D", '').replace("[?25l[?7l", '').replace("[18A[9999999D", '').replace("[20A[9999999D", '').replace("[?25h[?7h", '').replace("[19A[9999999D", '').replace("[28A[9999999D", '')

        stdout = subprocess.run(["neofetch", "--ascii_distro", os, "-L"], capture_output=True, text=True).stdout
        stdout = remove_cursor_moving_ansi(stdout)
        stdout = stdout.replace('`', '´').strip()  # Replace backticks to prevent code block escaping

        warning = ''
        if isinstance(ctx.author, discord.Member) and ctx.author.is_on_mobile():
            warning = ":warning: **You appear to be on Discord mobile**\n> - Colours are not displayed\n> - The logo might be too wide for your screen\n"

        embed = discord.Embed(title=os, description=f"{warning}```ansi\n{stdout}```", color=discord.Colour.greyple())
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        await ctx.reply(embed=embed)


async def setup(bot: Woolinator) -> None:
    await bot.add_cog(Misc(bot))
