import logging
from typing import Mapping

import discord
from discord.ext import commands
from discord import ui

from bot import Woolinator
from .utils.views import handle_view_edit
from .utils.common import plur
from .utils.context import Context

log = logging.getLogger(__name__)


class CategorySelectMenuView(ui.View):
    """ A custom View with a `ui.Select` item populated with the command categories. """

    def __init__(self, bot: Woolinator, *, timeout = 180):
        super().__init__(timeout=timeout)
        self.message = None
        self.add_item(CategorySelectMenu(bot))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        await handle_view_edit(self.message, view=self)

class CategorySelectMenu(ui.Select):

    def __init__(self, bot: Woolinator):
        self.bot: Woolinator = bot

        options = []
        misc_option = None
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
            # Add command count to description
            cmd_count = len(command_list)
            description_with_count = f"{description} • {cmd_count} command{plur(cmd_count)}"
            option = discord.SelectOption(label=cog.qualified_name, value=cog.qualified_name, description=description_with_count, emoji=emoji)

            # Keep Miscellaneous aside so it's always the last category
            if cog_name == "Miscellaneous":
                misc_option = option
                continue
            options.append(option)

        if misc_option is not None:
            options.append(misc_option)

        options.insert(0, discord.SelectOption(label="Home", value="Home", emoji="\U0001f44b"))
        super().__init__(placeholder="Select a category...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        if selected == "Home":
            embed = get_home_embed(self.bot, interaction.user)
        
        else:
            cog = self.bot.get_cog(selected)
            # Count non-hidden commands
            visible_commands = [cmd for cmd in cog.walk_commands() if not cmd.hidden]
            cmd_count = len(visible_commands)
            cog_desc = f"*{cog.description or '...'}*\n\n**{cmd_count} command{plur(cmd_count)}:**"
            embed = discord.Embed(title=selected, description=cog_desc, colour=0xFFF4E6)

            for command in visible_commands:
                signature = HelpCommand.format_command_signature(command, use_qualified=True)
                embed.add_field(name=signature, value=command.description or '...', inline=False)

            HelpCommand.add_help_footer(embed)

        await interaction.response.edit_message(embed=embed)


class AdditionalNotesButton(ui.View):
    """ A `ui.View` containing a button that will display parsed embed when pressed, providing 'Additional Context' for the current command. """

    def __init__(self, embed: discord.Embed|None = None, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.message = None
        self.embed = embed

    @ui.button(label="This command has additional context.", emoji="\U0001f6df", style=discord.ButtonStyle.green)
    async def button_callback(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message(embed=self.embed, ephemeral=True)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        await handle_view_edit(self.message, view=self)


def get_home_embed(bot: Woolinator, user: discord.Member|discord.User) -> discord.Embed:
    embed = discord.Embed(description="Welcome to the home page of the help command! :wave:\n\nSelect a category from the dropdown menu below to get help with specific features.", colour=0xffe3be)
    embed.set_author(name=f"Hello, {user.name}!", icon_url=user.display_avatar.url)
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    return embed


class HelpCommand(commands.HelpCommand):

    def __init__(self) -> None:
        super().__init__(
            command_attrs={
                "cooldown": commands.CooldownMapping.from_cooldown(2, 8.0, commands.BucketType.member),
                "help": "Shows help about a command or a category",
            }
        )

    @staticmethod
    def format_command_signature(command: commands.Command, use_qualified: bool = False) -> str:
        """Format a command signature with <required> and (optional) arguments."""
        signature_parts = [command.qualified_name if use_qualified else command.name]
        for name, param in command.clean_params.items():
            if param.required:
                signature_parts.append(f"<{param.name}>")
            else:
                signature_parts.append(f"({param.name})")
        return ' '.join(signature_parts)

    @staticmethod
    def add_help_footer(embed: discord.Embed) -> discord.Embed:
        """Add the standard help footer to an embed."""
        embed.set_footer(text="<arg> = required  |  (arg) = optional")
        return embed

    async def send_bot_help(self, mapping: Mapping[commands.Cog|None, list[commands.Command]]):
        bot = self.context.bot
        view = CategorySelectMenuView(bot)
        embed = get_home_embed(bot, self.context.author)
        view.message = await self.get_destination().send(embed=embed, view=view)
    
    async def send_command_help(self, command: commands.Command):
        embed = discord.Embed(description=f"*{command.description}*" if command.description else None, colour=0xFFF4E6)
        app_cmd = self.context.bot.tree.get_command(command.name, type=discord.AppCommandType.chat_input)

        if app_cmd:
            arg_descs = '\n'.join([f"**`{p.name}`**: {p.description}" for p in app_cmd.parameters])
            if arg_descs:
                embed.add_field(name="Arguments", value=arg_descs)

        # Optional example usages, set per-command via extras={"examples": [...]}
        examples = command.extras.get("examples")
        if examples:
            example_text = '\n'.join(f"`{self.context.clean_prefix}{command.qualified_name} {ex}`" for ex in examples)
            embed.add_field(name="Examples", value=example_text, inline=False)

        embed.title = self.format_command_signature(command, use_qualified=True)

        view = None
        if command.help:
            view = AdditionalNotesButton(discord.Embed(title="Additional Notes", description=command.help))

        self.add_help_footer(embed)
        m = await self.context.send(embed=embed, view=view)
        if hasattr(view, "message"): view.message = m

    async def send_group_help(self, group: commands.Group):
        cmd_count = len(group.commands)
        group_desc = f"*{group.description}*\n\n**{cmd_count} subcommand{plur(cmd_count)}:**" if group.description else f"**{cmd_count} subcommand{plur(cmd_count)}:**"
        embed = discord.Embed(title=group.qualified_name, description=group_desc, color=0xFFF4E6)

        for command in group.commands:
            signature = self.format_command_signature(command)
            embed.add_field(name=signature, value=command.description, inline=False)

        self.add_help_footer(embed)
        await self.get_destination().send(embed=embed)

    async def send_cog_help(self, cog: commands.Cog):
        visible_commands = [cmd for cmd in cog.get_commands() if not cmd.hidden]
        cmd_count = len(visible_commands)
        cog_desc = f"*{cog.description}*\n\n**{cmd_count} command{plur(cmd_count)}:**" if cog.description else f"**{cmd_count} command{plur(cmd_count)}:**"
        embed = discord.Embed(title=cog.qualified_name, description=cog_desc, color=0xFFF4E6)

        for command in visible_commands:
            signature = self.format_command_signature(command)
            embed.add_field(name=signature, value=command.description, inline=False)

        self.add_help_footer(embed)
        await self.get_destination().send(embed=embed)

    async def on_help_command_error(self, ctx: Context, error: commands.CommandError):
        if isinstance(error, commands.CommandInvokeError):
            # Ignore missing permission errors
            if isinstance(error.original, discord.HTTPException) and error.original.code == 50013:
                return

            await ctx.send(str(error.original))


class Help(commands.Cog, command_attrs=dict(hidden=True)):

    def __init__(self, bot: Woolinator) -> None:
        self.bot = bot
        self._original_help_command: commands.HelpCommand|None = bot.help_command
        bot.help_command = HelpCommand()
        bot.help_command.cog = self  # type: ignore

    def cog_unload(self):
        self.bot.help_command = self._original_help_command


async def setup(bot: Woolinator) -> None:
    await bot.add_cog(Help(bot))
