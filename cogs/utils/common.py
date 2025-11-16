import re
from datetime import timedelta

from dateutil.relativedelta import relativedelta
import discord

async def hybrid_msg_edit(message: discord.Message|discord.InteractionMessage|discord.InteractionCallbackResponse|None, content: str|None, **kwargs):
    """ Edit a hybrid message (`Message`/`InteractionMessage`), ignoring exceptions. """

    if message:
        try:
            if isinstance(message, discord.InteractionCallbackResponse):
                message = message.resource
                if not isinstance(message, discord.InteractionMessage):
                    return
                    
            await message.edit(content=content, **kwargs)
        except (discord.NotFound, discord.HTTPException):
            pass

def trim_str(string: str, max_length: int) -> str:
    """ Trims a string to the specified length, ending with '...' if trimmed. """
    if len(string) > max_length:
        return string[:max_length-3] + '...'
    return string

def plur(val: int) -> str:
    """ Returns 's' if the value is 2 or more or 0. """
    if val == 0 or val >= 2:
        return 's'
    else:
        return ''
    
def format_timedelta(td: timedelta):
    seconds = int(td.total_seconds())
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    
    parts = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} min{'s' if minutes != 1 else ''}")
    if seconds:
        parts.append(f"{seconds} sec{'s' if seconds != 1 else ''}")
    
    if not parts:
        return "0 seconds"
    elif len(parts) == 1:
        return parts[0]
    else:
        return ', '.join(parts[:-1]) + ' and ' + parts[-1]

def parse_entered_duration(when: str) -> tuple[relativedelta, list[str], list[str]]:
    """ Parses a human-readable duration string into a `relativedelta` object.

    The input string can contain multiple time expressions (e.g., '2h, 30m, 1day'), 
    separated by commas and spaces. Each time expression should include 
    a number followed by a time unit (e.g., '10 min', '2 hours', '1d', etc.).

    Time values that exceed reasonable limits (more than 4 years) are flagged 
    and not included in the final duration.

    Returns:
        tuple:
            relativedelta: Total duration parsed from valid parts of the string.
            list[str]: Substrings that could not be parsed due to invalid format.
            list[str]: Substrings that were valid but rejected for being excessively long.

    Example:
        >>> convert_time_human_to_delta('2h, 30 min, 5 days, 1 seco')
        (relativedelta(days=+5, hours=+2, minutes=+30, seconds=+1), [], [])
    """

    duration = relativedelta()

    invalid_formats = []
    too_long = []

    when: list[str] = when.replace('and', ',').replace('&', ',').replace('+', ',').strip(' ').split(',')
    for d in when:
        match = re.match(r"(\d+)(\D+)", d)  # (\d+) captures digits, (\D+) captures non-digits

        if match:
            value = int(match.group(1))  # The number (value)
            unit = match.group(2).lower()  # The unit (characters)

            if "seconds".startswith(unit) or unit == "secs":
                if value > 4 * 12 * 30 * 24 * 60 * 60:
                    too_long.append(d)
                    continue
                duration += relativedelta(seconds=value)

            elif "minutes".startswith(unit) or unit == "mins":
                if value > 4 * 12 * 30 * 24 * 60:
                    too_long.append(d)
                    continue
                duration += relativedelta(minutes=value)

            elif "hours".startswith(unit) or unit == "hrs" or unit == "hr":
                if value > 4 * 12 * 30 * 24:
                    too_long.append(d)
                    continue
                duration += relativedelta(hours=value)

            elif "days".startswith(unit):
                if value > 4 * 12 * 30:
                    too_long.append(d)
                    continue
                duration += relativedelta(days=value)

            elif "weeks".startswith(unit):
                if value > 4 * 12 * 4:
                    too_long.append(d)
                    continue
                duration += relativedelta(weeks=value)

            elif "months".startswith(unit):
                if value > 4 * 12:
                    too_long.append(d)
                    continue
                duration += relativedelta(months=value)

            elif "years".startswith(unit) or unit == "yrs" or unit == "yr":
                if value > 4:
                    too_long.append(d)
                    continue
                duration += relativedelta(years=value)

        else:
            invalid_formats.append(d)

    return duration, invalid_formats, too_long