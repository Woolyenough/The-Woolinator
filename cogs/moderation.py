from typing import Literal, Callable, Any
import logging
from datetime import timedelta, datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import escape_markdown, escape_mentions

from .utils import checks
from .utils.views import YesOrNo
from .utils.emojis import tick, Emojis
from .utils.common import parse_entered_duration, format_timedelta, trim_str, hybrid_msg_edit, plur, format_timedelta
from .utils.context import Context
from bot import Woolinator


log = logging.getLogger(__name__)


class Moderation(commands.Cog, name="Moderation", description="Tools to help moderate"):

    def __init__(self, bot: Woolinator) -> None:
        self.bot: Woolinator = bot

    async def cog_check(self, ctx: Context) -> bool:
        if ctx.guild is None: raise commands.NoPrivateMessage()
        return True

    @property
    def emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name="moderation",id=1337677182197039105)

    async def send_dm_victim(self, ctx: Context, action: str, victim: discord.Member | discord.User, info: list[str], colour: int | discord.Colour = 0xff7835) -> bool:
        #punisher = ctx.author
        embed = discord.Embed(description='\n'.join(info), colour=0xff8b43)
        embed.set_author(name=f"You have been {action}!", icon_url=victim.display_avatar.url)
        embed.set_footer(text=f"From {ctx.guild.name}", icon_url=getattr(ctx.guild.icon, "url", None))

        sent = False
        try:
            await victim.send(embed=embed)
            sent = True
        except discord.HTTPException:
            pass

        return sent

    async def get_mod_log_channel(self, guild: discord.Guild|int) -> int | None:
        """ Get snowflake channel ID of mod logs channel, `None` if it isn't set. """
        if isinstance(guild, discord.Guild): guild = guild.id

        async with self.bot.get_cursor() as cursor:
            await cursor.execute("SELECT channel_id FROM channels WHERE feature = %s AND guild_id = %s", ("mod-logs", guild,))
            res = await cursor.fetchone()
        return res[0] if res else None

    @commands.hybrid_group(name="mod-log", description="Get the channel mod logs are sent to", fallback="get")
    async def mod_log(self, ctx: Context):
        channel_id = await self.get_mod_log_channel(ctx.guild)
        
        if channel_id:
            await ctx.reply(f"Moderator actions are currently being logged to <#{channel_id}>", ephemeral=True)
        else:
            await ctx.reply(f"{Emojis.warn} Mod actions aren't currently being logged to any channels!\n> Set it to a channel now with </mod-log set:1381472026660835398>", ephemeral=True)

    @mod_log.command(name="remove", description="Remove the channel & disable mod log functionality")
    async def mod_log_remove(self, ctx: Context):
        channel_id = await self.get_mod_log_channel(ctx.guild)
        
        if channel_id:
            async with self.bot.get_cursor() as cursor:
                await cursor.execute("DELETE FROM chanels WHERE guild_id = %s AND feature = %s", (ctx.guild.id, "mod-logs"))
            await ctx.reply("Successfully removed. Mod actions won't be logged anymore.", ephemeral=True)
        else:
            await ctx.reply("There is currently no mod log channel set", ephemeral=True)

    @mod_log.command(name="set", description="Set the channel mod logs will be sent to")
    @app_commands.describe(channel="The channel where the logs will be sent to")
    async def mod_log_set(self, ctx: Context, channel: discord.TextChannel):
        channel_id = await self.get_mod_log_channel(ctx.guild)
        
        if channel_id and channel.id == channel_id:
            return await ctx.reply("But thats the same channel it's already set to...", ephemeral=True)

        async def update_db() -> None:
            async with self.bot.get_cursor() as cursor:
                await cursor.execute('''
                        INSERT INTO channels (feature, guild_id, channel_id)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE channel_id = %s
                    ''', ("mod-logs", ctx.guild.id, channel.id, channel.id))

        if channel_id:
            view = YesOrNo(ctx.author)
            message = await ctx.reply(f"This server already has a mod log channel set to: <#{channel_id}>!\n>>> Are you sure you want to change it to {channel.mention}?", view=view)
            view.message = message
            await view.wait()

            if not view.value:
                return

            await update_db()
            await message.edit(content=f"Done. Mod logs will now be sent to {channel.mention}", view=None)

        else:
            await update_db()
            await ctx.reply(f"Mod logs channel has been set to {channel.mention}")

    class PurgeFlags(commands.FlagConverter, delimiter=' ', prefix='-', case_insensitive=True):

        user: discord.User|discord.Member|None = commands.flag(
            description="Include messages from this user", aliases=['u'], default=None
        )

        contains: str | None = commands.flag(
            description="Include messages that contains this text (case sensitive)", aliases=['c'], default=None
        )

        prefix: str | None = commands.flag(
            description="Include messages that start with this text (case sensitive)", aliases=['p'], default=None
        )

        suffix: str | None = commands.flag(
            description="Include messages that end with this text (case sensitive)", aliases=['s'], default=None
        )

        after: int | None = commands.flag(
            description="Include messages that come after this message ID", aliases=['a'], default=None
        )

        before: int | None = commands.flag(
            description="Include messages that come before this message ID", aliases=['b'], default=None
        )

        bot: bool = commands.flag(
            description="Include messages from bots", default=False
        )

        require: Literal["any", "all"] = commands.flag(
            description="Whether any or all of the flags should be met. Default: 'all'",
            aliases=['r'], default="all",
        )

    @commands.hybrid_command(name="purge", description="Delete messages in bulk with customisable filters")
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    @checks.hybrid_has_permissions(manage_messages=True)
    @app_commands.describe(amount="The amount of messages to search back in the chat through (not the amount to delete!)")
    @commands.cooldown(4, 10.5, commands.BucketType.user)
    async def purge(self, ctx: Context, amount: commands.Range[int, 1, 999], *, flags: PurgeFlags):
        """ Due to the customisable nature of this command, there are a lot of flags. For autocompletion, it is advised to use the slash version of this command.

        The following flags (+ aliases) are available:
        `-user (-u) [USER]` - The user to include messages from
        `-contains (-c) [TEXT]` - The text to include messages that contain
        `-prefix (-p) [TEXT]` - The text to include messages that start with
        `-suffix (-s) [TEXT]` - The text to include messages that end with
        `-after (-a) [MESSAGE ID]` - The message ID to include messages that come after
        `-before (-b) [MESSAGE ID]` - The message ID to include messages that come before
        `-bot` - Whether to include messages from bots
        `-require (-r) [any/all]` (default:all) - Whether any or all of the flags should be met
        
        You can use as many flags as you like.

        Example:
        `?purge 100 -bot 1 -c hello there -b 123456789` will search the last 100 messages and delete all those that are sent from a bot, before the message with the ID '123456789', and contains the text 'hello there'
        """

        await ctx.defer(ephemeral=True)

        predicates: list[Callable[[discord.Message], Any]] = []
        if flags.bot:
            predicates.append(lambda m: (m.webhook_id is None or m.interaction is not None) and m.author.bot)

        if flags.user:
            predicates.append(lambda m: m.author == flags.user)

        if flags.contains:
            predicates.append(lambda m: flags.contains in m.content)

        if flags.prefix:
            predicates.append(lambda m: m.content.startswith(flags.prefix))

        if flags.suffix:
            predicates.append(lambda m: m.content.endswith(flags.suffix))

        threshold = discord.utils.utcnow() - timedelta(days=14)
        predicates.append(lambda m: m.created_at >= threshold)

        op = all if flags.require == "all" else any

        def predicate(m: discord.Message) -> bool:
            if m.id == ctx.message.id: return False  # ignore the message that invoked command
            r = op(p(m) for p in predicates)
            return r

        before = discord.Object(id=flags.before) if flags.before else None
        after = discord.Object(id=flags.after) if flags.after else None
        if before is None and ctx.interaction is not None:
            before = await ctx.interaction.original_response()

        amount = amount if ctx.interaction else (amount + 1)
        try:
            deleted = [msg async for msg in ctx.channel.history(limit=amount, before=before, after=after) if predicate(msg)]
        except discord.Forbidden:
            return await ctx.reply("I do not have permissions to search for messages.")
        except discord.HTTPException as e:
            return await ctx.reply(f"Error: {e} (try a smaller search?)")

        if len(deleted) == 0:
            return await ctx.reply("No messages found to delete.", ephemeral=True)

        for chunk in discord.utils.as_chunks(deleted, 100):
            try:
                await ctx.channel.delete_messages(chunk, reason=f"Purge command ran by {ctx.author.name} ({ctx.author.id})")
            except discord.HTTPException as e:
                return await ctx.reply(f"Error while deleting: {e}")
        
        if ctx.interaction is not None:
            await ctx.reply("Done!", ephemeral=True)
        else:
            await ctx.react()

    @commands.hybrid_command(name="kick", description="Kick a member")
    @commands.bot_has_permissions(kick_members=True)
    @checks.hybrid_has_permissions(kick_members=True)
    @app_commands.describe(member="The member you want to kick", reason="The reason for the kick")
    async def kick(self, ctx: Context, member: discord.Member, *, reason: commands.Range[str, 1, 400] = "No reason"):

        if member.guild_permissions.manage_guild:
            return await ctx.reply("You can't kick members with the `manage_guild` permission", ephemeral=True)

        if ctx.guild.me.top_role <= member.top_role:
            return await ctx.reply("I can't kick this member due to role hierarchy (their top role is higher than mine)", ephemeral=True)

        await ctx.typing()

        await ctx.guild.kick(member, reason=f"Mod: {ctx.author.name} | Reason: {reason}")

        info = [
            f"**Moderator:** `@{ctx.author.name}` ({ctx.author.mention})",
            f"**Reason:** {reason}"
        ]

        sent = await self.send_dm_victim(ctx=ctx, action="kicked", victim=member, colour=0xf0eb56, info=info)

        info.insert(1, f"**DM:** {tick(True) if sent else tick(False)}")
        embed = discord.Embed(description='\n'.join(info), colour=0xf0eb56)
        embed.set_author(name=f"Kicked @{member.name}", icon_url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="mute", aliases=["timeout", "tm"], description="Time out a member")
    @commands.bot_has_permissions(moderate_members=True)
    @checks.hybrid_has_permissions(moderate_members=True)
    @app_commands.describe(member="The member you want to time out", duration="The duration of the timeout; e.g., '1d, 10 days, 5secs' (separated by comma)", reason="The reason for the time out")
    async def mute(self, ctx: Context, member: discord.Member, duration: commands.Range[str, 2, 50], *, reason: commands.Range[str, 1, 400] = "No reason"):

        if member.guild_permissions.manage_guild:
            return await ctx.reply("You can't mute members with the `manage_guild` permission", ephemeral=True)

        if ctx.guild.me.top_role <= member.top_role:
            return await ctx.reply("I can't mute this member due to role hierarchy (their top role is higher than mine)", ephemeral=True)

        duration, invalid_formats, too_long = parse_entered_duration(duration)

        if invalid_formats or too_long:
            invalid_message = ''
            if invalid_formats:
                invalid_list = ''
                for i, invalid_format in enumerate(invalid_formats, start=1):
                    invalid_list += f'{i}. {trim_str(invalid_format, 15)}\n'

                if invalid_list:
                    invalid_message = f"Invalid time format{plur(len(invalid_formats))}:\n{invalid_list}"

            too_long_message = ''
            if too_long:
                too_long_list = ''
                for i, too_long_values in enumerate(too_long, start=1):
                    too_long_list += f"{i}. {trim_str(too_long_values, 15)}\n"

                if too_long_list:
                    too_long_message = f"Time format{' that is' if len(too_long) == 1 else 's that are'} too long:\n{too_long_list}"

            return await ctx.reply('\n\n'.join([invalid_message, too_long_message]), ephemeral=True)

        now = discord.utils.utcnow()
        end = now + duration
        duration: timedelta = end - now
        
        if duration.total_seconds() > 28 * 24 * 60 * 60:
            return await ctx.reply("Timeouts can't be longer than 28 days", ephemeral=True)

        view = None
        if member.is_timed_out():
            view = YesOrNo(ctx.author)
            view.message = await ctx.reply("This member is already timed out. Do you want this to replace their current timeout?", view=view)

            await view.wait()

            if not view.value:
                return

        await ctx.typing()

        await member.timeout(end, reason=f"Mod: {ctx.author.name} | Reason: {reason}")

        end_ts = round(end.timestamp())

        info = [
            f"**Moderator:** `@{ctx.author.name}` ({ctx.author.mention})",
            f"**Duration:** {format_timedelta(duration)}",
            f"**Ends:** <t:{end_ts}:f> (<t:{end_ts}:R>)",
            f"**Reason:** {reason}"
        ]

        sent = await self.send_dm_victim(ctx=ctx, action="timed out", victim=member, colour=0xff8b43, info=info)
        info.insert(3, f"**DM:** {tick(True) if sent else tick(False)}")

        embed = discord.Embed(description='\n'.join(info), colour=0xff8b43)
        embed.set_author(name=f"Timed out @{member.name}", icon_url=member.display_avatar.url)
        if view is not None:
            await hybrid_msg_edit(view.message, content='', view=None, embed=embed)
        else:
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="unmute", description="Remove a member's timeout")
    @commands.bot_has_permissions(moderate_members=True)
    @checks.hybrid_has_permissions(moderate_members=True)
    @app_commands.describe(member="The user whose timeout you want to remove", reason="The reason for the unmute")
    async def unmute(self, ctx: Context, member: discord.Member, *, reason: commands.Range[str, 1, 400] = "No reason"):

        if not member.is_timed_out():
            return await ctx.reply("This user is not timed out!", ephemeral=True)

        if ctx.guild.me.top_role <= member.top_role:
            return await ctx.reply("I can't remove this member's timeout due to role hierarchy (their top role is higher than mine)", ephemeral=True)

        await ctx.typing()


        info = [
            f"**Moderator:** `@{ctx.author.name}` ({ctx.author.mention})",
            f"**Reason:** {reason}",
        ]

        await member.timeout(None, reason=f"Mod: {ctx.author.name} | Reason: {reason}")

        sent = await self.send_dm_victim(ctx=ctx, action="unmuted", victim=member, colour=0x83f590, info=info)

        info.insert(1, f"**DM:** {tick(True) if sent else tick(False)}")
        embed = discord.Embed(description='\n'.join(info), colour=0x83f590)
        embed.set_author(name=f"Unmuted @{member.name}", icon_url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="ban", description="Ban a member")
    @commands.bot_has_permissions(ban_members=True)
    @checks.hybrid_has_permissions(ban_members=True)
    @app_commands.describe(member="The member you want to ban", reason="The reason for the ban")
    async def ban(self, ctx: Context, member: discord.Member|discord.User, *, reason: commands.Range[str, 1, 400] = "No reason"):
        
        if isinstance(member, discord.Member):
            if member.guild_permissions.manage_guild:
                return await ctx.reply("You can't ban members with the `manage_guild` permission", ephemeral=True)

            if ctx.guild.me.top_role <= member.top_role:
                return await ctx.reply("I can't ban this member due to role hierarchy (their top role is higher than mine)", ephemeral=True)

        is_banned = False
        try:
            await ctx.guild.fetch_ban(member)
            is_banned = True
        except discord.NotFound:
            pass

        view = None
        if is_banned:
            view = YesOrNo(ctx.author)
            view.message = await ctx.reply("This member is already banned. Do you want this to replace their current ban?", view=view)

            await view.wait()

            if not view.value:
                return

        await ctx.typing()

        await ctx.guild.ban(member, reason=f"Mod: {ctx.author.name} | Reason: {reason}", delete_message_days=0)

        info = [
            f"**Moderator:** `@{ctx.author.name}` ({ctx.author.mention})",
            f"**Reason:** {reason}",
        ]

        sent = await self.send_dm_victim(ctx=ctx, action="banned", victim=member, colour=0xd60f78, info=info)

        info.insert(1, f"**DM:** {tick(True) if sent else tick(False)}")
        embed = discord.Embed(description='\n'.join(info), colour=0xd60f78)
        embed.set_author(name=f"Banned @{member.name}", icon_url=member.display_avatar.url)

        if view is not None:
            await hybrid_msg_edit(view.message, content='', view=None, embed=embed)
        else:
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="unban", description="Unban a member")
    @commands.bot_has_permissions(ban_members=True)
    @checks.hybrid_has_permissions(ban_members=True)
    @app_commands.describe(user="The user you want to unban", reason="The reason for the unban")
    async def unban(self, ctx: Context, user: discord.User, *, reason: commands.Range[str, 1, 400] = "No reason"):
        await ctx.typing()

        try:
            await ctx.guild.unban(user, reason=f"Mod: {ctx.author.name} | Reason: {reason}")
        except discord.NotFound:
            return await ctx.reply("I could not find that unban... are you sure that user is banned?", ephemeral=True)


        info = [
            f"**Moderator:** `@{ctx.author.name}` ({ctx.author.mention})",
            f"**Reason:** {reason}",
        ]

        sent = await self.send_dm_victim(ctx=ctx, action="unbanned", victim=user, colour=0x83f590, info=info)

        info.insert(1, f"**DM:** {tick(True) if sent else tick(False)}")
        embed = discord.Embed(description='\n'.join(info), colour=0x83f590)
        embed.set_author(name=f"Unbanned @{user.name}", icon_url=user.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="checkban", description="Get info on a user's ban")
    @commands.bot_has_permissions(ban_members=True)
    @checks.hybrid_has_permissions(ban_members=True)
    @app_commands.describe(user="The user you want to get ban details of")
    async def checkban(self, ctx: Context, user: discord.User):
        try:
            ban_entry = await ctx.guild.fetch_ban(user)
        except discord.NotFound:
            return await ctx.reply(f"User `{user.name}` does not seem to be banned...", ephemeral=True)

        embed=discord.Embed(description=f"**Reason:**\n>>> {escape_markdown(escape_mentions(ban_entry.reason))}", colour=0x9a61ff)
        embed.set_author(name=f"@{user.name}'s ban", icon_url=user.display_avatar.url)
        await ctx.reply(embed=embed)

    @commands.hybrid_command(name="banall", description="Ban members in bulk")
    @commands.bot_has_permissions(ban_members=True)
    @checks.hybrid_has_permissions(ban_members=True)
    @commands.cooldown(4, 12, commands.BucketType.user)
    @app_commands.describe(members="The members you want to ban (separated by spaces)", reason="The reason for the bans")
    async def banall(self, ctx: Context, members: commands.Greedy[discord.Member|discord.User], *, reason: commands.Range[str, 0, 400] = "No reason"):
        res: list[discord.Member|discord.User|None] = []

        await ctx.typing()

        failed = 0
        for member in members:
            res.append(member)

            if isinstance(member, discord.Member):
                if member.guild_permissions.manage_guild or ctx.guild.me.top_role <= member.top_role:
                    failed += 1
                    continue

            try:
                await ctx.guild.ban(member, reason=f"Mod: {ctx.author.name} | Reason: {reason}", delete_message_days=0)
            except discord.HTTPException:
                failed += 1

        cleaned_reason = await commands.clean_content(escape_markdown=True).convert(ctx, reason)
        await ctx.reply(f"Banned {len(res)} {f'({failed} failed)' if failed else ''} members\n>>> **Reason:** {cleaned_reason}", ephemeral=True)


async def setup(bot: Woolinator) -> None:
    await bot.add_cog(Moderation(bot))
