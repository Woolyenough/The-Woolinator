import logging

import discord
from discord import ui

from .views import handle_view_edit


log = logging.getLogger(__name__)


class PaginationEmbedsView(ui.View):
    """ A `ui.View` class to paginate a list of embeds. """

    def __init__(self, embeds: list[discord.Embed], timeout: int = 300, author_id: int|None = None) -> None:
        super().__init__(timeout=timeout)
        self.embeds = embeds
        self.current_page = 0
        self.author_id = author_id
        self.message = None

        self.update_button_states()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author_id and interaction.user.id != self.author_id:
            await interaction.response.send_message("you are not the owner of this message grr", ephemeral=True)
            return False
        return True

    def update_button_states(self) -> None:
        self.first_page_button.disabled = self.current_page == 0
        self.prev_button.disabled = self.current_page == 0
        self.page_counter.label = f"Page {self.current_page + 1}/{len(self.embeds)}"
        self.next_button.disabled = self.current_page == len(self.embeds) - 1
        self.last_page_button.disabled = self.current_page == len(self.embeds) - 1

    @ui.button(label="≪", style=discord.ButtonStyle.gray)
    async def first_page_button(self, interaction: discord.Interaction, button: ui.Button):
        self.current_page = 0
        self.update_button_states()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @ui.button(label="Previous", style=discord.ButtonStyle.blurple)
    async def prev_button(self, interaction: discord.Interaction, button: ui.Button):
        self.current_page -= 1
        self.update_button_states()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @ui.button(label="Page 0/0", style=discord.ButtonStyle.gray)
    async def page_counter(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("This button doesn't do anything :stuck_out_tongue_winking_eye:", ephemeral=True)

    @ui.button(label="Next", style=discord.ButtonStyle.blurple)
    async def next_button(self, interaction: discord.Interaction, button: ui.Button):
        self.current_page += 1
        self.update_button_states()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @ui.button(label="≫", style=discord.ButtonStyle.gray)
    async def last_page_button(self, interaction: discord.Interaction, button: ui.Button):
        self.current_page = len(self.embeds) - 1
        self.update_button_states()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True

        await handle_view_edit(self.message, view=self)

