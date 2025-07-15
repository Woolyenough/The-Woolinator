import logging

from discord.utils import escape_markdown, escape_mentions
from discord.ext import commands
from discord.app_commands import AppCommandError
import discord

from bot import Woolinator
from .utils.common import trim_str
from .utils.context import Context

log = logging.getLogger(__name__)


class ErrorHandler(commands.Cog):
    
    def __init__(self, bot: Woolinator) -> None:
        self.bot: Woolinator = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx: Context, error: commands.CommandError):

        if isinstance(error, commands.CommandError):

            if isinstance(error, commands.HybridCommandError):
                error: AppCommandError = error.original
                try: await ctx.reply('An error occured while executing the slash command', ephemeral=True)
                except discord.HTTPException: pass
                log.exception('There was a HybridCommandError', exc_info=error)
                return

            if isinstance(error, commands.CommandOnCooldown):
                if ctx.interaction is not None:
                    await ctx.reply(f'You are on cooldown... take a breather and try again in ~{round(error.retry_after)} seconds', ephemeral=True)
                return

            if isinstance(error, commands.UserInputError):
                
                if isinstance(error, commands.CommandNotFound):
                    pass

                if isinstance(error, commands.TooManyArguments):
                    await ctx.reply('You\'ve entered more arguments than required...', ephemeral=True)

                if isinstance(error, commands.MissingRequiredAttachment):
                    await ctx.reply('You\'re missing a required attachment', ephemeral=True)

                if isinstance(error, commands.MissingRequiredArgument):
                    param: commands.Parameter = error.param

                    # If the command was ran without any additional args, then send help menu for it
                    if len(ctx.args) <= 2:
                        return await ctx.send_help(ctx.command)

                    await ctx.reply(f'You\'re missing a required argument. Please check your input and try again.\n>>> Param missing: `{param.name}`',
                                    ephemeral=True)

                if isinstance(error, commands.BadUnionArgument):

                    if (len(error.converters) == 2) and (discord.Member in error.converters) and (discord.User in error.converters):
                        error = error.errors[0]

                    else:
                        await ctx.reply('An unexpected error occured with one of your arguments.')
                        log.exception('Bad union argument', exc_info=error)  # :shrugging:

                if isinstance(error, commands.BadLiteralArgument):
                    await ctx.reply('An unexpected error occured with one of your arguments.')
                    log.exception('Bad literal argument', exc_info=error)  # :shrugging:

                if isinstance(error, commands.ArgumentParsingError):
                    await ctx.reply(str(error), ephemeral=True)

                if isinstance(error, commands.BadArgument):
                    def cleanup_string(string: str) -> str:
                        string = trim_str(string, 35)
                        return escape_markdown(escape_mentions(string.strip('`').replace('\n', ' \\ ')))

                    if isinstance(error, commands.RangeError):
                        value_entered = cleanup_string(str(error.value))

                        await ctx.reply(f'One of your arguments is out of range:\n>>> value entered: `{value_entered}` ({len(str(error.value))} chars)\nmin-max allowed: `{error.minimum}-{error.maximum}`', ephemeral=True)

                
                    if isinstance(error, commands.MemberNotFound) or isinstance(error, commands.UserNotFound):
                        value_entered = cleanup_string(error.argument)
                        await ctx.reply(f'One of your arguments mentions a user/member that was not found:\n>>> value entered: `{value_entered}`\nformats allowed: `username`, `@mention`, `404234902574202880`', ephemeral=True)

                    if isinstance(error, commands.ChannelNotFound) or isinstance(error, commands.ThreadNotFound):
                        value_entered = cleanup_string(error.argument)
                        await ctx.reply(f'One of your arguments mentions a channel/thread that was not found:\n>>> value entered: `{value_entered}`\nformats allowed: `#channel`, `694963864390860803`', ephemeral=True)

                    if isinstance(error, commands.ChannelNotReadable):
                        await ctx.reply(f'I do not have permission to read the following channel: {error.argument.mention}', ephemeral=True)

                    if isinstance(error, commands.RoleNotFound):
                        value_entered = cleanup_string(error.argument)
                        await ctx.reply(f'One of your arguments mentions a role that was not found:\n>>> value entered: `{value_entered}`\nformats allowed: `@role`, `1307028351709614184`', ephemeral=True)

                    if isinstance(error, commands.BadBoolArgument):
                        value_entered = cleanup_string(error.argument)
                        await ctx.reply(f'One of your arguments expected a boolean (yes/no) but got something else:\n>>> value entered: `{value_entered}`\nformats allowed: `yes/no`, `1/0`, `true/false`', ephemeral=True)

                    if isinstance(error, commands.FlagError):
                        if isinstance(error, commands.BadFlagArgument):
                            await ctx.reply(f'You\'ve given a flag a bad value:\n>>> flag: `{error.flag.name}`\nvalue given: {cleanup_string(error.argument)}', ephemeral=True)

                        if isinstance(error, commands.MissingFlagArgument):
                            log.warning('Missing flag argument?', exc_info=error)

                        if isinstance(error, commands.TooManyFlags):
                            values_entered = [f'`{cleanup_string(value_entered)}`' for value_entered in error.values]
                            await ctx.reply(f'You\'ve given a flag too many values:\n>>> flag: `{error.flag.name}`\nvalues given: {",".join(values_entered)}', ephemeral=True)

                        if isinstance(error, commands.MissingRequiredFlag):
                            await ctx.reply(f'You\'ve forgotten to give a flag a value: `{error.flag.name}`', ephemeral=True)

                    return  # errors ignored: BadColourArgument, BadInviteArgument, EmojiNotFound,GuildStickerNotFound, ScheduledEventNotFound, PartialEmojiConversionFailure

                return

            if isinstance(error, commands.CheckFailure):
                if isinstance(error, commands.NoPrivateMessage):
                    await ctx.reply('This command can NOT be used in private messages', ephemeral=True)
                    return

                if isinstance(error, commands.PrivateMessageOnly):
                    await ctx.reply('This command can ONLY be used in private messages', ephemeral=True)
                    return

                if isinstance(error, commands.BotMissingAnyRole):
                    missing_roles_list = [f'{i}. `{role}`' for i, role in enumerate(error.missing_roles, start=1)]
                    await ctx.reply(f'I require any of these roles to be able to do that:\n{"\n".join(missing_roles_list)}', ephemeral=True)
                    return

                if isinstance(error, commands.BotMissingRole):
                    await ctx.reply(f'I require this role to be able to do that: `{error.missing_role}`', ephemeral=True)
                    return

                if isinstance(error, commands.BotMissingPermissions):
                    missing_perms_list = [f'`{perm}`' for perm in error.missing_permissions]
                    await ctx.reply(f'I am lacking the following permissions to do that:\n>>> {", ".join(missing_perms_list)}', ephemeral=True)
                    return

                if isinstance(error, commands.NotOwner):
                    await ctx.reply('You are not allowed to run this command', ephemeral=True)
                    return

                if isinstance(error, commands.MissingPermissions):
                    missing_perms_list = [f'`{perm}`' for perm in error.missing_permissions]
                    await ctx.reply(f'You are missing the following permissions to be able to run this command:\n>>> {", ".join(missing_perms_list)}', ephemeral=True)
                    return

                if isinstance(error, commands.MissingRole):
                    await ctx.reply(f'You require this role to be able to do that: `{error.missing_role}`', ephemeral=True)
                    return

                if isinstance(error, commands.NSFWChannelRequired):
                    await ctx.reply('This command can only be used in NSFW channels... naughty naughty', ephemeral=True)
                    return

                if isinstance(error, commands.MissingAnyRole):
                    missing_roles_list = [f'{i}. `{perm}`' for i, perm in enumerate(error.missing_roles, start=1)]
                    await ctx.reply(f'You require any of these roles to be able to do that:\n{"\n".join(missing_roles_list)}', ephemeral=True)
                    return

                else:
                    await ctx.reply('You don\'t have permission to use this command', ephemeral=True)
                    return

            if isinstance(error, commands.DisabledCommand):
                await ctx.reply('This command is currently disabled... mysterious', ephemeral=True)
                return

            if isinstance(error, commands.MaxConcurrencyReached):
                await ctx.reply(f'You can\'t run this command more than **{error.number}** times right now.', ephemeral=True)
                return

            if isinstance(error, commands.CommandInvokeError):
                # already using getattr() to get original error
                #error: BaseException = error.__cause__
                pass

            error = getattr(error, 'original', error)
            await ctx.reply('An unexpected error occurred... :c', ephemeral=True)
            log.exception('An unexpected CommandError occurred', exc_info=error)
            return

        if isinstance(error, commands.ExtensionError):
            error = getattr(error, 'original', error)
            log.exception('An error occurred with an extension', exc_info=error)
            return


async def setup(bot: Woolinator) -> None:
    await bot.add_cog(ErrorHandler(bot))
