import io
import logging

from discord import app_commands, ui
from discord.ext import commands
import discord
import aiohttp
from PIL import Image

from bot import Woolinator
from .utils.views import handle_view_edit
from .utils.emojis import tick
from .utils.context import Context


log = logging.getLogger(__name__)


def make_attachment(file_data: tuple[bytes, str] | None) -> list[discord.File]:
    if file_data:
        return [discord.File(io.BytesIO(file_data[0]), file_data[1])]
    return []

async def get_image_buffer(url: str) -> Image.Image | None:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:

            if resp.status != 200:
                log.warning(f"Failed to fetch image data with the URL '{url}'...?")
                return None

            return Image.open(io.BytesIO(await resp.read()))

class GlobalGuildSwitchView(ui.View):

    def __init__(self,
        author_id: int,
        global_embed: discord.Embed | None,
        guild_embed: discord.Embed | None,
        global_file: tuple[bytes, str] | None = None,
        guild_file: tuple[bytes, str] | None = None,
        timeout: int | None = 180
    ):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.message = None

        self.global_embed = global_embed
        self.guild_embed = guild_embed

        self.global_file = global_file
        self.guild_file = guild_file

        self.children[0]: ui.Button
        self.children[1]: ui.Button

        if global_embed is None:
            self.set_button_state(1, False, True)
            self.set_button_state(0, False, False)
            self.stop()

        elif guild_embed is None:
            self.set_button_state(0, False, True)
            self.set_button_state(1, False, False)
            self.stop()
        
        else:
            if guild_embed:
                self.set_button_state(1, False, True)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You are not the owner of this message", ephemeral=True)
            return False
        return True

    def set_button_state(self, button_index: int, enabled: bool, selected: bool|None):
        button = self.children[button_index]
        button.disabled = not enabled
        button.style = discord.ButtonStyle.green if selected else discord.ButtonStyle.grey if selected is None else discord.ButtonStyle.red
        button.emoji = tick(selected)

    @ui.button(label="Global", style=discord.ButtonStyle.grey)
    async def display_global(self, interaction: discord.Interaction, button: ui.Button):

        if self.global_embed is None:
            await interaction.response.send_message("There is no global version", ephemeral=True)
            return

        self.set_button_state(1, True, None)
        self.set_button_state(0, False, True)
        
        attachments = make_attachment(self.global_file)
        await interaction.response.edit_message(embed=self.global_embed, attachments=attachments, view=self)

    @ui.button(label="Guild", style=discord.ButtonStyle.grey)
    async def display_guild(self, interaction: discord.Interaction, button: ui.Button):

        if self.guild_embed is None:
            await interaction.response.send_message("There is no guild version", ephemeral=True)
            return

        self.set_button_state(1, False, True)
        self.set_button_state(0, True, None)

        attachments = make_attachment(self.guild_file)
        await interaction.response.edit_message(embed=self.guild_embed, attachments=attachments, view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await handle_view_edit(self.message, view=self)


class Profile(commands.Cog, name="Profile", description="Do some funky things with peoples' profiles"):

    def __init__(self, bot: Woolinator) -> None:
        self.bot: Woolinator = bot

    @property
    def emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name="avatar",id=1337677146063372309)

    def create_asset_display_embeds(self, global_asset: discord.Asset|None, guild_asset: discord.Asset|None) -> tuple[discord.Embed, discord.Embed]:

        def format_size_link(url: str, size: int) -> str:
            return f"[**{size}**]("+url.replace('size=1024', f'size={size}').replace('size=512', f'size={size}')+')'

        sizes = [16, 32, 64, 128, 256, 512, 1024, 2048, 4096]

        def create_embed(asset: discord.Asset, colour: discord.Colour) -> discord.Embed:
            links = ", ".join([format_size_link(asset.url, s) for s in sizes])
            embed = discord.Embed(description=f"Sizes: {links}\n\n**Preview:**", colour=colour)
            embed.set_image(url=asset.url)
            return embed

        global_embed = create_embed(global_asset, discord.Colour.fuchsia()) if global_asset else None
        guild_embed = create_embed(guild_asset, discord.Colour.green()) if guild_asset else None
        return global_embed, guild_embed

    def prepare_embed(self, embed: discord.Embed, member: discord.abc.User, ctx: Context, label: str):
        embed.title = f"{member.name}'s {label}"
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)


    @commands.hybrid_command(name="banner", description="Get someone's banner")
    @app_commands.describe(member="The user/member whose banner you want to see")
    async def banner(self, ctx: Context, member: discord.Member|discord.User|None = commands.Author):
        user = await self.bot.fetch_user(member.id)  # get_user() does not return global banner

        guild_banner = getattr(member, "guild_banner", None) if ctx.guild else None
        global_banner = getattr(user, "banner", None)

        if (not guild_banner) and (not global_banner):
            await ctx.reply("that user does not even have a banner bro", ephemeral=True)
            return


        global_embed, guild_embed = self.create_asset_display_embeds(global_banner, guild_banner)
        if global_embed:
            self.prepare_embed(global_embed, member, ctx, "global banner")
        if guild_embed:
            self.prepare_embed(guild_embed, member, ctx, "guild banner")

        view = GlobalGuildSwitchView(ctx.author.id, global_embed, guild_embed)
        view.message = await ctx.reply(embed=guild_embed or global_embed, view=view)


    @commands.hybrid_command(name="avatar", aliases=["av"], description="Get someone's avatar")
    @app_commands.describe(member="The user/member whose avatar you want to see")
    async def avatar(self, ctx: Context, member: discord.Member|discord.User|None = commands.Author):
        guild_avatar = getattr(member, "guild_avatar", None) if ctx.guild else None
        global_avatar = getattr(member, "avatar", None)

        global_embed, guild_embed = self.create_asset_display_embeds(global_avatar, guild_avatar)
        if global_embed:
            self.prepare_embed(global_embed, member, ctx, "global avatar")
        if guild_embed:
            self.prepare_embed(guild_embed, member, ctx, "guild avatar")

        view = GlobalGuildSwitchView(ctx.author.id, global_embed, guild_embed)
        view.message = await ctx.reply(embed=guild_embed or global_embed, view=view)

    @commands.hybrid_command(name="pixelate", aliases=["pixel"], description="Pixelate someone's avatar")
    @app_commands.describe(dimension="The amount of pixels in the width & height of the new avatar", member="The user/member whose avatar you want to see")
    async def pixelate(self, ctx: Context, dimension: commands.Range[int, 1, 1024] = 8, member: discord.Member|discord.User|None = commands.Author):
        global_avatar_url = getattr(member, "avatar", member.display_avatar).url
        guild_avatar_url = getattr(member, "guild_avatar", None).url if ctx.guild else None

        def apply_filter(img: Image.Image, size: int) -> io.BytesIO:
            img = img.resize((size, size), Image.Resampling.NEAREST).resize(img.size, Image.Resampling.NEAREST)
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            return buffer

        async def process_avatar(label: str, url: str, colour: discord.Colour):
            img = await get_image_buffer(url)
            if not img:
                return None, None, None
            buffer = apply_filter(img, dimension)
            buffer.seek(0)
            filename = f"pixelated-{label}-avatar-{member.name}.png"
            embed = discord.Embed(title=f"{member.name}'s pixelated {label} avatar", description="**Preview:**", colour=colour)
            embed.set_image(url=f"attachment://{filename}")
            file = discord.File(buffer, filename=filename)
            return embed, file, buffer

        gu_embed, gu_file, gu_buffer = (await process_avatar("guild", guild_avatar_url, discord.Colour.green())) if guild_avatar_url else (None, None, None)
        gl_embed, gl_file, gl_buffer = await process_avatar("global", global_avatar_url, discord.Colour.fuchsia())

        view = GlobalGuildSwitchView(
            ctx.author.id,
            global_embed=gl_embed,
            guild_embed=gu_embed,
            global_file=(getattr(gl_buffer, "getvalue", None), f"pixelated-global-avatar-{member.name}.png") if gl_buffer else None,
            guild_file=(getattr(gu_buffer, "getvalue", None), f"pixelated-guild-avatar-{member.name}.png") if gu_buffer else None
        )

        view.message = await ctx.reply(embed=gu_embed or gl_embed, file=gu_file or gl_file, view=view)



async def setup(bot: Woolinator) -> None:
    await bot.add_cog(Profile(bot))
