import logging

import discord

log = logging.getLogger(__name__)

class YesOrNo(discord.ui.View):
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

    @discord.ui.button(label='Yuh uh', emoji='\U0001f44d', style=discord.ButtonStyle.green)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.value = True
        self.stop()

    @discord.ui.button(label='Nuh uh', emoji='\U0001f44e', style=discord.ButtonStyle.red)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content='Aborted.', embed=None, view=None, delete_after=20 if self.delete_after else None)
        self.value = False
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author_id and interaction.user.id != self.author_id:
            await interaction.response.send_message('not your button to press ,-,', ephemeral=True)
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

async def handle_view_edit(message: discord.Message|discord.InteractionMessage|discord.InteractionCallbackResponse|None, view=discord.ui.View):
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