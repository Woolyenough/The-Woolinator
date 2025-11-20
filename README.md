# The Woolinator
A multipurpose, personal Discord bot written in Python 3.12 using the discord.py API wrapper

## Running an Instance
> [!WARNING]
> This project has only been tested on Linux. You may encounter issues related to file paths or other platform-specific behaviour when running on Windows.

> [!NOTE]
> The version here may not reflect what the bot is currently running. I tend to test changes before pushing to GitHub.

This project isn't really intended to be forked and used as-is, but serves as an example which can hopefully help others with their own projects. Nonetheless, you are welcome to try and run an instance yourself.

To do this, you will need:
- A MariaDB/MySQL server
- A Discord bot application (https://discord.com/developers/applications)
- Python 3.12.x

To configure, copy `.env.TEMPLATE` into `.env`, and modify the values inside it.

Then, run with Python (on Linux, using Bash):
```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python launcher.py
```

## Public Instances
The bot is only in servers that I like. Here are a few of them:
1. [Sharpness](https://discord.gg/sharpness)&nbsp;&nbsp;![Join](https://badgen.net/discord/members/sharpness?color=blue&label=&cache=600&scale=.95)
2. [BlotCraft](https://discord.gg/blotcraft)&nbsp;&nbsp;![Join](https://badgen.net/discord/members/WykQ2cpVqx?color=blue&label=&cache=600&scale=.95)

If you would like to have it added to your server, you may contact me: `@woolyenough`

## Attribution
- [discord.py](https://github.com/Rapptz/discord.py) - a Discord API wrapper which was used
- [R. Danny](https://github.com/Rapptz/RoboDanny) - many of The Woolinator's features & design choices were inspired by the R. Danny bot

## Licence
This project is licensed under the CC0 (Creative Commons Zero) licence. You are free to use, modify, and share it without restriction. Attribution is not required - but if this project helped you out, a star is always appreciated!
