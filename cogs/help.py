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


def resolve_display_prefix(bot: Woolinator, user: discord.User | discord.Member, guild: discord.Guild | None) -> str:
    """ The prefix to advertise in help, priority: personal > guild > default """
    personal_prefix = bot.user_prefixes.get(user.id)
    if personal_prefix:
        return personal_prefix

    if guild is not None:
        guild_prefix = bot.guild_prefixes.get(guild.id)
        if guild_prefix:
            return guild_prefix

    return bot.default_prefix


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
            option = discord.SelectOption(label=cog.qualified_name, value=cog.qualified_name, description=description, emoji=emoji)

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
        prefix = resolve_display_prefix(self.bot, interaction.user, interaction.guild)

        if selected == "Home":
            embed = get_home_embed(self.bot, interaction.user, prefix)

        else:
            cog = self.bot.get_cog(selected)
            embed = HelpCommand.build_cog_embed(cog, prefix)

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


def get_home_embed(bot: Woolinator, user: discord.Member|discord.User, prefix: str) -> discord.Embed:
    embed = discord.Embed(description="Welcome to the home page of the help command! :wave:\n\nSelect a category from the dropdown menu below to get help with specific features.", colour=0xffe3be)
    embed.set_author(name=f"Hello, {user.name}!", icon_url=user.display_avatar.url)
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.add_field(name="Who you?", value=f"Run {bot.cmd_mention('about')} to learn about me")
    embed.add_field(name="Prefix", value=f"Your prefix is `{prefix}`. Use {bot.cmd_mention('prefix')} to view all prefixes.", inline=False)
    embed.add_field(name="Usage", value=f"`{prefix}help <command> (subcommand)` (or run a command with no arguments) for help with a specific command or subcommand.\n\n*Examples:*\n- `{prefix}ban` (no arguments) or `{prefix}help ban`\n- `{prefix}help purge`", inline=False)
    return embed


