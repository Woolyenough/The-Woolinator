import re
import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot import Woolinator
from .utils import checks
from .utils.emojis import tick
from .utils.context import Context
from .utils.pagination import PaginationEmbedsView

log = logging.getLogger(__name__)

# Matches a Discord message jump link, capturing the channel and message IDs.
MESSAGE_LINK_RE = re.compile(
    r"(?:https?://)?(?:\w+\.)?discord(?:app)?\.com/channels/(?:\d+|@me)/(\d+)/(\d+)/?"
)

class _MemberCooldownMapping(commands.CooldownMapping):
    """ A `CooldownMapping` keyed by an explicit value instead of a `Message`.

    Reaction events carry no `Message`, so the default key extraction can't be
    used; we pass a ``(guild_id, user_id)`` tuple straight through.
    """

    def _bucket_key(self, key: tuple[int, int]) -> tuple[int, int]:
        return key


class ReactionRoles(commands.Cog, name="Reaction Roles", description="Let members self-assign roles by reacting"):

    def __init__(self, bot: Woolinator) -> None:
        self.bot: Woolinator = bot
        # message_id -> { emoji_key: role_id }
        self.cache: dict[int, dict[str, int]] = {}
        self._cooldown = _MemberCooldownMapping.from_cooldown(
            6, 30.0, commands.BucketType.member
        )

    async def cog_load(self):
        self.cache = {}
        async with self.bot.get_cursor() as cursor:
            await cursor.execute("SELECT message_id, emoji, role_id FROM reaction_roles")
            rows = await cursor.fetchall()

        for message_id, emoji, role_id in rows:
            self.cache.setdefault(message_id, {})[emoji] = role_id

    async def cog_check(self, ctx: Context) -> bool:
        if ctx.guild is None: raise commands.NoPrivateMessage()
        return True

    @property
    def emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name="\U0001f9e9")

    # --- Helpers ---

    @staticmethod
    def emoji_key(emoji: discord.PartialEmoji) -> str:
        """ Canonical key used to match a reaction against the database.

        Custom emojis are keyed by their ID (immune to renames), unicode emojis
        by the character itself.
        """
        return str(emoji.id) if emoji.id else emoji.name

    async def fetch_bound_message(self, ctx: Context, channel_id: int | None, message_id: int) -> discord.Message | None:
        """ Fetch a message in this guild from a parsed reference, or ``None``. """
        if channel_id is None:
            channel = ctx.channel
        else:
            channel = await self.bot.get_or_fetch_channel(ctx.guild, channel_id)

        if channel is None or getattr(channel, "guild", None) is None or channel.guild.id != ctx.guild.id:
            return None

        if not isinstance(channel, discord.abc.Messageable):
            return None

        try:
            return await channel.fetch_message(message_id)
        except discord.HTTPException:
            return None

    def validate_role(self, ctx: Context, role: discord.Role) -> str | None:
        """ Return an error string if ``role`` can't be used, otherwise ``None``. """
        if role.is_default():
            return "You can't bind the @everyone role..."

        if role.managed:
            return "That role is managed by an integration (e.g. a bot or boosts) and can't be assigned manually."

        me = ctx.guild.me
        if role >= me.top_role:
            return f"That role is higher than my highest role, so I can't assign it. Move my role above {role.mention} and try again."

        # Owners and admins bypass the self-hierarchy guard.
        if ctx.author.id != ctx.guild.owner_id and not ctx.author.guild_permissions.administrator:
            if role >= ctx.author.top_role:
                return "You can't bind a role that's higher than or equal to your own highest role."

        return None

    async def remove_bot_reaction(self, channel_id: int | None, message_id: int, guild: discord.Guild, emoji: discord.PartialEmoji) -> None:
        """ Best-effort removal of a bound reaction from the message after unbinding. """
        try:
            channel = guild.get_channel(channel_id) if channel_id else None
            if channel is None:
                return
            message = await channel.fetch_message(message_id)
            try:
                await message.clear_reaction(emoji)  # needs Manage Messages
            except discord.Forbidden:
                await message.remove_reaction(emoji, guild.me)
        except (discord.HTTPException, AttributeError):
            pass

    # --- Listeners ---

    async def _resolve_member(self, payload: discord.RawReactionActionEvent, guild: discord.Guild) -> discord.Member | None:
        if payload.member is not None:
            return payload.member
        return await self.bot.get_or_fetch_member(guild, payload.user_id)

    def _rate_limited(self, guild_id: int, user_id: int) -> bool:
        """ True (and consumes a token) if this member is over the role-change rate limit. """
        bucket = self._cooldown.get_bucket((guild_id, user_id))
        return bucket.update_rate_limit() is not None

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None or payload.user_id == self.bot.user.id:
            return

        bindings = self.cache.get(payload.message_id)
        if not bindings:
            return

        role_id = bindings.get(self.emoji_key(payload.emoji))
        if role_id is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        role = guild.get_role(role_id)
        if role is None:
            # Role was deleted out from under us; drop the stale binding.
            await self._forget_role(guild.id, role_id)
            return

        member = await self._resolve_member(payload, guild)
        if member is None or member.bot or role in member.roles:
            return

        if not guild.me.guild_permissions.manage_roles or role >= guild.me.top_role:
            return

        if self._rate_limited(guild.id, member.id):
            log.debug("Rate-limited reaction role add for %s in %s", member.id, guild.id)
            return

        try:
            await member.add_roles(role, reason="Reaction role")
        except discord.HTTPException:
            log.warning("Failed to add reaction role %s to %s in %s", role_id, member.id, guild.id)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None or payload.user_id == self.bot.user.id:
            return

        bindings = self.cache.get(payload.message_id)
        if not bindings:
            return

        role_id = bindings.get(self.emoji_key(payload.emoji))
        if role_id is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        role = guild.get_role(role_id)
        if role is None:
            await self._forget_role(guild.id, role_id)
            return

        member = await self._resolve_member(payload, guild)
        if member is None or member.bot or role not in member.roles:
            return

        if not guild.me.guild_permissions.manage_roles or role >= guild.me.top_role:
            return

        if self._rate_limited(guild.id, member.id):
            log.debug("Rate-limited reaction role remove for %s in %s", member.id, guild.id)
            return

        try:
            await member.remove_roles(role, reason="Reaction role removed")
        except discord.HTTPException:
            log.warning("Failed to remove reaction role %s from %s in %s", role_id, member.id, guild.id)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if payload.message_id not in self.cache:
            return

        self.cache.pop(payload.message_id, None)
        async with self.bot.get_cursor() as cursor:
            await cursor.execute("DELETE FROM reaction_roles WHERE message_id = %s", (payload.message_id,))

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        affected = [mid for mid in payload.message_ids if mid in self.cache]
        if not affected:
            return

        for message_id in affected:
            self.cache.pop(message_id, None)

        placeholders = ', '.join(['%s'] * len(affected))
        async with self.bot.get_cursor() as cursor:
            await cursor.execute(f"DELETE FROM reaction_roles WHERE message_id IN ({placeholders})", tuple(affected))

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await self._forget_role(role.guild.id, role.id)

    async def _forget_role(self, guild_id: int, role_id: int) -> None:
        """ Purge every binding for a role (DB + cache), e.g. after the role is deleted. """
        async with self.bot.get_cursor() as cursor:
            await cursor.execute("DELETE FROM reaction_roles WHERE guild_id = %s AND role_id = %s", (guild_id, role_id))

        for message_id in list(self.cache):
            bindings = self.cache[message_id]
            for key in [k for k, rid in bindings.items() if rid == role_id]:
                del bindings[key]
            if not bindings:
                del self.cache[message_id]

    # --- Commands ---

    @commands.hybrid_group(name="reaction-role", aliases=["rr"], fallback="list",
                           description="List the reaction roles set up in this server")
    @checks.hybrid_has_permissions(manage_roles=True, manage_guild=True)
    async def reactionrole(self, ctx: Context):
        async with self.bot.get_cursor() as cursor:
            await cursor.execute('''
                    SELECT channel_id, message_id, emoji_display, role_id
                    FROM reaction_roles
                    WHERE guild_id = %s
                    ORDER BY channel_id, message_id, id
                ''', (ctx.guild.id,))
            rows = await cursor.fetchall()

        if not rows:
            await ctx.reply(f"No reaction roles are set up yet. Add one with {self.bot.cmd_mention('reaction-role add')}.", ephemeral=True)
            return

        # Group bindings by the message they live on, preserving order.
        grouped: dict[tuple[int, int], list[str]] = {}
        for channel_id, message_id, emoji_display, role_id in rows:
            line = f"{emoji_display} → <@&{role_id}>"
            grouped.setdefault((channel_id, message_id), []).append(line)

        embeds: list[discord.Embed] = []
        items = list(grouped.items())
        # 10 messages per page keeps us well under the 25-field embed limit.
        for page_start in range(0, len(items), 10):
            embed = discord.Embed(title="Reaction Roles", colour=0xFFF4E6)
            embed.set_footer(text=f"{len(rows)} binding{'' if len(rows) == 1 else 's'} across {len(items)} message{'' if len(items) == 1 else 's'}")
            for (channel_id, message_id), lines in items[page_start:page_start + 10]:
                jump = f"https://discord.com/channels/{ctx.guild.id}/{channel_id}/{message_id}"
                embed.add_field(name=f"#{getattr(ctx.guild.get_channel(channel_id), 'name', 'unknown-channel')}",
                                value=f"[Jump to message]({jump})\n" + '\n'.join(lines), inline=False)
            embeds.append(embed)

        if len(embeds) == 1:
            await ctx.reply(embed=embeds[0])
        else:
            view = PaginationEmbedsView(embeds, author_id=ctx.author.id)
            view.message = await ctx.reply(embed=embeds[0], view=view)

    @reactionrole.command(name="add", aliases=["create"], description="Bind an emoji reaction on a message to a role", extras={
        "examples": ["https://discord.com/channels/.../.../... \U0001f3ae @Gamer", "1234567890 :custom_emoji: @Member", "1234567890-1234567890 \U0001f601 @Happy"],
    })
    @app_commands.describe(message="Link or ID of the message to add the reaction to", emoji="The emoji members react with", role="The role to grant")
    @checks.hybrid_has_permissions(manage_roles=True, manage_guild=True)
    @commands.bot_has_permissions(manage_roles=True, add_reactions=True, read_message_history=True)
    async def reactionrole_add(self, ctx: Context, message: discord.Message, emoji: str, role: discord.Role):
        role_error = self.validate_role(ctx, role)
        if role_error:
            await ctx.reply(role_error, ephemeral=True)
            return

        partial_emoji = discord.PartialEmoji.from_str(emoji.strip())
        if partial_emoji is None or (not partial_emoji.id and not partial_emoji.name):
            await ctx.reply("That doesn't look like a valid emoji.", ephemeral=True)
            return

        key = self.emoji_key(partial_emoji)

        bindings = self.cache.get(message.id, {})
        if key in bindings:
            await ctx.reply("That emoji is already bound to a role on that message. Remove it first if you want to rebind it.", ephemeral=True)
            return

        max_bindings = 20
        if len(bindings) >= max_bindings:
            await ctx.reply(f"That message already has the maximum of {max_bindings} reaction roles.", ephemeral=True)
            return

        target = await self.fetch_bound_message(ctx, message.channel.id, message.id)
        if target is None:
            await ctx.reply("I couldn't find that message. Make sure it's in this server and I can see the channel.", ephemeral=True)
            return

        try:
            await target.add_reaction(partial_emoji)
        except discord.HTTPException:
            await ctx.reply("I couldn't react with that emoji. It might be invalid, or a custom emoji from a server I'm not in.", ephemeral=True)
            return

        async with self.bot.get_cursor() as cursor:
            await cursor.execute('''
                    INSERT INTO reaction_roles (guild_id, channel_id, message_id, emoji, emoji_display, role_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE emoji_display = VALUES(emoji_display), role_id = VALUES(role_id), channel_id = VALUES(channel_id)
                ''', (ctx.guild.id, target.channel.id, message.id, key, str(partial_emoji), role.id))

        self.cache.setdefault(message.id, {})[key] = role.id
        await ctx.reply(f"{tick(True)} Done! Reacting with {partial_emoji} on [that message]({target.jump_url}) will now grant {role.mention}.")

    @reactionrole.command(name="remove", aliases=["delete", "rm", "del"], description="Unbind an emoji from a role on a message")
    @app_commands.describe(message="Link or ID of the message", emoji="The bound emoji to remove")
    @checks.hybrid_has_permissions(manage_roles=True, manage_guild=True)
    async def reactionrole_remove(self, ctx: Context, message: discord.Message, emoji: str):

        partial_emoji = discord.PartialEmoji.from_str(emoji.strip())
        if partial_emoji is None or (not partial_emoji.id and not partial_emoji.name):
            await ctx.reply("That doesn't look like a valid emoji.", ephemeral=True)
            return

        key = self.emoji_key(partial_emoji)

        if key not in self.cache.get(message.id, {}):
            await ctx.reply("There's no reaction role bound to that emoji on that message.", ephemeral=True)
            return

        async with self.bot.get_cursor() as cursor:
            await cursor.execute("SELECT channel_id FROM reaction_roles WHERE guild_id = %s AND message_id = %s AND emoji = %s",
                                 (ctx.guild.id, message.id, key))
            row = await cursor.fetchone()
            await cursor.execute("DELETE FROM reaction_roles WHERE guild_id = %s AND message_id = %s AND emoji = %s",
                                 (ctx.guild.id, message.id, key))

        self.cache[message.id].pop(key, None)
        if not self.cache[message.id]:
            del self.cache[message.id]

        await self.remove_bot_reaction(row[0] if row else message.channel.id, message.id, ctx.guild, partial_emoji)
        await ctx.reply(f"{tick(True)} Removed the {partial_emoji} reaction role from that message.")

    @reactionrole.command(name="clear", description="Remove every reaction role from a message")
    @app_commands.describe(message="Link or ID of the message to clear")
    @checks.hybrid_has_permissions(manage_roles=True)
    async def reactionrole_clear(self, ctx: Context, message: discord.Message):

        if message.id not in self.cache:
            await ctx.reply("That message has no reaction roles bound to it.", ephemeral=True)
            return

        count = len(self.cache[message.id])

        async with self.bot.get_cursor() as cursor:
            await cursor.execute("SELECT channel_id FROM reaction_roles WHERE guild_id = %s AND message_id = %s LIMIT 1", (ctx.guild.id, message.id))
            row = await cursor.fetchone()
            await cursor.execute("DELETE FROM reaction_roles WHERE guild_id = %s AND message_id = %s", (ctx.guild.id, message.id))

        self.cache.pop(message.id, None)

        # Best-effort: clear our reactions from the message if it still exists.
        stored_channel_id = row[0] if row else message.channel.id
        try:
            channel = ctx.guild.get_channel(stored_channel_id) if stored_channel_id else ctx.channel
            if channel is not None:
                target = await channel.fetch_message(message.id)
                await target.clear_reactions()
        except (discord.HTTPException, AttributeError):
            pass

        await ctx.reply(f"{tick(True)} Cleared {count} reaction role{'' if count == 1 else 's'} from that message.")


async def setup(bot: Woolinator) -> None:
    await bot.add_cog(ReactionRoles(bot))
