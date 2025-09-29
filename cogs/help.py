import logging
from typing import Mapping

import discord
from discord.ext import commands

from bot import Woolinator
from .utils.views import handle_view_edit
from .utils.context import Context

log = logging.getLogger(__name__)


class CategorySelectMenuView(discord.ui.View):
    """ A custom View with a `ui.Select` item populated with the command categories. """

    def __init__(self, bot: Woolinator, *, timeout = 180):
        super().__init__(timeout=timeout)
        self.message = None
        self.add_item(CategorySelectMenu(bot))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        await handle_view_edit(self.message, view=self)

class CategorySelectMenu(discord.ui.Select):

    def __init__(self, bot: Woolinator):
        self.bot: Woolinator = bot

        options = []
        for cog_name, cog in self.bot.cogs.items():
            if cog_name == "Help": continue
            command_list = []
            for command in cog.get_commands():
                if command.hidden: continue
                command_list.append(command)

            if len(command_list) == 0:
                continue

            description = getattr(cog, "description", "No description")
            emoji = getattr(cog, "emoji", None)
            options.append(discord.SelectOption(label=cog.qualified_name, value=cog.qualified_name, description=description, emoji=emoji))

        options.insert(0, discord.SelectOption(label="Home", value="Home", emoji="\U0001f44b"))
        super().__init__(placeholder="Select a category...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        if selected == "Home":
            embed = get_home_embed(interaction.user)
        
        else:
            cog = self.bot.get_cog(selected)
            embed = discord.Embed(title=selected, description=cog.description or '...', colour=discord.Colour(0xA8B9CD))

            for command in cog.walk_commands():
                command.signature
                signature = f"{command.qualified_name} {command.signature}"
                embed.add_field(name=signature, value=command.description or '...', inline=False)

        await interaction.response.edit_message(embed=embed)


class AdditionalNotesButton(discord.ui.View):
    """ A `discord.ui.View` containing a button that will display parsed embed when pressed, providing 'Additional Context' for the current command. """

    def __init__(self, embed: discord.Embed|None = None, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.message = None
        self.embed = embed

    @discord.ui.button(label="This command has additional context.", emoji="\U0001f6df", style=discord.ButtonStyle.green)
    async def button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=self.embed, ephemeral=True)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        await handle_view_edit(self.message, view=self)


def get_home_embed(user: discord.Member|discord.User) -> discord.Embed:
    """ Create and get a personalised main menu help embed. """

    return discord.Embed(
        title="Help",
        description=f":wave: Hello, {user.mention}, and welcome to the home page of the help command. \n\n**Warning:** The help feature is currently still under development.\n\nSelect a category in the dropdown menu to get help with specific features.",
        color=discord.Color.blurple()
    )


class HelpCommand(commands.HelpCommand):

    def __init__(self) -> None:
        super().__init__(
            command_attrs={
                "cooldown": commands.CooldownMapping.from_cooldown(2, 6.0, commands.BucketType.member),
                "help": "Shows help about a command or a category",
            }
        )

    async def send_bot_help(self, mapping: Mapping[commands.Cog|None, list[commands.Command]]):
        bot = self.context.bot
        view = CategorySelectMenuView(bot)
        view.message = await self.get_destination().send(embed=get_home_embed(self.context.author), view=view)
    
    async def send_command_help(self, command: commands.Command):
        embed = discord.Embed(description=command.description, colour=discord.Colour(0xA8B9CD))
        app_cmd = self.context.bot.tree.get_command(command.name, type=discord.AppCommandType.chat_input)

        if app_cmd:
            arg_descs = '\n'.join([f"**`{p.name}`**: {p.description}" for p in app_cmd.parameters])
            if arg_descs:
                embed.add_field(name="Parameter Descriptions", value=arg_descs)

        signature = [command.qualified_name, ]
        for name, param in command.clean_params.items():
            if param.required:
                signature.append(f"<{param.name}>")
            else:
                signature.append(f"({param.name})")

        embed.title = ' '.join(signature)

        view = None
        if command.help:
            view = AdditionalNotesButton(discord.Embed(title="Additional Notes", description=command.help))

        embed.set_footer(text="<arg> = required  |  (arg) = optional")
        m = await self.context.send(embed=embed, view=view)
        if hasattr(view, "message"): view.message = m

    async def send_group_help(self, group: commands.Group):
        embed = discord.Embed(title=group.qualified_name, description=group.description, color=discord.Color.blurple())

        for command in group.commands:
            embed.add_field(name=command.name, value=command.description, inline=False)

        await self.get_destination().send(embed=embed)

    async def send_cog_help(self, cog: commands.Cog):
        embed = discord.Embed(title=cog.qualified_name, description=cog.description, color=discord.Color.blurple())

        for command in cog.get_commands():
            embed.add_field(name=command.name, value=command.description, inline=False)

        await self.get_destination().send(embed=embed)

    async def on_help_command_error(self, ctx: Context, error: commands.CommandError):
        if isinstance(error, commands.CommandInvokeError):
            # Ignore missing permission errors
            if isinstance(error.original, discord.HTTPException) and error.original.code == 50013:
                return

            await ctx.send(str(error.original))


class Help(commands.Cog, command_attrs=dict(hidden=True)):

    def __init__(self, bot: Woolinator) -> None:
        self.bot: Woolinator = bot
        self._original_help_command: commands.HelpCommand|None = bot.help_command
        bot.help_command = HelpCommand()
        bot.help_command.cog = self  # type: ignore

    def cog_unload(self):
        self.bot.help_command = self._original_help_command


async def setup(bot: Woolinator) -> None:
    await bot.add_cog(Help(bot))
