import logging

import discord
from discord import ui
from discord.ext import commands
from discord.utils import escape_markdown as rmd

from .utils import checks
from .utils.common import trim_str
from .utils.context import Context
from .utils.emojis import Emojis
from .utils.views import handle_view_edit

from bot import Woolinator


log = logging.getLogger(__name__)


# Registry of configurable log types
LOG_FEATURES: dict[str, dict[str, str]] = {
    "log-mod-actions": {
        "label": "Mod Actions",
        "desc": "Kicks, bans, mutes, purges, etc.",
        "emoji": Emojis.Flags.discord_certified_moderator,
    },
    "log-messages": {
        "label": "Messages",
        "desc": "Edited & deleted messages",
        "emoji": Emojis.text_bubble,
    },
    "log-voice": {
        "label": "Voice",
        "desc": "Members joining, leaving or moving voice channels",
        "emoji": "🔊",
    },
    "log-joins": {
        "label": "Joins & Leaves",
        "desc": "Members joining & leaving the server",
        "emoji": "🚪",
    },
    "log-nicknames": {
        "label": "Nicknames",
        "desc": "Member nickname changes",
        "emoji": "🏷️",
    },
    "log-roles": {
        "label": "Roles",
        "desc": "Roles added to or removed from members",
        "emoji": "🎭",
    },
}

ACCENT = 0xFFF9E0

# Channel types offered when picking channels/categories to exclude from message logs
IGNORE_CHANNEL_TYPES = [
    discord.ChannelType.text,
    discord.ChannelType.news,
    discord.ChannelType.voice,
    discord.ChannelType.stage_voice,
    discord.ChannelType.forum,
    discord.ChannelType.category,
]


class FeatureSelect(ui.Select):
    """ Overview dropdown: pick a log type to configure. """

    def __init__(self, parent: "LoggingView"):
        self.lview = parent
        options = []
        for code, meta in LOG_FEATURES.items():
            name = parent._channel_name(parent.config.get(code))
            options.append(discord.SelectOption(
                label=meta["label"],
                value=code,
                description=trim_str(f"Currently: {name}" if name else "Not configured", 100),
                emoji=meta["emoji"],
            ))
        super().__init__(placeholder="Choose a log type to configure…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        code = self.values[0]
        self.lview.show_feature(code)
        await interaction.response.edit_message(embed=self.lview.feature_embed(code), view=self.lview)


class FeatureChannelSelect(ui.ChannelSelect):
    """ Feature dropdown: pick the channel a log type is sent to. """

    def __init__(self, parent: "LoggingView", code: str):
        self.lview = parent
        self.code = code
        super().__init__(placeholder="Select a channel…", min_values=1, max_values=1, channel_types=[discord.ChannelType.text])
        current = parent.config.get(code)
        if current:
            self.default_values = [discord.Object(id=current)]

    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]
        await self.lview.cog.set_channel(self.lview.guild_id, self.code, channel.id)
        await self.lview.cog.set_mod_log_setup_done(self.lview.guild_id, True)
        self.lview.config[self.code] = channel.id
        self.lview.show_overview()
        await interaction.response.edit_message(embed=self.lview.overview_embed(), view=self.lview)


class MessageIgnoreSelect(ui.ChannelSelect):
    """ Dropdown: pick channels/categories to exclude from message logs. """

    def __init__(self, parent: "LoggingView"):
        self.lview = parent
        super().__init__(
            placeholder="Ignore channels for message logs…",
            min_values=0,
            max_values=25,
            channel_types=IGNORE_CHANNEL_TYPES,
        )
        guild = parent.bot.get_guild(parent.guild_id)
        # Only pre-select channels that still exist, otherwise Discord rejects the component
        defaults = [discord.Object(id=cid) for cid in parent.ignored if guild and guild.get_channel(cid)]
        if defaults:
            self.default_values = defaults

    async def callback(self, interaction: discord.Interaction):
        ids = [channel.id for channel in self.values]
        await self.lview.cog.set_ignored_channels(self.lview.guild_id, ids)
        self.lview.ignored = set(ids)
        self.lview.show_feature("log-messages")
        await interaction.response.edit_message(embed=self.lview.feature_embed("log-messages"), view=self.lview)


