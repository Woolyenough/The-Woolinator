from datetime import datetime
import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from .utils.views import YesOrNo
from .utils.common import trim_str
from .utils.context import Context
from bot import Woolinator


log = logging.getLogger(__name__)


class Tags(commands.Cog, name='Tags', description='Create trigger-able messages'):
    
    def __init__(self, bot: Woolinator) -> None:
        self.bot: Woolinator = bot
        self.db_columns_order = ['id', 'user_id', 'guild_id', 'created', 'name', 'content']

    async def cog_check(self, ctx: Context) -> bool:
        if ctx.guild is None: raise commands.NoPrivateMessage()
        return True

    @property
    def emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name='tags', id=1337677206175879168)

    def prev_tag(self, tag: str) -> str:
        return tag.replace('*', '\\*').replace('`', '\\`').replace('_', '\\_')

    def index_tag(self, tag: list[str]) -> dict[str, str] | None:
        if tag is None:
            return None
        
        if len(tag) != len(self.db_columns_order):
            log.warning(f'Tags length ({len(tag)}) does not match table columns length ({len(self.db_columns_order)})')

        return {
            self.db_columns_order[i]: tag[i] for i in range(len(self.db_columns_order))
        }

    def index_tags(self, tags: list[list[str]]) -> list[dict[str, str]]:
        return [self.index_tag(tag) for tag in tags]

    async def delete_tag(self, id: int):
        async with self.bot.get_cursor() as cursor:
            res = await cursor.execute('DELETE FROM tags WHERE id = %s', (id,))
        return res

    async def get_all_tags_starts_with(self, starts_with: str, user: discord.Member|discord.User|None = None, guild: discord.Guild|None = None, limit: int|None = None) -> list[dict[str, str]]:
        async with self.bot.get_cursor() as cursor:

            query = 'SELECT * FROM tags WHERE LOWER(name) LIKE %s'
            params = (f'{starts_with.lower()}%',)

            if user is not None:
                query += ' AND user_id = %s'
                params += (user.id,)

            if guild is not None:
                query += ' AND guild_id = %s'
                params += (guild.id,)

            if limit is not None:
                query += ' LIMIT %s'
                params += (limit,)

            await cursor.execute(query, params)
            tags = await cursor.fetchall()
        return self.index_tags(tags)

    async def get_user_tags(self, user: discord.Member|discord.User, guild: discord.Guild|None, limit: int|None = None) -> list[dict[str, str]]:
        async with self.bot.get_cursor() as cursor:

            if guild is None:
                query = 'SELECT * FROM tags WHERE user_id = %s'
                params = (user.id,)
            else:
                query = 'SELECT * FROM tags WHERE user_id = %s AND guild_id = %s'
                params = (user.id, guild.id)
                
            if limit is not None:
                query += ' LIMIT %s'
                params += (limit,)
                
            await cursor.execute(query, params)
            tags = await cursor.fetchall()

        return self.index_tags(tags)

    async def get_guild_tags(self, guild: discord.Guild) -> list[dict[str, str]]:

        async with self.bot.get_cursor() as cursor:
            await cursor.execute('SELECT * FROM tags WHERE guild_id = %s', (guild.id))
            tags = await cursor.fetchall()

        return self.index_tags(tags)
    
    async def get_tag(self, name: str, guild: discord.Guild) -> dict[str, str]:
        async with self.bot.get_cursor() as cursor:
            await cursor.execute('SELECT * FROM tags WHERE LOWER(name) = LOWER(%s) AND guild_id = %s', (name, guild.id))
            tag = await cursor.fetchone()
        return self.index_tag(tag)
    
    async def insert_tag(self, tag: dict[str, str]) -> None:
        async with self.bot.get_cursor() as cursor:
            await cursor.execute('INSERT INTO tags (user_id, guild_id, created, name, content) VALUES (%s, %s, %s, %s, %s)', (tag['user_id'], tag['guild_id'], tag['created'], tag['name'], tag['content']))

    def is_valid_tag(self, name: str) -> tuple[bool, str]:
        if len(name) > 32:
            return (False, 'Tag name cannot be longer than 32 characters.')

        first_word, _, _ = name.partition(' ')
        root: commands.GroupMixin = self.bot.get_command('tag')
        if first_word in root.all_commands:
            return (False, 'This tag name can\'t be used.')

        return (True, '')


    async def owned_tag_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        tags = await self.get_all_tags_starts_with(current, user=interaction.user, guild=interaction.guild, limit=15)

        if len(tags) == 0:
            return []
        
        options = [app_commands.Choice(name=tag['name'], value=tag['name']) for tag in tags]
        return options

    async def guild_tag_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        tags = await self.get_all_tags_starts_with(current, guild=interaction.guild, limit=15)

        if len(tags) == 0:
            return []
        
        options = [app_commands.Choice(name=tag['name'], value=tag['name']) for tag in tags]
        return options

    @commands.hybrid_group(name='tag', description='Get a tag\'s contents', fallback='get')
    @app_commands.describe(name='The name of the tag')
    @app_commands.autocomplete(name=guild_tag_autocomplete)
    async def tag(self, ctx: Context, *, name: commands.Range[str, 1, 32]):
        name = ''.join(name.splitlines())
        name = await commands.clean_content(fix_channel_mentions=True, use_nicknames=False).convert(ctx, name)

        tag = await self.get_tag(name, ctx.guild)

        if tag is None:
            if ctx.interaction is None:
                if name.startswith('get'):
                    await ctx.reply('Tag does not exist! (BTW, you do not need to use the `get` argument when not using a slash command)', ephemeral=True)
                    return
            await ctx.reply('Could not find a tag with that name!', ephemeral=True)
            return
        
        footer = f'-# *Message triggered by **`@{ctx.author.name}`***'

        ref = ctx.replied_message
        if ref:
            await ctx.message.delete()

        try:
            await ctx.send(f'{tag['content']}\n{footer}', reference=ref)
        except (discord.HTTPException):
            pass  # if the user deletes the referenced message before this message is sent

    @tag.command(description='Create a tag w/ a modal')
    async def modal(self, ctx: Context):
        if ctx.interaction is None:
            await ctx.reply('This command requires to be ran as a slash command.', ephemeral=True)
            return
        await ctx.reply('This feature is not implemented yet :grimacing:', ephemeral=True)

    @tag.command(description='Delete all your tags')
    async def clear(self, ctx: Context):
        tags = await self.get_user_tags(ctx.author, ctx.guild)

        if len(tags) == 0:
            await ctx.reply('You do not own any tags!', ephemeral=True)
            return
        
        view = YesOrNo(ctx.author)
        message = await ctx.reply(f'Are you sure you want to delete ALL your {len(tags)} tags? They\'ll be gone forever!', view=view)
        view.message = message
        await view.wait()

        if not view.value:
            return

        async with self.bot.get_cursor() as cursor:
            await cursor.execute('DELETE FROM tags WHERE user_id = %s AND guild_id = %s', (ctx.author.id, ctx.guild.id))
        
        await message.edit(content=f'Successfully deleted the {len(tags)} tags.', embed=None, view=None)

    @tag.command(description='Create a tag')
    @app_commands.describe(name='The name of the tag', content='The message in the tag')
    async def create(self, ctx: Context, name: commands.Range[str, 1, 32], *, content: commands.Range[str, 1, 1900]):
        name = ''.join(name.splitlines())
        name = await commands.clean_content(fix_channel_mentions=True, use_nicknames=False).convert(ctx, name)
        content = await commands.clean_content(use_nicknames=False).convert(ctx, content)

        valid, reason = self.is_valid_tag(name)
        if not valid:
            await ctx.reply(reason, ephemeral=True)
            return
        
        tags = await self.get_user_tags(ctx.author, ctx.guild)

        if len(tags) > 25:
            await ctx.reply('You can only own 25 tags at a time (per guild)!', ephemeral=True)
            return

        tag = await self.get_tag(name, ctx.guild)

        if tag is not None:

            if tag['user_id'] == ctx.author.id:
                await ctx.reply(f"You already own the tag '{self.prev_tag(tag['name'])}'! To modify it, use '/tag edit {self.prev_tag(tag['name'])}'", ephemeral=True)
                return
            else:
                tag_owner = await self.bot.get_or_fetch_user(tag['user_id'])
                await ctx.reply(f"Tag with name '{self.prev_tag(tag['name'])}' already exists, and is owned by `@{tag_owner.name}`! Try another name.", ephemeral=True)
                return

        await self.insert_tag({'user_id': ctx.author.id, 'guild_id': ctx.guild.id, 'created': datetime.now(), 'name': name, 'content': content})

        await ctx.reply(f"You are now the proud owner of the tag '{self.prev_tag(name)}'!")

    @tag.command(description='Remove a tag that belongs to you', aliases=['delete'])
    @app_commands.describe(name='The name of the tag')
    @app_commands.autocomplete(name=owned_tag_autocomplete)
    async def remove(self, ctx: Context, *, name: commands.Range[str, 1, 32]):
        name = ''.join(name.splitlines())
        name = await commands.clean_content(fix_channel_mentions=True, use_nicknames=False).convert(ctx, name)
        tag = await self.get_tag(name, ctx.guild)

        if tag is None:
            await ctx.reply('Tag does not exist!', ephemeral=True)
            return
        
        created_ts = round(tag['created'].timestamp())

        view = YesOrNo(ctx.author)
        embed = discord.Embed(description=f'> Created on <t:{created_ts}:d> at <t:{created_ts}:T>\n\n**Preview:**\n{trim_str(tag['content'], 80)}', colour=discord.Colour.red())
        embed.set_author(name=tag['name'], icon_url=ctx.author.display_avatar.url)
        message = await ctx.reply('Are you sure you want to delete this tag?', embed=embed, view=view)
        view.message = message
        await view.wait()

        if not view.value:
            return

        await self.delete_tag(tag['id'])
        await message.edit(content=f"Successfully deleted the tag '{self.prev_tag(tag['name'])}'.", embed=None, view=None)

    @tag.command(description='List tags owned by a specific user')
    @app_commands.describe(user='The user to list tags for')
    async def list(self, ctx: Context, user: discord.Member|discord.User = commands.Author):
        tags = await self.get_user_tags(user, ctx.guild)

        if len(tags) == 0:
            await ctx.reply('You don\'t own any tags!', ephemeral=True)
            return

        embed = discord.Embed(description='\n'.join(f'{i}. {self.prev_tag(tag['name'])}' for i, tag in enumerate(tags, start=1)), colour=discord.Colour.random())
        embed.set_author(name=f'{user.name}\'s tags', icon_url=user.display_avatar.url)
        await ctx.reply(embed=embed)

    @tag.command(description='Rename a tag')
    @app_commands.describe(name='The name of the tag', new_name='The new name of the tag')
    @app_commands.rename(new_name='new-name')
    @app_commands.autocomplete(name=owned_tag_autocomplete)
    async def rename(self, ctx: Context, name: commands.Range[str, 1, 32], new_name: commands.Range[str, 1, 32]):
        name = ''.join(name.splitlines())
        name = await commands.clean_content(fix_channel_mentions=True, use_nicknames=False).convert(ctx, name)
        new_name = ''.join(new_name.splitlines())
        new_name = await commands.clean_content(fix_channel_mentions=True, use_nicknames=False).convert(ctx, new_name)
        
        valid, reason = self.is_valid_tag(new_name)
        if not valid:
            await ctx.reply(reason, ephemeral=True)
            return

        old_tag = await self.get_tag(name, ctx.guild)

        if old_tag is None:
            await ctx.reply('That tag does not exist!', ephemeral=True)
            return

        if (old_tag['user_id'] != ctx.author.id) and (not ctx.author.guild_permissions.manage_guild):
            await ctx.reply('You do not own this tag or have permission to rename it!', ephemeral=True)
            return
        
        tag = await self.get_tag(new_name, ctx.guild)

        if tag is not None:
            await ctx.reply('That name is already taken!', ephemeral=True)
            return
        
        async with self.bot.get_cursor() as cursor:
            await cursor.execute('UPDATE tags SET name = %s WHERE LOWER(name) = LOWER(%s) AND guild_id = %s', (new_name, name, ctx.guild.id))

        await ctx.reply(f"Successfully renamed tag '{self.prev_tag(old_tag['name'])}' to '{self.prev_tag(new_name)}'!")

    @tag.command(description='Get information about a specific tag')
    @app_commands.describe(name='The name of the tag')
    @app_commands.autocomplete(name=guild_tag_autocomplete)
    async def info(self, ctx: Context, *, name: commands.Range[str, 1, 32]):
        name = ''.join(name.splitlines())
        name = await commands.clean_content(fix_channel_mentions=True, use_nicknames=False).convert(ctx, name)

        tag = await self.get_tag(name, ctx.guild)

        if tag is None:
            await ctx.reply('A tag with that name does not exist!', ephemeral=True)
            return
        
        tag_owner = await self.bot.get_or_fetch_user(tag['user_id'])
        tag_created_ts = round(tag['created'].timestamp())

        embed = discord.Embed(title=f'Name: {tag['name']}', description=f'**Created:** at <t:{tag_created_ts}:T> on <t:{tag_created_ts}:d>\n\n**Preview:**\n{trim_str(tag['content'], 80)}', colour=discord.Colour.random())
        embed.set_author(name=f'Owned by @{tag_owner}', icon_url=tag_owner.display_avatar.url)
        await ctx.reply(embed=embed)

    @tag.command(description='Search for a tag', hidden=True)
    @app_commands.describe(query='The query to search for')
    async def search(self, ctx: Context, *, query: commands.Range[str, 3, 32]):
        query = ''.join(query.splitlines())
        query = await commands.clean_content(fix_channel_mentions=True, use_nicknames=False).convert(ctx, query)

        if not await self.bot.is_owner(ctx.author):
            await ctx.reply('This feature is not implemented yet :grimacing:', ephemeral=True)
            return

        async with self.bot.get_cursor() as cursor:
            await cursor.execute('SELECT user_id, name FROM tags WHERE guild_id = %s AND MATCH(name) AGAINST (%s IN NATURAL LANGUAGE MODE) ORDER BY MATCH(name) AGAINST (%s IN NATURAL LANGUAGE MODE) DESC LIMIT 20', (ctx.guild.id, query, query))
            tags = await cursor.fetchall()

        if len(tags) == 0:
            await ctx.reply('No tags found!', ephemeral=True)
            return

        await ctx.reply(f"Tags containing '{query}': {', '.join([tag[1] for tag in tags])}")

    @tag.command(description='Modify the content of a tag', aliases=['edit'])
    @app_commands.describe(name='The name of the tag', new_content='The new content of the tag')
    @app_commands.rename(new_content='new-content')
    @app_commands.autocomplete(name=owned_tag_autocomplete)
    async def modify(self, ctx: Context, name: commands.Range[str, 1, 32], *, new_content: commands.Range[str, 1, 1900]):
        name = ''.join(name.splitlines())
        name = await commands.clean_content(fix_channel_mentions=True, use_nicknames=False).convert(ctx, name)
        new_content = await commands.clean_content(use_nicknames=False).convert(ctx, new_content)

        tag = await self.get_tag(name, ctx.guild)
        if tag is None:
            await ctx.reply('You do not own a tag with this name!', ephemeral=True)
            return
        
        async with self.bot.get_cursor() as cursor:
            await cursor.execute('UPDATE tags SET content = %s WHERE user_id = %s AND LOWER(name) = LOWER(%s) AND guild_id = %s', (new_content, ctx.author.id, name, ctx.guild.id))

        await ctx.reply('Successfully updated tag content.')

    @tag.command(description='Claim a tag whose owner has left the server')
    @app_commands.describe(name='The name of the tag')
    @app_commands.autocomplete(name=guild_tag_autocomplete)
    async def claim(self, ctx: Context, *, name: commands.Range[str, 1, 32]):
        name = ''.join(name.splitlines())
        name = await commands.clean_content(fix_channel_mentions=True, use_nicknames=False).convert(ctx, name)
        
        tag = await self.get_tag(name, ctx.guild)

        if tag is None:
            await ctx.reply('No tag by that name exists - you can create it yourself!', ephemeral=True)
            return
        
        member = ctx.guild.get_member(tag['user_id'])
        if member is None:
            try:
                member = await ctx.guild.fetch_member(tag['user_id'])
            except discord.HTTPException:
                await ctx.reply('An error occurred while checking if the owner is still in the server... please try again.', ephemeral=True)

        if member is not None:
            await ctx.reply('The owner of this tag is still in the server - you cannot claim it.', ephemeral=True)
            return
        
        async with self.bot.get_cursor() as cursor:
            await cursor.execute('UPDATE tags SET user_id = %s WHERE LOWER(name) = LOWER(%s) AND guild_id = %s', (ctx.author.id, name, ctx.guild.id))

        await ctx.reply(f"You are now the proud owner of the tag '{self.prev_tag(tag['name'])}'!")

    @tag.command(description='Transfer ownership of a tag')
    @app_commands.describe(name='The name of the tag', new_owner='The new owner of the tag')
    @app_commands.rename(new_owner='new-owner')
    @app_commands.autocomplete(name=owned_tag_autocomplete)
    async def transfer(self, ctx: Context, name: commands.Range[str, 1, 32], new_owner: discord.Member|discord.User):
        name = ''.join(name.splitlines())
        name = await commands.clean_content(fix_channel_mentions=True, use_nicknames=False).convert(ctx, name)

        if new_owner.bot:
            await ctx.reply('You cannot transfer a tag to a bot!', ephemeral=True)
            return

        tags = await self.get_user_tags(new_owner, ctx.guild)

        if len(tags) > 25:
            await ctx.reply('This person has reached the max of 25 tags!', ephemeral=True)
            return

        tag = await self.get_tag(name, ctx.guild)

        if tag is None:
            await ctx.reply('A tag with that name does not exist!', ephemeral=True)
            return

        if (tag['user_id'] != ctx.author.id) and (not ctx.author.guild_permissions.manage_guild):
            await ctx.reply('You do not own this tag or have permission to transfer it!', ephemeral=True)
            return

        if new_owner.id == tag['user_id']:
            await ctx.reply('That user already owns this tag...', ephemeral=True)
            return

        old_owner = await self.bot.get_or_fetch_user(tag['user_id'])

        async with self.bot.get_cursor() as cursor:
            await cursor.execute('UPDATE tags SET user_id = %s WHERE LOWER(name) = LOWER(%s) AND guild_id = %s', (new_owner.id, name, ctx.guild.id))

        await ctx.reply(f'Tag ownership transferred from `@{old_owner.name}` to `@{new_owner.name}`')


async def setup(bot: Woolinator) -> None:
    await bot.add_cog(Tags(bot))
