import logging

import discord
from discord import ui

from bot import Woolinator
from cogs.utils.emojis import tick

log = logging.getLogger(__name__)

class ChannelSelector(ui.View):
    def __init__(self, bot: Woolinator, author: discord.User|discord.Member|int, feature: str, code: str):
        super().__init__(timeout=30)
        self.bot = bot
        self.message = None
        self.author_id = author if isinstance(author, int) else author.id
        self.feature = feature
        self.code = code

    @ui.select(cls=ui.ChannelSelect, placeholder=f"Select a channel...", channel_types=[discord.ChannelType.text])
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
    async def disable(self, interaction: discord.Interaction, button: ui.Button):
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