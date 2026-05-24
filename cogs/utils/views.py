import io
import logging

import discord
from discord import ui

from bot import Woolinator
from cogs.utils.emojis import tick, Emojis
from cogs.utils.common import trim_str, plur

log = logging.getLogger(__name__)

class ChannelSelector(ui.View):
    def __init__(self, bot: Woolinator, author: discord.User|discord.Member|int, feature: str, code: str, current_channel: discord.TextChannel|int|None = None):
        super().__init__(timeout=30)
        self.bot = bot
        self.message = None
        self.author_id = author if isinstance(author, int) else author.id
        self.feature = feature
        self.code = code
        self.current_channel_id = current_channel.id if isinstance(current_channel, discord.TextChannel) else current_channel
        
        # Update the select with preconfigure if a channel is already set
        if self.current_channel_id:
            for item in self.children:
                if isinstance(item, ui.ChannelSelect):
                    item.default_values = [discord.Object(id=self.current_channel_id)]
        else:
            # Remove the disable button if no channel is currently set
            self.remove_item(self.disable_button)

    @ui.select(cls=ui.ChannelSelect, placeholder=f"Select a channel to enable feature...", channel_types=[discord.ChannelType.text])
    async def select_channel(self, interaction: discord.Interaction, select: ui.ChannelSelect):
        channel = select.values[0]
        async with self.bot.get_cursor() as cursor:
            await cursor.execute('''
                    INSERT INTO channels (feature, guild_id, channel_id)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE channel_id = %s
                ''', (self.code, interaction.guild_id, channel.id, channel.id))
        await interaction.response.edit_message(content=f"{tick(True)} {self.feature} channel set to {channel.mention}", view=None)
        self.stop()

    @ui.button(label="Remove (disables feature)", style=discord.ButtonStyle.danger)
    async def disable_button(self, interaction: discord.Interaction, button: ui.Button):
        async with self.bot.get_cursor() as cursor:
            await cursor.execute("DELETE FROM channels WHERE guild_id = %s AND feature = %s", (interaction.guild_id, self.code))
        await interaction.response.edit_message(content=f"{tick(False)} {self.feature} disabled", view=None)
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

