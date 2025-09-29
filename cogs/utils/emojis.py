from typing import Optional
from dataclasses import dataclass


@dataclass
class Tick:
    green = "<:green_check:1324872603042713611>"
    red = "<:red_tick:1324872615357190154>"
    grey = "<:grey_slash:1324872625645944882>"

@dataclass
class Presence:
    offline = "<:offline:1358862810255458444>"
    idle = "<:idle:1358862798385316046>"
    dnd = "<:dnd:1358862768702492833>"
    streaming = "<:streaming:1358862835240669284>"
    online = "<:online:1358862820715925695>"

class Emojis:
    warn = "<:warn:1381478501562974261>"
    info = "<:info:1381486855610171422>"
    Tick = Tick()
    Presence = Presence()


def tick(state: Optional[bool] = True) -> str:
    """ Returns an emoji based on the parsed value. """

    lookup = {
        True: Emojis.Tick.green,
        False: Emojis.Tick.red,
        None: Emojis.Tick.grey,
    }
    return lookup.get(state, Emojis.Tick.grey)
