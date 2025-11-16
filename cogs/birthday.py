import logging
from datetime import time, timezone, datetime
import re
import asyncio

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot import Woolinator
from .utils import checks
from .utils.views import YesOrNo, ChannelSelector
from .utils.emojis import Emojis, tick
from .utils.context import Context

log = logging.getLogger(__name__)


class Birthday(commands.Cog, name="Birthday Announcer", description="Keep track of everybodys' birthdays"):
    
    def __init__(self, bot: Woolinator) -> None:
        self.bot: Woolinator = bot

    async def cog_load(self):
        if not self.birthday_notifier.is_running():
            self.birthday_notifier.start()

    async def cog_unload(self):
        self.birthday_notifier.cancel()

    async def cog_check(self, ctx: Context) -> bool:
        if ctx.guild: return True
        else: raise commands.NoPrivateMessage

    @property
    def emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name="\U0001f382")

    async def get_year_last_announced(self, user: discord.Member|discord.User|int, guild: discord.Guild|int) -> int|None:
        if isinstance(guild, discord.Guild): guild = guild.id
        if isinstance(user, discord.Member) or isinstance(user, discord.User): user = user.id

        async with self.bot.get_cursor() as cursor:
            await cursor.execute('''
                    SELECT last_announced
                    FROM birthdays
                    WHERE user_id = %s AND guild_id = %s
                ''', (user, guild,))
            res = await cursor.fetchone()

        return res[0] if res else None

    async def get_user_birthday(self, user: discord.Member|discord.User|int, guild: discord.Guild|int) -> datetime|None:
        if isinstance(guild, discord.Guild): guild = guild.id
        if isinstance(user, discord.Member) or isinstance(user, discord.User): user = user.id

        async with self.bot.get_cursor() as cursor:
            await cursor.execute('''
                    SELECT date
                    FROM birthdays
                    WHERE user_id = %s AND guild_id = %s
                ''', (user, guild,))
            res = await cursor.fetchone()

        if res:
            parts = res[0].split('.')[::-1]
            return datetime(*[int(i) for i in parts])  # type: ignore
        return None

    async def get_bday_channel(self, guild: discord.Guild|int) -> int | None:
        """ Get snowflake channel ID, `None` if it isn't set. """

        if isinstance(guild, discord.Guild): guild = guild.id

        async with self.bot.get_cursor() as cursor:
            await cursor.execute('''
                    SELECT channel_id
                    FROM channels
                    WHERE feature = %s AND guild_id = %s
                ''', ("birthdays", guild,))
            res = await cursor.fetchone()
        return res[0] if res else None

    async def no_channel_warn(self, user: discord.Member) -> str:
        """ Get tailored warning message if the birthday channel isn't set. """

        channel_id = await self.get_bday_channel(user.guild)
        if not channel_id:
            if user.guild_permissions.manage_guild: return f"\n-# {Emojis.warn} No birthday channel has been set up. Until then, no birthdays will be announced. Set one now with </birthday-channel set:1381472026660835399>."
            else: return f"\n-# {Emojis.warn} No birthday channel has been set up. Until then, no birthdays will be announced."
        return ''


    def format_date(self, dt: datetime) -> str:

        def ordinal_suffix(day) -> str:
            if 10 <= day % 100 <= 20:
                suffix = 'th'
            else:
                suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
            return suffix

        day = dt.day
        suffix = ordinal_suffix(day)
        return dt.strftime(f"{day}{suffix} %B %Y")

    @commands.hybrid_group(name="birthday", description="Get your birth date for this guild", fallback="get")
    async def birthday(self, ctx: Context):
        date = await self.get_user_birthday(ctx.author, ctx.guild)
        warning = await self.no_channel_warn(ctx.author)

        if date:
            await ctx.reply(f"Your set birthdate for this guild is `{self.format_date(date)}`{warning}", ephemeral=True)
        else:
            await ctx.reply(f"You have no set birthdate for this server!\n> Set one now with </birthday set:1381472026660835398>{warning}", ephemeral=True)

    @birthday.command(name="remove", description="Remove your birth date for this guild")
    async def birthday_remove(self, ctx: Context):
        date = await self.get_user_birthday(ctx.author, ctx.guild)

        if date:
            async with self.bot.get_cursor() as cursor:
                await cursor.execute("DELETE FROM birthdays WHERE guild_id = %s AND user_id = %s", (ctx.guild.id, ctx.author.id))
            await ctx.reply("Successfully removed. Your birthday won't be announced anymore.", ephemeral=True)
        else:
            await ctx.reply("You have no set birthdate for this server!", ephemeral=True)

    @birthday.command(name="set", description="Set your birth date for this guild")
    @app_commands.describe(date="The date (dd/mm/yyyy), e.g., '1/1/2000', '02/03/2004', '10.10.2010'")
    async def birthday_set(self, ctx: Context, date: commands.Range[str, 1, 16]):
        warning = await self.no_channel_warn(ctx.author)
        invalid_msg = f"That date format is incorrect. It must be the format `dd/mm/yyyy`.\n> Examples: `15/1/2003`, `06.06.2005`, `24.3.2007`{warning}"
        
        # Split using either . or /
        parts = re.split(r'[./]', date)

        # Must be only 3 parts: day, month, year
        if len(parts) != 3:
            return await ctx.reply(invalid_msg)

        try:
            day, month, year = map(int, parts)
            birth_date = datetime(year, month, day)
        except ValueError:
            return await ctx.reply(invalid_msg)

        current = await self.get_user_birthday(ctx.author, ctx.guild)
        if current:
            if (current.day == birth_date.day) and (current.month == birth_date.month) and (current.year == birth_date.year):
                return await ctx.reply("But your birthday is already set to that...")

        today = discord.utils.utcnow()
        age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))

        if age < 13:
            return await ctx.reply("You can't be under 13 years of age...", ephemeral=True)
        elif age > 100:
            return await ctx.reply("Now that's just too old...", ephemeral=True)

        last_announced = await self.get_year_last_announced(ctx.author, ctx.guild)
        now = discord.utils.utcnow()
        message = None
        if last_announced == now.year:
            is_in_same_year = (birth_date.month, birth_date.day) > (now.month, now.day) or (
                (birth_date.month == now.month and birth_date.day == now.day) and now.hour < 12
            )
            if is_in_same_year:
                view = YesOrNo(ctx.author)
                message = await ctx.reply(f"Your birthday has already been announced in this guild for this current year ({last_announced}), so it won't be announced until {last_announced+1}. Continue?", view=view)
                view.message = message
                await view.wait()

                if not view.value:
                    return

        async with self.bot.get_cursor() as cursor:
            await cursor.execute('''
                    INSERT INTO birthdays (user_id, guild_id, date)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE date = VALUES(date);
                ''', (ctx.author.id, ctx.guild.id, birth_date.strftime('%d.%m.%Y')))

        content_to_send = f"Your birthday has been set to `{self.format_date(birth_date)}`{warning}"
        if message is not None:
            return await message.edit(content=content_to_send, view=None)
        await ctx.reply(content_to_send)

    @commands.hybrid_command(name="birthday-channel", description="Configure birthday channel")
    @checks.hybrid_has_permissions(manage_guild=True)
    async def birthday_channel(self, ctx: Context):
        channel_id = await self.get_bday_channel(ctx.guild)

        status = f"Current: <#{channel_id}>" if channel_id else f"{tick(None)} Not configured"

        channel = await self.bot.get_or_fetch_channel(ctx.guild, channel_id)
        warning = f"\n-# {Emojis.warn} This channel doesn't seem to exist anymore." if not channel else ''
        view = ChannelSelector(self.bot, ctx.author, "Birthday", "birthdays")
        view.message = await ctx.reply(f"**Birthday Channel**\n{status}{warning}", view=view, ephemeral=True)

    @tasks.loop(time=time(12, 0, tzinfo=timezone.utc))
    async def birthday_notifier(self):
        now = discord.utils.utcnow()
        # `now.day` (& month) does not include 0 if single digit
        day = now.strftime('%d')
        month = now.strftime('%m')

        async with self.bot.get_cursor() as cursor:
            await cursor.execute('''
                SELECT guild_id, user_id, date, last_announced
                FROM birthdays
                WHERE SUBSTRING_INDEX(date, '.', 1) = %s -- day
                    AND SUBSTRING_INDEX(SUBSTRING_INDEX(date, '.', 2), '.', -1) = %s -- month
            ''', (day, month,))
        
            rows = await cursor.fetchall()

        index: dict[int, list[tuple[int, int]]] = {}
        for row in rows:
            guild_id: int = row[0]
            user_id: int = row[1]
            date: str = row[2]
            last_announced: int = row[3]

            # User's birthday already announced this year
            if last_announced == now.year: continue

            # If bot is not in the guild, skip it
            if guild_id not in [guild.id for guild in self.bot.guilds]:
                continue

            birthday_channel_id = await self.get_bday_channel(guild_id)
            # birthday channel not set
            if birthday_channel_id is None: continue
            year = int(date.split('.')[2])
            index.setdefault(guild_id, []).append((user_id, year))

        for guild_id, user_list in index.items():
            await asyncio.sleep(12.5)

            guild = await self.bot.get_or_fetch_guild(guild_id)
        
            channel = await self.bot.get_or_fetch_channel(guild, birthday_channel_id)
            if not channel:  # channel doesn't exist anymore
                async with self.bot.get_cursor() as cursor:
                    await cursor.execute("UPDATE channels SET fails = fails + 1 WHERE feature = %s AND channel_id = %s", ("birthdays", birthday_channel_id,))
                continue

            if not guild.chunked:
                await guild.chunk()
            
            birthday_people = []
            for user_id, year in user_list:
                user = guild.get_member(user_id)
                if not user: continue  # not in the server
                age = now.year - year
                birthday_people.append(f"Happy birthday to {user.mention}, who is now {age}! :sparkles:")

                # Update the last_announced field to the current year after announcing the birthday
                async with self.bot.get_cursor() as cursor:
                    await cursor.execute('''
                        UPDATE birthdays
                        SET last_announced = %s
                        WHERE user_id = %s AND guild_id = %s
                    ''', (now.year, user_id, guild_id))

            if birthday_people:
                num = len(birthday_people)
                footer = "May you " + ('' if num == 1 else 'both ' if num == 2 else 'all ') + "have a blessed day 🎂🎉"
                message = f"{'\n'.join(birthday_people)}\n\n{footer}"
                await channel.send(message)
        
        # Remove channels that have failed thrice, and most likely no longer exist
        async with self.bot.get_cursor() as cursor:
            await cursor.execute("DELETE FROM channels WHERE channel_id = fails > %s", (3,))


async def setup(bot: Woolinator) -> None:
    await bot.add_cog(Birthday(bot))
