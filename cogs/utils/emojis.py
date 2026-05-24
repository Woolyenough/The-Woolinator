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

@dataclass
class Flags:
    staff = "<:staff:1507956208961589400>"
    partner = "<:partner:1507957018999132341>"
    hypesquad = "<:hypesquad:1507957137681154238>"
    hypesquad_bravery = "<:hypesquad_bravery:1507957426606047252>"
    hypesquad_brilliance = "<:hypesquad_brilliance:1507957493559459983>"
    hypesquad_balance = "<:hypesquad_balance:1507957548681007175>"
    bug_hunter = "<:bug_hunter:1507957700158558368>"
    bug_hunter_level_2 = "<:bug_hunter_level_2:1507957701454598184>"
    early_supporter = "<:early_supporter:1507957792009621584>"
    verified_bot_developer = "<:verified_bot_developer:1507957890198274199>"
    discord_certified_moderator = "<:discord_certified_moderator:1507957978949484604>"

class Emojis:
    warn = "<:warn:1381478501562974261>"
    info = "<:info:1381486855610171422>"
    server_boost = "<:server_boost:1508142145960415284>"
    Tick = Tick()
    Presence = Presence()
    Flags = Flags()


def tick(state: Optional[bool] = True) -> str:
    """ Returns an emoji based on the parsed value. """

    lookup = {
        True: Emojis.Tick.green,
        False: Emojis.Tick.red,
        None: Emojis.Tick.grey,
    }
    return lookup.get(state, Emojis.Tick.grey)