class HelpCommand(commands.HelpCommand):

    def __init__(self) -> None:
        super().__init__(
            command_attrs={
                "cooldown": commands.CooldownMapping.from_cooldown(2, 8.0, commands.BucketType.member),
                "help": "Shows help about a command or a category",
            }
        )

    @property
    def display_prefix(self) -> str:
        """ The prefix to show in help for the member who invoked it (personal > guild > default). """
        return resolve_display_prefix(self.context.bot, self.context.author, self.context.guild)

    @staticmethod
    def shortest_name(command: commands.Command) -> str:
        """ The shortest of a command's name and its aliases. """
        return min((command.name, *command.aliases), key=len)

    @staticmethod
    def qualified_display_name(command: commands.Command, compact: bool = False) -> str:
        """ The command's qualified name, optionally using the shortest alias at each level (e.g. `rr add`). """
        if not compact:
            return command.qualified_name

        parts = []
        current = command
        while current is not None:
            parts.append(HelpCommand.shortest_name(current))
            current = current.parent
        return ' '.join(reversed(parts))

    @staticmethod
    def format_command_signature(command: commands.Command, prefix: str = "", compact: bool = False) -> str:
        """ Format a command signature as `<prefix><name> <args>` with <required> and (optional) arguments.

        `compact` swaps long command names for their shortest alias; use it in focused
        views (a single command/group) where it's already obvious what's being shown.
        """
        name = HelpCommand.qualified_display_name(command, compact=compact)
        signature_parts = [f"{prefix}{name}"]
        for _, param in command.clean_params.items():
            if param.required:
                signature_parts.append(f"<{param.name}>")
            else:
                signature_parts.append(f"({param.name})")
        return ' '.join(signature_parts)

    @staticmethod
    def add_help_footer(embed: discord.Embed) -> discord.Embed:
        """Add the standard argument legend footer to an embed."""
        embed.set_footer(text="<arg> = required  •  (arg) = optional")
        return embed

    @staticmethod
    def build_cog_embed(cog: commands.Cog, prefix: str) -> discord.Embed:
        """ Build the category overview embed shared by `?help <category>` and the dropdown. """
        visible_commands = sorted([cmd for cmd in cog.get_commands() if not cmd.hidden], key=lambda c: c.qualified_name)
        cmd_count = len(visible_commands)
        cog_desc = f"*{cog.description}*\n\n**{cmd_count} command{plur(cmd_count)}:**" if cog.description else f"**{cmd_count} command{plur(cmd_count)}:**"
        embed = discord.Embed(title=cog.qualified_name, description=cog_desc, colour=0xFFF4E6)

        for command in visible_commands:
            signature = HelpCommand.format_command_signature(command, prefix)
            value = command.description or '...'

            if isinstance(command, commands.Group):
                subs = sorted([s for s in command.commands if not s.hidden], key=lambda c: c.name)
                if subs:
                    value += f"\n**{len(subs)} subcommand{plur(len(subs))}:**"
                    for sub in subs:
                        sub_signature = HelpCommand.format_command_signature(sub, prefix, compact=True)
                        value += f"\n↳ `{sub_signature}` - {sub.description or '...'}"

            embed.add_field(name=signature, value=value, inline=False)

        HelpCommand.add_help_footer(embed)
        return embed

    async def send_bot_help(self, mapping: Mapping[commands.Cog|None, list[commands.Command]]):
        bot = self.context.bot
        view = CategorySelectMenuView(bot)
        embed = get_home_embed(bot, self.context.author, self.display_prefix)
        view.message = await self.get_destination().send(embed=embed, view=view)

    async def send_command_help(self, command: commands.Command):
        prefix = self.display_prefix
        embed = discord.Embed(description=f"*{command.description}*" if command.description else None, colour=0xFFF4E6)
        app_cmd = self.context.bot.tree.get_command(command.name, type=discord.AppCommandType.chat_input)

        if app_cmd:
            arg_descs = '\n'.join([f"**`{p.name}`**: {p.description}" for p in app_cmd.parameters])
            if arg_descs:
                embed.add_field(name="Arguments", value=arg_descs)

        # Surface alternative names so the (shorter) title isn't ambiguous.
        title_name = self.shortest_name(command)
        other_names = [name for name in (command.name, *command.aliases) if name != title_name]
        if other_names:
            embed.add_field(name="Also known as", value=', '.join(f"`{name}`" for name in other_names), inline=False)

        # Optional example usages, set per-command via extras={"examples": [...]}
        examples = command.extras.get("examples")
        if examples:
            qualified = self.qualified_display_name(command, compact=True)
            example_text = '\n'.join(f"`{prefix}{qualified} {ex}`" for ex in examples)
            embed.add_field(name="Examples", value=example_text, inline=False)

        # Focused view: it's already clear what this is, so show the compact name.
        embed.title = self.format_command_signature(command, prefix, compact=True)

        view = None
        if command.help:
            view = AdditionalNotesButton(discord.Embed(title="Additional Notes", description=command.help))

        self.add_help_footer(embed)
        m = await self.context.send(embed=embed, view=view)
        if hasattr(view, "message"): view.message = m

    async def send_group_help(self, group: commands.Group):
        prefix = self.display_prefix
        subcommands = sorted([cmd for cmd in group.commands if not cmd.hidden], key=lambda c: c.name)
        cmd_count = len(subcommands)

        desc_parts = []
        if group.description:
            desc_parts.append(f"*{group.description}*")
        if group.aliases:
            desc_parts.append("Aliases: " + ', '.join(f"`{alias}`" for alias in group.aliases))
        desc_parts.append(f"**{cmd_count} subcommand{plur(cmd_count)}:**")
        embed = discord.Embed(title=group.qualified_name, description='\n\n'.join(desc_parts), color=0xFFF4E6)

        for command in subcommands:
            # Focused view: prefix subcommands with the group's short alias (e.g. `?rr add`).
            signature = self.format_command_signature(command, prefix, compact=True)
            embed.add_field(name=signature, value=command.description or '...', inline=False)

        self.add_help_footer(embed)
        await self.get_destination().send(embed=embed)

    async def send_cog_help(self, cog: commands.Cog):
        embed = self.build_cog_embed(cog, self.display_prefix)
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
