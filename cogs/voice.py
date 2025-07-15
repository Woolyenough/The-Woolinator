import logging
import os
import io
import asyncio

from discord.ext import commands
from discord import app_commands
from discord.app_commands import Choice
from discord.utils import escape_markdown as esc_md
from discord.utils import escape_mentions as esc_me

import discord
from gtts import gTTS
from gtts.tts import gTTSError

from .utils.context import Context
from bot import Woolinator


log = logging.getLogger(__name__)


class Voice(commands.Cog, name='Voice', description='Voice call-related features'):

    def __init__(self, bot: Woolinator) -> None:
        self.bot: Woolinator = bot
        self.used_channel: dict[int, discord.abc.MessageableChannel] = {}
        self.queue = []

    async def cog_check(self, ctx: Context):
        if ctx.guild is None: raise commands.NoPrivateMessage()
        return True

    @property
    def emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name='voice', id=1337677215848206387)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        channel: discord.abc.Messageable|None = self.used_channel.get(member.guild.id)

        async def send_msg(ch: discord.abc.Messageable|None, content: str) -> None:
            if ch is not None:
                try: await ch.send(content)
                except (discord.HTTPException, discord.NotFound, discord.Forbidden): pass

        # Member still in channel
        if before.channel and after.channel:
            pass

        # Member joined channel
        if not before.channel and after.channel:
            pass

        # Member left channel
        if before.channel and not after.channel:

            vc = member.guild.voice_client
            if vc:
                cur_vc_members = [m for m in before.channel.members if not m.bot]
                if len(cur_vc_members) == 0:
                    await vc.disconnect(force=True)
                    vc.cleanup()
                    await send_msg(channel, 'I left the vc out of sadness because I was the only member left in it')

    async def join_vc(self, ctx: Context) -> discord.VoiceProtocol | None:
        """ Join the VC from the context, returning `None` if unable to. """
        
        voice_state = ctx.message.author.voice

        if voice_state is None:
            await ctx.reply('You\'re not in a voice channel smh', ephemeral=True)
            return None
    
        vc = ctx.guild.voice_client
        if vc:
            if (vc.channel != voice_state.channel) and vc.is_playing():
                await ctx.reply('I\'m already playing audio in another voice channel', ephemeral=True)
                return None

            elif vc.is_playing():
                await ctx.reply('I\'m already playing audio', ephemeral=True)
                return None

            elif vc.channel != voice_state.channel:
                await vc.disconnect(force=True)
                vc.cleanup()
                vc = await voice_state.channel.connect()

        if not vc:
            vc = await voice_state.channel.connect()

        self.used_channel[ctx.guild.id] = ctx.channel
        return vc

    @commands.hybrid_command(name='tts', description='Have a say in the voice chat without speaking')
    @app_commands.describe(message='The message you want to convert to speech')
    async def tts(self, ctx: Context, *, message: commands.Range[str, 1, 200]):
        vc = await self.join_vc(ctx)
        if vc is None:
            return

        audio_bytes = io.BytesIO()
        try:
            tts = gTTS(f'{ctx.author.name} says {message}', timeout=5.0)
            await asyncio.to_thread(tts.write_to_fp, audio_bytes)
            audio_bytes.seek(0)
        except gTTSError as e:
            log.warning('Error when using gTTS', exc_info=e)
            return await ctx.reply('Sorry, there was an error with the speech API... :confused:', ephemeral=True)

        vc.play(discord.FFmpegPCMAudio(audio_bytes, pipe=True))

        try: await ctx.message.add_reaction('\U0001f5e3')
        except discord.NotFound: await ctx.reply(':speaking_head:')

    @commands.hybrid_command(name='leave', description='Leave the voice channel (if in one)')
    async def leave(self, ctx: Context):
        vc = ctx.guild.voice_client
        
        if not vc:
            await ctx.reply('I\'m not in a voice channel', ephemeral=True)
            return

        if vc.channel != ctx.author.voice.channel:
            await ctx.reply('You\'re not in the same voice channel as me', ephemeral=True)
            return

        await vc.disconnect(force=True)
        vc.cleanup()
        self.queue.clear()
        await ctx.reply('Farewell')

    @commands.hybrid_command(name='join', description='Join the voice channel you\'re in')
    async def join(self, ctx: Context):
        vc = await self.join_vc(ctx)
        if vc is None:
            return
        await ctx.reply('Hello there')

    def get_sound_files(self, with_extension: bool = True) -> list[str]:
        if with_extension:
            return ['.'.join(file.split('.')[:-1]) for file in os.listdir('resources/sounds')]
        return [file for file in os.listdir('resources/sounds')]

    @commands.hybrid_command(name='sounds', aliases=['soundboard'], description='View all the sounds available to play')
    async def sounds(self, ctx: Context):
        sound_files = '`, `'.join(self.get_sound_files(False))
        await ctx.reply(f'Available sounds:`{sound_files}`\n\nRun the command </sound:1308500118554546220> to play a sound', ephemeral=True)

    @commands.hybrid_command(name='sound', aliases=['s'], description='Play a specified sound')
    @app_commands.describe(sound='The sound you want to play')
    async def sound(self, ctx: Context, *, sound: commands.Range[str, 1, 64]):
        vc = await self.join_vc(ctx)
        if vc is None:
            return

        audio_extensions = ['.mp3', '.ogg', '.wav', '.flac', '.m4a']

        sound_path = None
        for ext in audio_extensions:
            potential_path = f'resources/sounds/{sound}{ext}'
            if os.path.isfile(potential_path):
                sound_path = potential_path
                break

        if not sound_path:
            await ctx.reply(f"Sound file for '{esc_md(esc_me(sound))}' was not found", ephemeral=True)
            return

        await ctx.reply(f'Playing the sound `{sound}`')
        vc.play(discord.FFmpegPCMAudio(sound_path))

    @sound.autocomplete('sound')
    async def sound_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        file_names_without_extensions = self.get_sound_files()
        return [Choice(name=file_name, value=file_name) for file_name in file_names_without_extensions if file_name.lower().startswith(current.lower())][:25]


async def setup(bot: Woolinator) -> None:
    await bot.add_cog(Voice(bot))
