from datetime import timedelta, datetime, timezone
import logging

import asyncio
import discord
from discord.ext import commands, tasks
from discord import app_commands, ui
from dateutil.relativedelta import relativedelta

from bot import Woolinator
from .utils.views import handle_view_edit
from .utils.context import Context
from .utils.common import parse_entered_duration, trim_str


log = logging.getLogger(__name__)


class RemindersRemoveView(ui.View):

    def __init__(self, reminders: list):
        super().__init__(timeout=60)
        self.reminders_to_remove = []

        self.add_item(RemindersRemoveDropdown(reminders=reminders))


class RemindersRemoveDropdown(ui.Select):

    def __init__(self, reminders: list):
        options = []
        for i, reminder in enumerate(reminders, start=1):
            _id = reminder[0]
            #time_created = reminder[1]
            #time_expire = reminder[2]
            content = trim_str(reminder[3], 32)

            options.append(discord.SelectOption(label=f"Reminder #{i}", description=content, value=_id))

        super().__init__(placeholder='...', options=options, min_values=1, max_values=len(reminders))
        self.reminders_to_remove = []

    async def callback(self, interaction: discord.Interaction):
        self.view.reminders_to_remove = [int(i) for i in self.values]
        await interaction.response.defer()
        self.view.stop()


class RemindersListView(ui.View):

    def __init__(self, author_id: int, reminders, bot: Woolinator, asyncio_timers: dict, timeout: int = 20):
        super().__init__(timeout=timeout)
        self.bot: Woolinator = bot
        self.author_id = author_id
        self.reminders = reminders
        self.reminders_to_remove = []
        self.message = None
        self.asyncio_timers = asyncio_timers

    @ui.button(label="Delete reminder(s)", emoji="\U0001f5d1", style=discord.ButtonStyle.red)
    async def delete_reminder(self, interaction: discord.Interaction, button: ui.Button):
        view = RemindersRemoveView(reminders=self.reminders)
        await interaction.response.send_message("Please select the reminder(s) you want to delete:", view=view, ephemeral=True)
        await view.wait()
        await interaction.delete_original_response()

        embed = discord.Embed(colour=discord.Colour.random())
        embed.set_author(name=interaction.user.name + "'s reminders", icon_url=interaction.user.display_avatar.url)
        for i, reminder in enumerate(self.reminders, start=1):
            _id = reminder[0]
            if _id in view.reminders_to_remove: continue
            time_created = reminder[1]
            time_expire = reminder[2]
            content = trim_str(reminder[3], 900)

            embed.add_field(name=f"Reminder #{i}",
                            value=f"Created: <t:{round(time_created.timestamp())}:F>\nExpires: <t:{round(time_expire.timestamp())}:F> (<t:{round(time_expire.timestamp())}:R>)\nContent: {content}",
                            inline=False)

        await interaction.message.edit(embed=embed)

        async with self.bot.get_cursor() as cursor:
            for reminder_id in view.reminders_to_remove:
                await cursor.execute("DELETE FROM reminders WHERE id = %s", (reminder_id,))

                task: asyncio.Task|None = self.asyncio_timers.get(reminder_id, None)
                if task:
                    del self.asyncio_timers[reminder_id]
                    task.cancel()

    async def on_timeout(self) -> None:
        button = self.children[0]  # only one button
        button.disabled = True

        await handle_view_edit(self.message, view=self)
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author_id and interaction.user.id != self.author_id:
            await interaction.response.send_message("Not your button to press .-.", ephemeral=True)
            return False
        return True