class DisableButton(ui.Button):
    def __init__(self, parent: "LoggingView"):
        self.lview = parent
        super().__init__(label="Disable this log", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        code = self.lview.active_feature
        await self.lview.cog.remove_channel(self.lview.guild_id, code)
        self.lview.config[code] = None
        self.lview.show_overview()
        await interaction.response.edit_message(embed=self.lview.overview_embed(), view=self.lview)


class BackButton(ui.Button):
    def __init__(self, parent: "LoggingView"):
        self.lview = parent
        super().__init__(label="Back", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        self.lview.show_overview()
        await interaction.response.edit_message(embed=self.lview.overview_embed(), view=self.lview)


class LoggingView(ui.View):
    """ Overview -> per-feature channel picker. """

    def __init__(self, cog: "Logging", author: discord.User | discord.Member, guild_id: int, config: dict[str, int | None], ignored: set[int]):
        super().__init__(timeout=120)
        self.cog = cog
        self.bot = cog.bot
        self.author_id = author.id
        self.guild_id = guild_id
        self.config = config
        self.ignored = ignored
        self.active_feature: str | None = None
        self.message = None
        self.show_overview()

    def _channel_name(self, channel_id: int | None) -> str | None:
        if not channel_id:
            return None
        guild = self.bot.get_guild(self.guild_id)
        channel = guild.get_channel(channel_id) if guild else None
        return f"#{channel.name}" if channel else None

    def _format_ignored(self, channel_id: int) -> str:
        """ Categories show as their plain name (no #); channels keep their #mention. """
        guild = self.bot.get_guild(self.guild_id)
        channel = guild.get_channel(channel_id) if guild else None
        if isinstance(channel, discord.CategoryChannel):
            return rmd(channel.name)
        return f"<#{channel_id}>"

    def overview_embed(self) -> discord.Embed:
        lines = []
        for code, meta in LOG_FEATURES.items():
            channel_id = self.config.get(code)
            status = f"<#{channel_id}>" if channel_id else "*Not set*"
            lines.append(f"{meta['emoji']} **{meta['label']}:** {status}\n-# > {meta['desc']}")
        embed = discord.Embed(title="Server Logging", description='\n\n'.join(lines), colour=ACCENT)
        embed.set_footer(text="Pick a log type below to set or change its channel")
        return embed

    def feature_embed(self, code: str) -> discord.Embed:
        meta = LOG_FEATURES[code]
        channel_id = self.config.get(code)
        status = f"Currently logging to <#{channel_id}>" if channel_id else "Not currently set"
        verb = "change" if channel_id else "set"
        desc = f"{meta['desc']}\n\n{status}\n\nSelect a channel below to {verb} where these logs are sent."
        if code == "log-messages":
            if self.ignored:
                ignored_str = ', '.join(self._format_ignored(cid) for cid in self.ignored)
            else:
                ignored_str = "*None*"
            desc += f"\n\n**Ignored:**\n> -# Edits & deletions in these channels (or categories) won't be logged.\n{ignored_str}"
        embed = discord.Embed(
            title=f"{meta['emoji']} {meta['label']}",
            description=desc,
            colour=ACCENT,
        )
        return embed

    def show_overview(self):
        self.clear_items()
        self.active_feature = None
        self.add_item(FeatureSelect(self))

    def show_feature(self, code: str):
        self.clear_items()
        self.active_feature = code
        self.add_item(FeatureChannelSelect(self, code))
        if code == "log-messages":
            self.add_item(MessageIgnoreSelect(self))
        if self.config.get(code):
            self.add_item(DisableButton(self))
        self.add_item(BackButton(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("not your button to press ,-,", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await handle_view_edit(self.message, view=self)


class Logging(commands.Cog, name="Logging", description="Configure server event logging"):

    def __init__(self, bot: Woolinator) -> None:
        self.bot: Woolinator = bot
        self._webhooks: dict[int, discord.Webhook] = {}

    @property
    def emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name="\U0001f4dd")

    # --- Database helpers ---

    async def get_log_channel(self, guild: discord.Guild | int, feature: str) -> int | None:
        """ Get snowflake channel ID for a log feature, `None` if it isn't set. """
        guild_id = guild.id if isinstance(guild, discord.Guild) else guild
        async with self.bot.get_cursor() as cursor:
            await cursor.execute("SELECT channel_id FROM channels WHERE feature = %s AND guild_id = %s", (feature, guild_id))
            res = await cursor.fetchone()
        return res[0] if res else None

    async def get_all_log_channels(self, guild_id: int) -> dict[str, int | None]:
        """ Map every known log feature to its configured channel ID (or `None`). """
        config: dict[str, int | None] = {code: None for code in LOG_FEATURES}
        async with self.bot.get_cursor() as cursor:
            await cursor.execute("SELECT feature, channel_id FROM channels WHERE guild_id = %s", (guild_id,))
            rows = await cursor.fetchall()
        for feature, channel_id in rows:
            if feature in config:
                config[feature] = channel_id
        return config

    async def set_channel(self, guild_id: int, feature: str, channel_id: int) -> None:
        async with self.bot.get_cursor() as cursor:
            await cursor.execute('''
                    INSERT INTO channels (feature, guild_id, channel_id)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE channel_id = %s
                ''', (feature, guild_id, channel_id, channel_id))

    async def remove_channel(self, guild_id: int, feature: str) -> None:
        async with self.bot.get_cursor() as cursor:
            await cursor.execute("DELETE FROM channels WHERE guild_id = %s AND feature = %s", (guild_id, feature))

    async def remove_channel_by_id(self, guild_id: int, channel_id: int) -> None:
        """ Drop every feature config pointing at a (now-gone) channel. """
        async with self.bot.get_cursor() as cursor:
            await cursor.execute("DELETE FROM channels WHERE guild_id = %s AND channel_id = %s", (guild_id, channel_id))

    async def get_ignored_channels(self, guild_id: int) -> set[int]:
        """ Channels/categories whose messages should be excluded from message logs. """
        async with self.bot.get_cursor() as cursor:
            await cursor.execute("SELECT channel_id FROM ignored_log_channels WHERE guild_id = %s", (guild_id,))
            rows = await cursor.fetchall()
        return {row[0] for row in rows}

    async def set_ignored_channels(self, guild_id: int, channel_ids: list[int]) -> None:
        """ Replace the whole ignored-channel set for a guild with the given IDs. """
        async with self.bot.get_cursor() as cursor:
            await cursor.execute("DELETE FROM ignored_log_channels WHERE guild_id = %s", (guild_id,))
            if channel_ids:
                await cursor.executemany(
                    "INSERT INTO ignored_log_channels (guild_id, channel_id) VALUES (%s, %s)",
                    [(guild_id, cid) for cid in channel_ids],
                )

    async def remove_ignored_channel(self, guild_id: int, channel_id: int) -> None:
        """ Drop a single ignored entry (e.g. when its channel/category is deleted). """
        async with self.bot.get_cursor() as cursor:
            await cursor.execute("DELETE FROM ignored_log_channels WHERE guild_id = %s AND channel_id = %s", (guild_id, channel_id))

    async def is_channel_ignored(self, guild_id: int, channel: discord.abc.GuildChannel | discord.Thread) -> bool:
        """ True if the channel, its category, or its thread parent is on the ignore list. """
        ignored = await self.get_ignored_channels(guild_id)
        if not ignored:
            return False
        candidates = {channel.id}
        parent = getattr(channel, "parent", None)
        if parent is not None:
            candidates.add(parent.id)
            parent_category = getattr(parent, "category_id", None)
            if parent_category:
                candidates.add(parent_category)
        category_id = getattr(channel, "category_id", None)
        if category_id:
            candidates.add(category_id)
        return not candidates.isdisjoint(ignored)

    async def get_mod_log_setup_done(self, guild_id: int) -> bool:
        async with self.bot.get_cursor() as cursor:
            await cursor.execute("SELECT mod_log_setup_done FROM guild_settings WHERE guild_id = %s", (guild_id,))
            res = await cursor.fetchone()
        return bool(res[0]) if res else False

    async def set_mod_log_setup_done(self, guild_id: int, value: bool = True) -> None:
        async with self.bot.get_cursor() as cursor:
            await cursor.execute('''
                    INSERT INTO guild_settings (guild_id, mod_log_setup_done)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE mod_log_setup_done = %s
                ''', (guild_id, int(value), int(value)))

    # --- Sending ---

    async def _get_webhook(self, channel: discord.TextChannel) -> discord.Webhook | None:
        """ Get (or lazily create + cache) a bot-owned webhook for the channel. """
        cached = self._webhooks.get(channel.id)
        if cached is not None:
            return cached

        if not channel.permissions_for(channel.guild.me).manage_webhooks:
            return None

        try:
            for wh in await channel.webhooks():
                if wh.user and wh.user.id == self.bot.user.id:
                    self._webhooks[channel.id] = wh
                    return wh

            avatar = None
            try:
                avatar = await self.bot.user.display_avatar.read()
            except discord.HTTPException:
                pass

            wh = await channel.create_webhook(name="Woolinator Logs", avatar=avatar, reason="Logging webhook")
            self._webhooks[channel.id] = wh
            return wh
        except discord.HTTPException:
            return None

    async def _send_via_webhook(self, channel: discord.TextChannel, embed: discord.Embed, view: ui.View | None = None) -> bool:
        """ Send a log embed through a webhook, falling back to a normal message. """
        wh = await self._get_webhook(channel)
        if wh is not None:
            kwargs = dict(embed=embed, username=self.bot.user.name, avatar_url=self.bot.user.display_avatar.url)
            if view is not None:
                kwargs["view"] = view
                kwargs["wait"] = True
            try:
                await wh.send(**kwargs)
                return True
            except discord.NotFound:
                self._webhooks.pop(channel.id, None)
                wh = await self._get_webhook(channel)
                if wh is not None:
                    try:
                        await wh.send(**kwargs)
                        return True
                    except discord.HTTPException:
                        pass
            except discord.HTTPException:
                pass

        try:
            if view is not None:
                await channel.send(embed=embed, view=view)
            else:
                await channel.send(embed=embed)
            return True
        except discord.HTTPException:
            return False

    async def send_log(self, guild: discord.Guild, feature: str, embed: discord.Embed, view: ui.View | None = None) -> bool:
        """ Send a log embed to the configured channel for a feature, if set. """
        channel_id = await self.get_log_channel(guild, feature)
        if channel_id is None:
            return False

        channel = guild.get_channel(channel_id)
        if channel is None:
            try:
                channel = await guild.fetch_channel(channel_id)
            except discord.NotFound:
                # Channel was deleted (e.g. while the bot was offline) - drop the stale config
                await self.remove_channel_by_id(guild.id, channel_id)
                return False
            except discord.HTTPException:
                return False  # transient failure - leave the config intact

        return await self._send_via_webhook(channel, embed, view)

    # --- Mod log entry point (called by the Moderation cog) ---

    async def handle_mod_log(self, guild: discord.Guild, embed: discord.Embed) -> bool:
        """ Send a mod-log embed, auto-creating the channel on first use if needed. """
        embed.timestamp=discord.utils.utcnow()
        channel_id = await self.get_log_channel(guild, "log-mod-actions")
        if channel_id is None:
            channel = await self.maybe_auto_create_mod_log(guild)
            if channel is None:
                return False
            return await self._send_via_webhook(channel, embed)
        return await self.send_log(guild, "log-mod-actions", embed)

    async def maybe_auto_create_mod_log(self, guild: discord.Guild) -> discord.TextChannel | None:
        """ Create a mods-only mod-log channel once per guild, with an info message. """
        if await self.get_mod_log_setup_done(guild.id):
            return None

        me = guild.me
        if me is None or not me.guild_permissions.manage_channels:
            return None
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            me: discord.PermissionOverwrite(view_channel=True, send_messages=True, embed_links=True, manage_webhooks=True),
        }
        for role in guild.roles:
            if role.permissions.manage_guild or role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True)

        try:
            channel = await guild.create_text_channel(
                "log-mod-actions",
                overwrites=overwrites,
                reason="Auto-created mod log channel (no logging configured)",
            )
        except discord.HTTPException:
            log.warning("Failed to auto-create mod-log channel in guild %s", guild.id)
            return None
        
        await self.set_mod_log_setup_done(guild.id, True)
        await self.set_channel(guild.id, "log-mod-actions", channel.id)

        info = discord.Embed(
            title="Mod log channel created",
            description=(
                "Channel was created because no mod-log channel has been set. "
                "To disable mod logging, either delete this channel and I won't bother you again "
                f"or configure logging channels with the {self.bot.cmd_mention('logging')} command."
            ),
            colour=ACCENT,
        )
        try:
            await channel.send(embed=info)
        except discord.HTTPException:
            pass

        return channel

    # --- Event listeners ---

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        """ Clean up any log/feature configs when their channel is deleted. """
        self._webhooks.pop(channel.id, None)
        await self.remove_channel_by_id(channel.guild.id, channel.id)
        await self.remove_ignored_channel(channel.guild.id, channel.id)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        if await self.is_channel_ignored(message.guild.id, message.channel):
            return

        embed = discord.Embed(
            description=trim_str(message.content, 4096) if message.content else "*No text content*",
            colour=0xf93838,
            timestamp=message.created_at,
        )
        embed.set_author(name=f"@{message.author.name}", icon_url=message.author.display_avatar.url)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        if message.attachments:
            embed.add_field(name="Attachments", value='\n'.join(f"- {a.filename}" for a in message.attachments), inline=False)
        embed.set_footer(text=f"Message Deleted • User ID: {message.author.id}")
        await self.send_log(message.guild, "log-messages", embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if after.guild is None or after.author.bot or before.content == after.content:
            return
        if await self.is_channel_ignored(after.guild.id, after.channel):
            return

        embed = discord.Embed(colour=0xff8d42, timestamp=after.edited_at or discord.utils.utcnow())
        embed.set_author(name=f"@{after.author.name}", icon_url=after.author.display_avatar.url)
        embed.add_field(name="Before", value=trim_str(before.content or "*empty*", 1024), inline=False)
        embed.add_field(name="After", value=trim_str(after.content or "*empty*", 1024), inline=False)
        embed.add_field(name="Channel", value=after.channel.mention, inline=True)
        embed.set_footer(text=f"Message Edited • User ID: {after.author.id}")

        view = ui.View()
        view.add_item(ui.Button(style=discord.ButtonStyle.link, label="Jump to Message", url=after.jump_url))
        await self.send_log(after.guild, "log-messages", embed, view=view)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot or before.channel == after.channel:
            return

        if before.channel is None:
            action, detail, colour = "joined", after.channel.mention, 0x83f590
        elif after.channel is None:
            action, detail, colour = "left", before.channel.mention, 0xf93838
        else:
            action, detail, colour = "moved", f"{before.channel.mention} → {after.channel.mention}", ACCENT

        embed = discord.Embed(description=f"**Channel:** {detail}", colour=colour, timestamp=discord.utils.utcnow())
        embed.set_author(name=f"@{member.name} {action} a voice channel", icon_url=member.display_avatar.url)
        embed.set_footer(text=f"Voice {action.capitalize()} • User ID: {member.id}")
        await self.send_log(member.guild, "log-voice", embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = discord.Embed(description=member.mention, colour=0x83f590, timestamp=discord.utils.utcnow())
        embed.set_author(name=f"@{member.name} joined", icon_url=member.display_avatar.url)
        embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, "R"), inline=True)
        embed.add_field(name="Member Count", value=f"{member.guild.member_count:,}", inline=True)
        embed.set_footer(text=f"Member Joined • User ID: {member.id}")
        await self.send_log(member.guild, "log-joins", embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = discord.Embed(description=member.mention, colour=0xf93838, timestamp=discord.utils.utcnow())
        embed.set_author(name=f"@{member.name} left", icon_url=member.display_avatar.url)
        if member.joined_at:
            embed.add_field(name="Joined", value=discord.utils.format_dt(member.joined_at, "R"), inline=True)
        roles = [r.mention for r in reversed(member.roles) if not r.is_default()]
        if roles:
            embed.add_field(name=f"Roles [{len(roles)}]", value=trim_str(', '.join(roles), 1024), inline=False)
        embed.set_footer(text=f"Member Left • User ID: {member.id}")
        await self.send_log(member.guild, "log-joins", embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.nick != after.nick:
            embed = discord.Embed(colour=0xff8d42, timestamp=discord.utils.utcnow())
            embed.set_author(name=f"@{after.name} changed nickname", icon_url=after.display_avatar.url)
            embed.add_field(name="Before", value=trim_str(rmd(before.nick), 1024) if before.nick else "*None*", inline=True)
            embed.add_field(name="After", value=trim_str(rmd(after.nick), 1024) if after.nick else "*None*", inline=True)
            embed.set_footer(text=f"Nickname Changed • User ID: {after.id}")
            await self.send_log(after.guild, "log-nicknames", embed)

        added = [r for r in after.roles if r not in before.roles]
        removed = [r for r in before.roles if r not in after.roles]
        if added or removed:
            embed = discord.Embed(colour=ACCENT, timestamp=discord.utils.utcnow())
            embed.set_author(name=f"@{after.name}'s roles updated", icon_url=after.display_avatar.url)
            if added:
                embed.add_field(name="Added", value=trim_str(', '.join(r.mention for r in added), 1024), inline=False)
            if removed:
                embed.add_field(name="Removed", value=trim_str(', '.join(r.mention for r in removed), 1024), inline=False)
            embed.set_footer(text=f"Roles Updated • User ID: {after.id}")
            await self.send_log(after.guild, "log-roles", embed)

    # --- Command ---

    @commands.hybrid_command(name="logging", description="Configure server logging channels")
    @commands.guild_only()
    @checks.hybrid_has_permissions(manage_guild=True)
    async def logging_command(self, ctx: Context):
        config = await self.get_all_log_channels(ctx.guild.id)
        ignored = await self.get_ignored_channels(ctx.guild.id)
        view = LoggingView(self, ctx.author, ctx.guild.id, config, ignored)
        view.message = await ctx.reply(embed=view.overview_embed(), view=view, ephemeral=True)


async def setup(bot: Woolinator) -> None:
    await bot.add_cog(Logging(bot))
