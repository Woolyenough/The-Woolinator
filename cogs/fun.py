import logging
from datetime import datetime
import io
import re
import urllib.parse

import discord
from discord import app_commands
from discord.utils import escape_markdown, escape_mentions
from discord.ext import commands

import cogs.utils.pagination as paginator
from bot import Woolinator
from .utils.context import Context


log = logging.getLogger(__name__)


class Fun(commands.Cog, name='Fun', description='Welcome to the house of fun'):
    
    def __init__(self, bot: Woolinator) -> None:
        self.bot: Woolinator = bot

    @property
    def emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name='fun', id=1337677161351352350)

    @commands.hybrid_command(name='urban', aliases=['ud'], description='Search something on the Urban Dictionary')
    @app_commands.describe(search='The term you want to search for')
    async def urban(self, ctx: Context, *, search: commands.Range[str, 1, 50]):

        def link_terms(text: str) -> str:
            def replacer(match):
                term = match.group(1)
                encoded_term = urllib.parse.quote(term)
                return f'[{term}](<https://www.urbandictionary.com/define.php?term={encoded_term}>)'

            # Match anything inside square brackets, non-greedy
            return re.sub(r'\[([^\[\]]+?)\]', replacer, text)

        async with self.bot.session.get(f'https://api.urbandictionary.com/v0/define?term={search}') as resp:
            if resp.status != 200:
                return await ctx.reply('Failed to fetch definition - API may be down :pensive:', ephemeral=True)
            data = await resp.json()

        if not data['list']:
            return await ctx.reply('No results found for that search term.')

        embeds_to_paginate = []
        for entry in data['list']:

            definition = link_terms(entry['definition'])
            example = link_terms(escape_markdown(entry['example']))

            embed = discord.Embed(
                title=f'**{entry['word']}**',
                description=f'{definition}\n\n**Example**\n*{example}*',
                colour=discord.Colour.dark_orange(),
                url=entry['permalink']
            )

            def parse_written_on(timestamp: str) -> datetime:
                # Try parsing with microseconds first
                try:
                    return datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S.%fZ')
                except ValueError:
                    # Otherwise, exclude it
                    return datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%SZ')

            embed.set_footer(text=f'Written on: {parse_written_on(entry['written_on']).strftime('%d/%m/%Y at %H:%M:%S (UTC)')}  ▪  👍 {entry['thumbs_up']} - 👎 {entry['thumbs_down']}')
            embed.set_author(name=f'Posted by {entry['author']}')
            embeds_to_paginate.append(embed)

        view = paginator.PaginationEmbedsView(embeds_to_paginate, author_id=ctx.author.id)
        message = await ctx.reply(embed=embeds_to_paginate[0], view=view, ephemeral=False)
        view.message = message

    @commands.hybrid_command(name='insult', description='Insult someone')
    @app_commands.describe(member='The member you want to insult')
    async def insult(self, ctx: Context, member: discord.Member):
        async with self.bot.session.get(f'https://insult.mattbas.org/api/insult?who={member.name}') as resp:
            if resp.status != 200:
                return await ctx.reply('Failed to fetch insult - API may be down :pensive:', ephemeral=True)
            data = await resp.text()

        await ctx.reply(escape_markdown(escape_mentions(data)), ephemeral=False)

    @commands.hybrid_command(name='cat', description='Get a random cat')
    async def cat(self, ctx: Context):
        async with self.bot.session.get('https://api.thecatapi.com/v1/images/search') as resp:
            if resp.status != 200:
                return await ctx.reply('No cat found - API may be down :pensive:', ephemeral=True)
            js = await resp.json()
            await ctx.reply(embed=discord.Embed(description='**A cat :cat:**', colour=discord.Colour.random()).set_image(url=js[0]['url']))

    @commands.hybrid_command(name='dog', description='Get a random dog')
    async def dog(self, ctx: Context):
        
        async with self.bot.session.get('https://random.dog/woof') as resp:
            if resp.status != 200:
                return await ctx.send('No dog found - API may be down :pensive:', ephemeral=True)

            filename = await resp.text()
            url = f'https://random.dog/{filename}'
            filesize = ctx.guild.filesize_limit if ctx.guild else 10 * 1024 * 1024 # 10MiB
            
            if filename.endswith(('.mp4', '.webm')):
                await ctx.typing()

                async with self.bot.session.get(url) as other:
                    if other.status != 200:
                        return await ctx.reply('No dog found - API may be down :pensive:', ephemeral=True)

                    if int(other.headers['Content-Length']) >= filesize:
                        return await ctx.reply(f'Video was too large for Discord...\n> See it [**here**]({url}) instead')

                    fp = io.BytesIO(await other.read())
                    await ctx.send(file=discord.File(fp, filename=filename))

            else:
                await ctx.reply(embed=discord.Embed(description='**A dog :dog:**', colour=discord.Colour.random()).set_image(url=url))


async def setup(bot: Woolinator) -> None:
    await bot.add_cog(Fun(bot))
