import discord
from discord.ext import commands


class Context(commands.Context):
    prefix: str

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @discord.utils.cached_property
    def replied_message(self) -> discord.Message|None:
        ref = self.message.reference
        if ref and isinstance(ref.resolved, discord.Message):
            return ref.resolved
        return None

    async def react(self, state: bool = True) -> None:
        lookup = {
            True: "\U0001f44c",  # 👌
            False: "\U0001f6ab",  # 🚫
        }
        try:
            await self.message.add_reaction(lookup.get(state))
        except (discord.HTTPException, discord.Forbidden, TypeError):
            pass

    async def send(self, content: str | None = None, **kwargs) -> discord.Message:
        limit = 2000
        if content and len(content) > limit:
            suffix = "\n\n [ Message cropped ]"
            content = content[:limit - len(suffix)] + suffix
        return await super().send(content, **kwargs)

    async def reply(self, content: str | None = None, **kwargs) -> discord.Message:
        limit = 2000
        if content and len(content) > limit:
            suffix = "\n\n [ Message cropped ]"
            content = content[:limit - len(suffix)] + suffix

        try:
            return await super().reply(content, **kwargs)
        except (discord.HTTPException): # In case the message no longer exists
            return await super().send(content, **kwargs)
