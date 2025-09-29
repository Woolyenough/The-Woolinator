import os
import glob
import logging
import io
import importlib
import sys
import re
import textwrap
import subprocess
import copy
import traceback
from typing import Any

import discord
from discord.ext import commands
from discord.utils import escape_markdown as escape_md
import asyncio
from contextlib import redirect_stdout

from bot import Woolinator
from .utils.context import Context, Context
from .utils.emojis import tick


log = logging.getLogger(__name__)


class Wooly(commands.Cog, command_attrs=dict(hidden=True)):

    def __init__(self, bot: Woolinator) -> None:
        self.bot = bot
        self.sessions: set[int] = set()

    async def cog_check(self, ctx):
        if await self.bot.is_owner(ctx.author): return True
        raise commands.NotOwner()

    async def run_process(self, command: str) -> list[str]:
        """ Runs a shell command asynchronously and return standard output and error. """

        try:
            process = await asyncio.create_subprocess_shell(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            result = await process.communicate()
        except NotImplementedError:
            process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            result = await self.bot.loop.run_in_executor(None, process.communicate)
        return [output.decode() for output in result]

    @commands.command(name="sync", description="Sync the 'App Command Tree' with Discord")
    async def sync(self, ctx: Context) -> None:
        synced = await self.bot.tree.sync()
        await ctx.reply(f"Synced {len(synced)} slash command in {len(self.bot.guilds)} guilds.")

    @commands.command(name="sql", description="Execute SQL in the bot database")
    async def sql(self, ctx: Context, *, statement: str):
        async with self.bot.get_cursor() as cursor:
            code: int = await cursor.execute(statement)
            rows: tuple[tuple[Any]] = await cursor.fetchall()

        lines = '\n'.join([str(r) for r in rows])
        await ctx.reply(f"Return: {code}```sql\n{lines}```")

    def remove_backticks(self, content: str) -> str:
        """ Removes ```py\n ... ``` """

        if content.endswith('```'):
            if content.strip().startswith('```'):
                return '\n'.join(content.split('\n')[1:-1])
            if content.strip().startswith('\n```py'):
                return '\n'.join(content.split('\n')[2:-1])
        return content

    @commands.command(name="log", description="Upload woolinator.log")
    async def log(self, ctx: Context):
        file = "woolinator.log"
        await ctx.reply(f"`{file}`:", file=discord.File(fp=file, filename=file))

    @commands.command(name="eval", description="Evaluate some Python code")
    async def eval(self, ctx: Context, *, code: str):
        env = {
            "self": self,
            "bot": self.bot,
            "ctx": ctx
        }

        env.update(globals())

        code = self.remove_backticks(code)
        code = f"async def _eval_func():\n{textwrap.indent(code, '    ')}"

        try:
            exec(code, env)
        except Exception as e:
            return await ctx.send(f"```py\n{e.__class__.__name__}: {e}\n```")

        func = env['_eval_func']
        stdout = io.StringIO()

        try:
            with redirect_stdout(stdout):
                result = await func()
        except Exception:
            output = stdout.getvalue()
            error = traceback.format_exc()
            return await ctx.send(f"```py\n{output}{error}\n```")

        output = stdout.getvalue()
        try:
            await ctx.message.add_reaction('✅')
        except discord.HTTPException:
            pass

        if result is None:
            if output:
                await ctx.send(f"```py\n{output}\n```")
        else:
            await ctx.send(f"```py\n{output}{result}\n```")

    @commands.group(name="git", description="Run git commands", invoke_without_command=True)
    async def git(self, ctx: Context):
        args = ctx.message.content.replace(f"{ctx.prefix}git", '', 1).strip()

        if not args:
            return await ctx.reply("Please specify a git subcommand (e.g. `git pull`).")

        stdout, stderr = await self.run_process(f"git {args}")
        stdout = escape_md(stdout) if stdout else ''
        stderr = escape_md(stderr) if stderr else ''

        project_folder = __file__.split('/')[-3]
        branch = (await self.run_process("git branch"))[0].strip('\n* ')
        command_display = f"-# **{project_folder} ({branch})#** git {escape_md(args)}"

        if not (stdout or stderr):
            embed = discord.Embed(description="Successfully ran, but empty output.", colour=discord.Colour.orange())
        else:
            embed = discord.Embed(description=f"{stderr}\n\n{stdout}", colour=0xCCCCCC)

        await ctx.reply(command_display, embed=embed)

    @git.command(name="sync", aliases=["s"], description="git pull and then reload modified modules")
    async def git_sync(self, ctx: Context):
        stdout, stderr = await self.run_process("git pull")

        if stdout.startswith("Already up to date."):
            await ctx.send(stdout)
            return

        git_pull_output = f"```ansi\n{stderr}```\n\n```ansi\n{stdout}```"
        modules = self.find_modules_from_git(stdout)
    
        if len(modules) == 0:
            await ctx.reply(f"Latest commits were pulled, but no modules to reload:{git_pull_output}")
            return

        statuses = await self.reload_modules(modules)
        modules = '\n'.join(f'{i}. `{module}`: {status}' for i, (status, module) in enumerate(statuses, start=1))
        await ctx.reply(git_pull_output + "\n\n**Updated modules:**\n" + modules)

    async def reload_or_load_extension(self, extension: str) -> bool:
        """ Reload the parsed extension - or load, if not already loaded. """

        try:
            await self.bot.reload_extension(extension)
            return False
        except commands.ExtensionNotLoaded:
            await self.bot.load_extension(extension)
            return True

    def find_modules_from_git(self, output: str) -> list[tuple[int, str]]:
        """ Return a list of modules & submodules that were modified. """

        git_pull_regex = re.compile(r"\s*(?P<filename>.+?)\s*\|\s*[0-9]+\s*[+-]+")
        files = git_pull_regex.findall(output)
        ret: list[tuple[int, str]] = []
        for file in files:
            root, ext = os.path.splitext(file)
            if ext != ".py":
                continue

            if root.startswith("cogs/"):
                ret.append((root.count('/') - 1, root.replace('/', '.')))

        # Submodules should be reloaded first
        ret.sort(reverse=True)
        return ret

    def get_all_modules(self) -> list[tuple[int, str]]:
        """ Get all the available project modules. """

        ret: list[tuple[int, str]] = []

        prev_active_modules = [mod for mod in sys.modules.keys() if mod.startswith("cog") and sys.modules[mod].__file__]

        project_path = '.'
        modules = glob.glob(os.path.join(project_path, "**", "*.py"), recursive=True)
        modules = [os.path.relpath(m, project_path) for m in modules]  # Get relative paths

        for module in modules:
            module = module[:-3] if module.endswith(".py") else module  # remove .py ending, if exists
            if module.startswith("cogs/"):
                ret.append((module.count('/') - 1, module.replace('/', '.')))

        # Add any modules that have been removed, so that they can be unloaded
        for prev_mod in prev_active_modules:
            if prev_mod not in [val for n, val in ret]:
                ret.append((prev_mod.count('.') - 1, prev_mod))

        # Submodules should be reloaded first
        ret.sort(reverse=True)
        return ret

    async def reload_modules(self, modules: list[tuple[int, str]] = []) -> list[tuple[str, str]]:
        """ Reload all or specified modules. 
        
        Args:
            modules (list of tuples): A list of tuples where each tuple contains:
                - An integer indicating the file depth (1 for submodule aka in util package, 0 for module aka cog)
                - A string representing the module name (e.g., 'cogs.some_cog' or 'utils.some_util')
                
        Returns:
            list of tuples: A list of tuples with the status of each module reload, where:
                - The first string is an emoji representing reload status
                - The second string is the name of the module
        """

        # Retrieve all modules if none are specified
        if not modules:
            modules = self.get_all_modules()

        # Helper function to strip 'cogs.' prefix
        def s(module: str) -> str:
            return module[5:] if module.startswith("cogs.") else module

        statuses = []
        for is_submodule, module in modules:

            # Submodules are in 'cogs.utils'; modules are in 'cogs'
            if is_submodule:
                try:
                    actual_module = sys.modules[module]
                except KeyError:
                    # If the module is not found in sys.modules, it hasn't been loaded yet
                    statuses.append(("<a:sparkles:1324914202497777694> : :jigsaw:", s(module)))
                else:
                    try:
                        importlib.reload(actual_module)
                    except ModuleNotFoundError:
                        # If the module was not found, clean up sys.modules
                        del sys.modules[module]
                        statuses.append((":wastebasket: : :jigsaw:", s(module)))
                    except Exception:
                        statuses.append((tick(False) + " : :jigsaw:", s(module)))
                        log.exception("Failed to reload submodule %s", module)
                    else:
                        # Successful reload
                        statuses.append((tick(True) + " : :jigsaw:", s(module)))

            # Handle cogs
            else:
                try:
                    is_new = await self.reload_or_load_extension(module)
                except commands.ExtensionNotFound:
                    # If not found, unload it
                    statuses.append((":wastebasket: : :gear:", s(module)))
                    await self.bot.unload_extension(module)
                except commands.ExtensionError:
                    statuses.append((tick(False) + " : :gear:", s(module)))
                    log.exception("Failed to reload extension %s", module)
                else:
                    if is_new:
                        statuses.append(("<a:sparkles:1324914202497777694> : :gear:", s(module)))
                    else:
                        statuses.append((tick(True) + " : :gear:", s(module)))
        return statuses

    @commands.command(name="reload", description="reload any local changes")
    async def reload(self, ctx: Context):
        statuses = await self.reload_modules()
        await ctx.reply("**Module Statuses:**\n" +
                                    '\n'.join(f'{status}`{module}`' for status, module in statuses))

    @commands.command(name="sudo", description="Run a command as another user")
    @commands.guild_only()
    async def sudo(self, ctx: Context, channel: discord.TextChannel|None, user: discord.Member|discord.User, *, command: str,):
        msg = copy.copy(ctx.message)
        new_channel = channel or ctx.channel
        msg.channel = new_channel
        msg.author = user
        msg.content = ctx.prefix + command
        new_ctx = await self.bot.get_context(msg, cls=type(ctx))
        await self.bot.invoke(new_ctx)


async def setup(bot: Woolinator) -> None:
    await bot.add_cog(Wooly(bot))
