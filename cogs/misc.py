import logging
import base64
import binascii
import os
import subprocess
import unicodedata
import psutil
import itertools

import discord
from discord import app_commands
from discord.ext import commands, tasks

from .utils import checks
from .utils.common import trim_str
from .utils.context import Context
from bot import Woolinator


log = logging.getLogger(__name__)


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

    @tasks.loop(minutes=5)
    async def rotate_status(self):
        """ A task to change the bot status at intervals. """

        await self.bot.wait_until_ready()
        await self.bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(self.bot.users)} users in {len(self.bot.guilds)} guilds 🤙😎"
            )
        )

    @commands.hybrid_command(name="end-of-10", description="Windows 10 support countdown")
    async def end_of_10(self, ctx: Context):
        ts = "1761375540"
        await ctx.reply(f"Microsoft will end support for Windows 10 on <t:{ts}:F> (<t:{ts}:R>)!")

    @commands.hybrid_command(name="about", description="About myself!")
    async def about(self, ctx: Context):
        total_lines, total_chars, total_files = [0] * 3

        for dirpath, dirnames, filenames in os.walk('.'):
            dirnames[:] = [d for d in dirnames if d not in {".venv", "__pycache__"}]

            for file in filenames:
                if file.endswith('.py'):
                    file_path = os.path.join(dirpath, file)

                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            total_lines += content.count('\n') + 1  # +1 for last line without \n
                            total_chars += len(content)
                            total_files += 1

                    except Exception as e:
                        log.warning(f"Couldn't read file '{file_path}'", exc_info=e)
                        continue
        
        memory_usage = self.process.memory_full_info().uss / 1024**2
        total_memory = psutil.virtual_memory().total / 1024**2
        mem_pc = (memory_usage / total_memory) * 100
        cpu_usage = self.process.cpu_percent() / psutil.cpu_count()

        description = [
            f"Private bot made by [**`@woolyenough`**](https://discord.com/users/{self.bot.owner.id})",
            "",
            f"**Created:** <t:{round(self.bot.user.created_at.timestamp())}:R>",
            f"**Code:** {total_lines:,} lines / {total_chars:,} chars / {total_files} .py files",
            "",
        ]

        embed = discord.Embed(title=str(self.bot.user), description='\n'.join(description), colour=0xffe3be)
        embed.set_author(name=f"@{self.bot.owner.name}", icon_url=self.bot.owner.display_avatar.url)
        embed.add_field(name="**Exposure:**", value=f"> {len(self.bot.guilds)} Guilds (Servers)\n> {len(self.bot.users):,} Users")
        embed.add_field(name="**Process:**", value=f"> {cpu_usage:.2f}% CPU\n> {memory_usage:.2f} MiB ({mem_pc:.2f}%) Mem")
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text="Made with discord.py", icon_url="http://i.imgur.com/5BFecvA.png")
        await ctx.reply(embed=embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild:
            self.deleted_messages[message.channel.id] = message

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if after.guild and before.content != after.content:
            self.edited_messages[before.channel.id] = (before, after)

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

        view = discord.ui.View()\
            .add_item(discord.ui.Button(style=discord.ButtonStyle.link, label="Jump to Message", url=after.jump_url))
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

    @commands.hybrid_command(name="user", description="Get information about a user")
    @app_commands.describe(user="The user you want to get the info of")
    @commands.guild_only()
    async def user(self, ctx: Context, user: discord.Member|discord.User = commands.Author):
        try:
            pass
            #f_user = await self.bot.fetch_user(user.id)  # get_user() does not return user banner
        except discord.HTTPException:
            pass
        
        links = []
        description = f"**Created:** <t:{round(user.created_at.timestamp())}:F>"
        embed = discord.Embed(title=user.display_name, colour=discord.Colour.random())
        embed.set_author(name=f"@{user.name}", icon_url=user.display_avatar.url)
        
        if isinstance(user, discord.Member):
            description += f"\n**Joined:** <t:{round(user.joined_at.timestamp())}:F>"
            embed.add_field(name="Roles:", value=', '.join(role.mention for role in user.roles), inline=False)

            if ctx.guild.owner == user: perms = "All - this user owns the guild."
            elif user.guild_permissions.administrator: perms = "Administrator - this pretty much overrides all other permissions."
            else: perms = ', '.join(f'`{perm}`' for perm, value in iter(user.guild_permissions) if value)

            embed.add_field(name="Permissions:", value=perms, inline=False)

            if user.guild_avatar:
                links.append(("Guild Avatar", user.guild_avatar.url))
                embed.set_thumbnail(url=user.guild_avatar.url)
            if user.guild_banner: links.append(("Guild Banner", user.guild_banner.url))

        links.append(("Avatar", user.display_avatar.url))

        embed.add_field(name="Links:", value='\n'.join(f"{i}. [**{name}**]({url.replace('size=1024', 'size=4096')})" for i, (name, url) in enumerate(links, start=1)), inline=False)

        embed.description = description
        embed.set_footer(text=f"ID: {user.id}")
        await ctx.reply(embed=embed)
        # Add buttons 'avatar' & 'banner' which are red/green (depending on if the user has them) which will self.invoke_command() the command

    @commands.hybrid_command(name="base64", aliases=["b64"], description="Encode & decode text in base64")
    @app_commands.describe(method="Whether to decode or encode (default: encode)", text="The text to encode/decode")
    async def base64(self, ctx: Context, method: str = "encode", *, text: commands.Range[str, 1, 3000]):
        try:
            if "decode".startswith(method):
                b = base64.b64decode(bytes(text, "utf-8"))
                base64_str = b.decode("utf-8")
                await ctx.reply(embed=discord.Embed(title="Base64 Decoded", description=base64_str, color=discord.Color.random()))
            else:
                #if ctx.interaction is None and not 'encode'.startswith(method): text = f'{method} {text}'  # hmm, idk about this...
                b = base64.b64encode(bytes(text, "utf-8"))
                base64_str = b.decode("utf-8")
                await ctx.reply(embed=discord.Embed(title="Base64 Encoded", description=base64_str, color=discord.Color.random()))

        except binascii.Error:
            await ctx.reply("There was an error encoding/decoding the text.", ephemeral=True)

    @base64.autocomplete(name="method")
    async def base64_autocomplete(self, interaction: discord.Interaction, current: str):
        opts = ["encode", "decode"]
        return [
            app_commands.Choice(name=opt, value=opt) for opt in opts if opt.startswith(current.lower())
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
