from typing import Callable, TypeVar

from discord.ext import commands
from discord import app_commands

T = TypeVar('T')

async def check_guild_permissions(ctx, perms: dict[str, bool], *, check=all) -> bool:
    """ Guild permissions check predicate. """

    if await ctx.bot.is_owner(ctx.author):
        return True

    if ctx.guild is None:
        return False

    resolved = ctx.author.guild_permissions
    return check(getattr(resolved, name, None) == value for name, value in perms.items())

def hybrid_has_permissions(**perms: bool) -> Callable[[T], T]:
    """ Similar to `has_permissions`, but also applies to `app_commands.default_permissions`. """
    
    async def pred(ctx):
        return await check_guild_permissions(ctx, perms)

    def decorator(func: T) -> T:
        commands.check(pred)(func)
        app_commands.default_permissions(**perms)(func)
        return func

    return decorator