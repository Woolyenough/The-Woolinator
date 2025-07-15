import logging

from discord.ext import commands
import discord

from bot import Woolinator


log = logging.getLogger(__name__)


class Utilities(commands.Cog):
    
    def __init__(self, bot: Woolinator) -> None:
        self.bot: Woolinator = bot

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        async with self.bot.get_cursor() as cursor:
            await cursor.execute('DELETE FROM channels WHERE channel_id = %s', (channel.id,))
        

async def setup(bot: Woolinator) -> None:
    await bot.add_cog(Utilities(bot))