class YesOrNo(ui.View):
    """ A Discord UI view that includes a 'Yes' and 'No' buttons.

    Attributes:
        value (Optional[bool]): The result of the interaction. `True` if 'Yes', `False` if 'No', or `None` if timed out.
    """

    def __init__(self, author: discord.User|discord.Member|int, timeout: int = 60, delete_after: bool = False):
        super().__init__(timeout=timeout)
        if isinstance(author, discord.User) or isinstance(author, discord.Member): author = author.id
        self.author_id = author
        self.value = None
        self.message = None
        self.delete_after = delete_after

    @ui.button(label="Yuh uh", emoji="\U0001f44d", style=discord.ButtonStyle.green)
    async def yes(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        self.value = True
        self.stop()

    @ui.button(label="Nuh uh", emoji="\U0001f44e", style=discord.ButtonStyle.red)
    async def no(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="Aborted.", embed=None, view=None, delete_after=20 if self.delete_after else None)
        self.value = False
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author_id and interaction.user.id != self.author_id:
            await interaction.response.send_message("not your button to press ,-,", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.delete_after:
            if self.message:

                if isinstance(self.message, discord.InteractionCallbackResponse):
                    self.message = self.message.resource

                try:
                    await self.message.delete()
                except (discord.NotFound, discord.HTTPException):
                    pass

        else:
            for item in self.children:
                item.disabled = True

            await handle_view_edit(self.message, view=self)

def _make_attachment(file_data: tuple[bytes, str] | None) -> list[discord.File]:
    if file_data:
        return [discord.File(io.BytesIO(file_data[0]), file_data[1])]
    return []


class GlobalGuildSwitchView(ui.View):
    """Toggleable Global / Guild embed view, used for avatars, banners, and user info."""

    def __init__(self,
        author_id: int,
        global_embed: discord.Embed | None,
        guild_embed: discord.Embed | None,
        global_file: tuple[bytes, str] | None = None,
        guild_file: tuple[bytes, str] | None = None,
        default_guild: bool = True,
        timeout: int | None = 180
    ):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.message = None
        self.global_embed = global_embed
        self.guild_embed = guild_embed
        self.global_file = global_file
        self.guild_file = guild_file

        if global_embed is None:
            self._set_btn(0, enabled=False, selected=False)
            self._set_btn(1, enabled=False, selected=True)
            self.stop()
        elif guild_embed is None:
            self._set_btn(0, enabled=False, selected=True)
            self._set_btn(1, enabled=False, selected=False)
            self.stop()
        elif default_guild:
            self._set_btn(0, enabled=True, selected=None)
            self._set_btn(1, enabled=False, selected=True)
        else:
            self._set_btn(0, enabled=False, selected=True)
            self._set_btn(1, enabled=True, selected=None)

    def _set_btn(self, index: int, enabled: bool, selected: bool | None):
        btn = self.children[index]
        btn.disabled = not enabled
        btn.style = discord.ButtonStyle.green if selected else discord.ButtonStyle.grey if selected is None else discord.ButtonStyle.red
        btn.emoji = tick(selected)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("not your button to press ,-,", ephemeral=True)
            return False
        return True

    @ui.button(label="Global", style=discord.ButtonStyle.grey)
    async def display_global(self, interaction: discord.Interaction, button: ui.Button):
        self._set_btn(0, enabled=False, selected=True)
        self._set_btn(1, enabled=True, selected=None)
        await interaction.response.edit_message(embed=self.global_embed, attachments=_make_attachment(self.global_file), view=self)

    @ui.button(label="Guild", style=discord.ButtonStyle.grey)
    async def display_guild(self, interaction: discord.Interaction, button: ui.Button):
        self._set_btn(0, enabled=True, selected=None)
        self._set_btn(1, enabled=False, selected=True)
        await interaction.response.edit_message(embed=self.guild_embed, attachments=_make_attachment(self.guild_file), view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await handle_view_edit(self.message, view=self)


class GuildInfoView(ui.View):
    """ Buttons for the `guild` command, each revealing extra info as an ephemeral embed. """

    def __init__(self, guild: discord.Guild, timeout: int | None = 180):
        super().__init__(timeout=timeout)
        self.guild = guild
        self.message = None

    @ui.button(label="Emojis", emoji="\U0001f600", style=discord.ButtonStyle.grey)
    async def emojis_button(self, interaction: discord.Interaction, button: ui.Button):
        guild = self.guild
        embed = discord.Embed(title=f"Emojis", colour=discord.Colour.blurple())

        if not guild.emojis:
            embed.description = "*This server has no custom emojis.*"
        else:
            static = ' '.join(str(e) for e in guild.emojis if not e.animated)
            animated = ' '.join(str(e) for e in guild.emojis if e.animated)

            sections = []
            if static:
                sections.append(f"**Static**\n{static}")
            if animated:
                sections.append(f"**Animated**\n{animated}")

            embed.description = trim_str('\n\n'.join(sections), 4096)
            embed.set_footer(text=f"{len(guild.emojis)} / {guild.emoji_limit} emojis")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Boosters", emoji=Emojis.server_boost, style=discord.ButtonStyle.grey)
    async def boosters_button(self, interaction: discord.Interaction, button: ui.Button):
        guild = self.guild
        embed = discord.Embed(title=f"Boosting Members", colour=0xf47fff)

        boosters = sorted(guild.premium_subscribers, key=lambda m: m.premium_since or m.joined_at)
        if not boosters:
            embed.description = "*No one is boosting this server right now.*"
        else:
            lines = [
                f"{m.mention} (<t:{round(m.premium_since.timestamp())}:R>)" if m.premium_since else m.mention
                for m in boosters
            ]
            embed.description = trim_str('\n'.join(lines), 4096)
            embed.set_footer(text=f"{len(boosters)} booster{plur(len(boosters))} • {guild.premium_subscription_count or 0} boosts")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Staff", emoji=Emojis.Flags.discord_certified_moderator, style=discord.ButtonStyle.grey)
    async def staff_button(self, interaction: discord.Interaction, button: ui.Button):
        guild = self.guild
        embed = discord.Embed(title=f"Staff Members", colour=discord.Colour.blurple())

        # Highest-privilege category wins, so each member appears only once.
        admins, managers, mods = [], [], []
        for m in sorted(guild.members, key=lambda m: (m.id != guild.owner_id, -m.top_role.position)):
            perms = m.guild_permissions
            is_owner = m.id == guild.owner_id

            if is_owner or perms.administrator:
                bucket = admins
            elif perms.manage_guild:
                bucket = managers
            elif perms.kick_members or perms.ban_members or perms.moderate_members or perms.manage_messages:
                bucket = mods
            else:
                continue

            suffix = " (owner)" if is_owner else " (bot)" if m.bot else ""
            bucket.append(f"{m.mention}{suffix}")

        sections = []
        if admins:
            sections.append(f"**Administrators [{len(admins)}]**\n" + '\n'.join(admins))
        if managers:
            sections.append(f"**Manage Server [{len(managers)}]**\n" + '\n'.join(managers))
        if mods:
            sections.append(f"**Moderators [{len(mods)}]**\n" + '\n'.join(mods))

        if not sections:
            embed.description = "*No staff members found.*"
        else:
            embed.description = trim_str('\n\n'.join(sections), 4096)
            total = len(admins) + len(managers) + len(mods)
            embed.set_footer(text=f"{total} staff member{plur(total)}")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await handle_view_edit(self.message, view=self)


async def handle_view_edit(message: discord.Message|discord.InteractionMessage|discord.InteractionCallbackResponse|None, view=ui.View):
    """ Edit a hybrid message (`Message`/`InteractionMessage`), ignoring exceptions. """

    if message:
        try:
            if isinstance(message, discord.InteractionCallbackResponse):
                message = message.resource
                if not isinstance(message, discord.InteractionMessage):
                    return
                    
            await message.edit(view=view)
        except (discord.NotFound, discord.HTTPException):
            pass