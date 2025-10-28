import os
import logging
from contextlib import asynccontextmanager
from datetime import timezone, datetime

import asyncmy
import discord
from discord import app_commands
from discord.ext import commands
import aiohttp

from cogs.utils.context import Context

log = logging.getLogger(__name__)

# all slash commands are hybrid commands, and majority of it's features use `commands` package instead of `app_commands`
class AppCommandsTree(app_commands.CommandTree):
    pass

class Woolinator(commands.Bot):
    session: aiohttp.ClientSession
    pool: asyncmy.Pool
    bot_app_info: discord.AppInfo

    def __init__(self):
        super().__init__(
            command_prefix=_get_prefix_callable,
            intents=discord.Intents.all(),
            tree_cls=AppCommandsTree,
            activity=discord.Activity(type=discord.ActivityType.watching, name='meow meow meow meow meoowww'),
            allowed_mentions=discord.AllowedMentions(roles=False, everyone=False, users=True, replied_user=False),
        )

        self.default_prefix = '?'
        self.guild_prefixes = {}
        self.user_prefixes = {}

        self.spam_control = commands.CooldownMapping.from_cooldown(4, 7.5, commands.BucketType.user)

    async def setup_hook(self) -> None:
        self.session = aiohttp.ClientSession()
        self.bot_app_info = await self.application_info()

        async with self.get_cursor() as cursor:

            with open('database.sql', "r", encoding="utf-8") as f:
                sql = f.read()

            # Remove comments
            lines = []
            for line in sql.splitlines():
                if not line.strip().startswith('--'):
                    lines.append(line)
            cleaned_sql = '\n'.join(lines)

            # Split into statements
            statements = [s.strip() for s in cleaned_sql.split(';') if s.strip()]
            for statement in statements:
                await cursor.execute(statement)

            # Get the SQL server's UTC offset, for certain features
            await cursor.execute("SELECT TIMEDIFF(NOW(), UTC_TIMESTAMP);")
            self.sql_server_tz = timezone((await cursor.fetchone())[0])

            # Get prefixes
            await cursor.execute('SELECT entity_id, is_guild, prefix FROM prefixes')
            rows = await cursor.fetchall()

        # Populate the guild & user prefixes dicts
        for row in rows:
            entity_id: int = row[0]
            is_guild: bool = row[1]
            prefix: str = row[2]

            if is_guild is True:
                self.guild_prefixes[entity_id] = prefix
            else:
                self.user_prefixes[entity_id] = prefix

        for extension in [f'cogs.{file}' for file in os.listdir('cogs')]:
            if extension.endswith('.py'):
                extension = extension[:-3]
            else: continue

            try:
                await self.load_extension(extension)
                log.info('Loaded extension: %s', extension)
            except Exception:
                log.exception('Failed to load extension %s.', extension)

    @asynccontextmanager
    async def get_cursor(self):
        conn = await self.pool.acquire()
        try:
            async with conn.cursor() as cursor:
                yield cursor
        finally:
            await self.pool.release(conn)

    @property
    def owner(self) -> discord.User:
        return self.bot_app_info.owner

    async def start(self) -> None:
        await super().start(os.getenv('BOT_TOKEN'))

    async def close(self) -> None:
        log.info(' - Closing the connection to Discord')
        await super().close()
        log.info(' - Closing the SQL connection pool')
        self.pool.close()
        await self.pool.wait_closed()
        log.info(' - Closing aiohttp ClientSession')
        await self.session.close()
        log.info('Done. Bye!')

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        await self.process_commands(message)

    async def get_context(self, message: discord.Interaction|discord.Message, *, cls=Context):
        return await super().get_context(message, cls=cls)

    async def process_commands(self, message: discord.Message):
        ctx = await self.get_context(message)

        if ctx.command is None:
            return

        log.info(f'{ctx.author.name} ({f'in {ctx.guild.name}' if ctx.guild else 'in DM\'s'}) executing: ?{ctx.command.qualified_name}')

        bucket = self.spam_control.get_bucket(message)
        current = message.created_at.timestamp()
        retry_after = bucket and bucket.update_rate_limit(current)

        if retry_after:
            return

        await self.invoke(ctx)

    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.command:
            log.info(f'{interaction.user.name} ({f'in {interaction.guild.name}' if interaction.guild else 'in DM\'s'}) executing: /{interaction.command.qualified_name}')

    async def on_ready(self) -> None:
        if not hasattr(self, 'uptime'):
            self.uptime = round(discord.utils.utcnow().timestamp())

        log.info('Ready as %s (%s)', self.user, self.user.id)

        log.info('I am in the following guilds:')
        for i, guild in enumerate(self.guilds, start=1):
            log.info(' %s. %s (%s)', i, guild.name, guild.id)

    async def get_or_fetch_guild(self, guild_id: int) -> discord.Guild|None:
        guild = self.get_guild(guild_id)
        if guild is not None:
            return guild

        try:
            guild = await self.fetch_guild(guild_id)
        except (discord.HTTPException, discord.NotFound):
            return None
        else:
            return guild

    async def get_or_fetch_channel(self, guild: discord.Guild, channel_id: int):
        channel = guild.get_channel(channel_id)
        if channel is not None:
            return channel

        try:
            channel = await guild.fetch_channel(channel_id)
        except (discord.HTTPException, discord.NotFound):
            return None
        else:
            return channel

    async def get_or_fetch_member(self, guild: discord.Guild, member_id: int) -> discord.Member|None:
        member = guild.get_member(member_id)
        if member is not None:
            return member

        try:
            member = await guild.fetch_member(member_id)
        except (discord.HTTPException, discord.NotFound):
            return None
        else:
            return member

    async def get_or_fetch_user(self, user_id: int) -> discord.User|None:
        user = self.get_user(user_id)
        if user is not None:
            return user

        try:
            user = await self.fetch_user(user_id)
        except (discord.HTTPException, discord.NotFound):
            return None
        else:
            return user

    async def get_or_fetch_role(self, guild: discord.Guild, role_id: int) -> discord.Role|None:
        role = guild.get_role(role_id)
        if role is not None:
            return role

        try:
            role = await guild.fetch_role(role_id)
        except (discord.HTTPException, discord.NotFound):
            return None
        else:
            return role


def _get_prefix_callable(bot: Woolinator, msg: discord.Message):
    user_id = bot.user.id
    base = [f'<@!{user_id}> ', f'<@{user_id}> ']

    personal_prefix: str = bot.user_prefixes.get(msg.author.id, '')
    if len(personal_prefix) != 0:
        base.append(personal_prefix)

    if msg.guild:
        guild_prefix: str = bot.guild_prefixes.get(msg.guild.id, '')
        if len(guild_prefix) != 0:
            base.append(guild_prefix)

    if len(base) == 2:
        base.append(bot.default_prefix)

    return base