class Reminder(commands.Cog, name="Reminders", description="Never forget a thing again"):

    def __init__(self, bot: Woolinator) -> None:
        self.bot: Woolinator = bot

        # minutes; when changing, make sure to change task loop interval to match
        self.update_interval = 10

        self.asyncio_timers: dict[int, asyncio.Task] = {}
        if not self.sync_asyncio_timers.is_running():
            self.sync_asyncio_timers.start()

    async def cog_unload(self):
        for task in self.asyncio_timers.values():
            task.cancel()
        self.asyncio_timers.clear()
        self.sync_asyncio_timers.cancel()

    @property
    def emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name="reminder",id=1337677195694575626)

    @tasks.loop(minutes=10)
    async def sync_asyncio_timers(self):
        for task in self.asyncio_timers.values():
            task.cancel()
        self.asyncio_timers.clear()

        async with self.bot.get_cursor() as cursor:
            await cursor.execute('''
                    SELECT id, user_id, time_created, time_expire, content, is_dm, link
                    FROM reminders
                    WHERE time_expire < %s
                ''', (discord.utils.utcnow().astimezone(self.bot.sql_server_tz) + timedelta(minutes=self.update_interval),))
            reminders = await cursor.fetchall()

        for reminder in reminders:
            id: int = reminder[0]
            task = asyncio.create_task(self.handle_reminder_expiration(reminder))
            self.asyncio_timers[id] = task

    async def handle_reminder_expiration(self, reminder: tuple):
        time_expire: datetime = reminder[3].replace(tzinfo=timezone.utc)
        await asyncio.sleep((time_expire - discord.utils.utcnow()).total_seconds())

        async with self.bot.get_cursor() as cursor:
            await cursor.execute("DELETE FROM reminders WHERE id = %s", (reminder[0],))

        id: int = reminder[0]
        user_id: str = reminder[1]
        time_created: datetime = reminder[2].replace(tzinfo=timezone.utc)
        time_expire: datetime = reminder[3].replace(tzinfo=timezone.utc)
        content: str = reminder[4]
        is_dm: bool = reminder[5]
        link: str = reminder[6]

        user = await self.bot.get_or_fetch_user(reminder[1])

        if user is None:
            log.warning(
                f"User {user_id} was not found to remind them for a reminder set on {time_created.strftime('%Y/%m/%d %H:%M:%S')}")
            return

        message = f"{user.mention}, your reminder that you set on <t:{round(time_created.timestamp())}:f> has expired <t:{round(time_expire.timestamp())}:R>!\n\nHere's what you wanted to be reminded of:\n>>> {content}"
        view = ui.View()
        view.add_item(ui.Button(style=discord.ButtonStyle.link, label="Jump to when the reminder was made", url=link))

        failed_to_send = False
        if not is_dm:
            msg_details = link.split('/')
            guild = await self.bot.get_or_fetch_guild(int(msg_details[-3]))

            if guild is not None:

                member = await self.bot.get_or_fetch_member(guild, int(user_id))

                if member is None:
                    is_dm = True  # left guild
                else:
                    channel = await self.bot.get_or_fetch_channel(guild, int(msg_details[-2]))
                    try:
                        await channel.send(message, view=view)
                    except (discord.Forbidden, discord.HTTPException):
                        failed_to_send = True
            else:
                is_dm = True  # guild no longer exists
        if is_dm or failed_to_send:
            try:
                await user.send(message, view=view)
            except (discord.Forbidden, discord.HTTPException):
                pass

        # This should be last because cancelling the task while running is not good
        task = self.asyncio_timers.get(id, None)
        if task:
            del self.asyncio_timers[id]

    @commands.hybrid_command(name="remindme", aliases=["reminder"], description="Set a reminder")
    @commands.cooldown(4, 10.5, commands.BucketType.user)  # each reminder can send 2 messages
    @app_commands.describe(when="When you want to be reminded; e.g., '1d, 10 days, 5secs' (separated by comma)",
                           what="What you want to be reminded of")
    async def remindme(self, ctx: Context, when: commands.Range[str, 2, 50], *,
                       what: commands.Range[str, 1, 1234] = "...nothing?"):

        what = await commands.clean_content(use_nicknames=False).convert(ctx, what)
        now = discord.utils.utcnow()
        duration, invalid_formats, too_long = parse_entered_duration(when)

        if invalid_formats or too_long:

            invalid_message = ''
            if invalid_formats:
                invalid_list = ''
                for i, invalid_format in enumerate(invalid_formats, start=1):
                    invalid_list += f"{i}. {trim_str(invalid_format, 15)}\n"

                if invalid_list:
                    invalid_message = f"Invalid time format{'' if len(invalid_formats) == 1 else 's'}:\n{invalid_list}"

            too_long_message = ''
            if too_long:
                too_long_list = ''
                for i, too_long_values in enumerate(too_long, start=1):
                    too_long_list += f"{i}. {trim_str(too_long_values, 15)}\n"

                if too_long_list:
                    too_long_message = f"Time format{' that is too long' if len(too_long) == 1 else 's that are too long'} :\n{too_long_list}"

            return await ctx.reply('\n\n'.join([invalid_message, too_long_message]), ephemeral=True)

        when = now + duration

        if when > now + relativedelta(years=5, seconds=1):
            if when > now + relativedelta(years=20):
                return await ctx.reply("now that's just WAYYY too far into the future...", ephemeral=True)
            return await ctx.reply("that's too far into the future... please try less than 4 years!", ephemeral=True)

        is_dm_channel = True if isinstance(ctx.channel, discord.DMChannel) else False

        async with self.bot.get_cursor() as cursor:
            await cursor.execute('''
                    INSERT INTO reminders (user_id, time_created, time_expire, content, is_dm, link)
                    VALUES (%s, %s, %s, %s, %s, %s)
                ''', (ctx.author.id, now, when, what, is_dm_channel, ctx.message.jump_url))
            await cursor.execute("SELECT LAST_INSERT_ID()")
            id = (await cursor.fetchone())[0]

        remaining_time = when - now
        if remaining_time.total_seconds() < float(self.update_interval * 60):
            task = asyncio.create_task(self.handle_reminder_expiration(
                tuple((id, ctx.author.id, now, when, what, is_dm_channel, ctx.message.jump_url,))),
                                       name=f"reminder-{id}")
            self.asyncio_timers[id] = task

        await ctx.reply(f"Okay dokey, <t:{round(when.timestamp())}:R>: {what}", ephemeral=False)

    @commands.hybrid_command(name="reminders", description="View your reminders")
    async def reminders(self, ctx: Context):
        
        async with self.bot.get_cursor() as cursor:
            await cursor.execute('''
                    SELECT id, time_created, time_expire, content
                    FROM reminders
                    WHERE user_id = %s
                    ORDER BY time_created
                ''', (ctx.author.id,))
            reminders = await cursor.fetchall()

        if not reminders:
            return await ctx.reply("You have no reminders set... breh", ephemeral=True)

        embed = discord.Embed(colour=discord.Colour.random())
        embed.set_author(name=ctx.author.name + "'s reminders", icon_url=ctx.author.display_avatar.url)
        for i, reminder in enumerate(reminders, start=1):
            #id = reminder[0]
            ts_created = round(reminder[1].replace(tzinfo=timezone.utc).timestamp())
            ts_expire = round(reminder[2].replace(tzinfo=timezone.utc).timestamp())
            content = trim_str(reminder[3], 900)

            embed.add_field(name=f"Reminder #{i}",
                            value=f"Created: <t:{ts_created}:F>\nExpires: <t:{ts_expire}:F> (<t:{ts_expire}:R>)\nContent: {content}",
                            inline=False)

        view = RemindersListView(author_id=ctx.author.id, bot=self.bot, asyncio_timers=self.asyncio_timers,
                                 reminders=reminders)
        message = await ctx.reply(embed=embed, view=view)
        view.message = message


async def setup(bot: Woolinator) -> None:
    await bot.add_cog(Reminder(bot))
