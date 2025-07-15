# The Woolinator
A personal Discord bot written in Python 3.12 using the discord.py API wrapper

## Running an Instance
> [!WARNING]
> This project has only been tested on Linux. You may encounter issues related to file paths or other platform-specific behaviour when running on Windows.

> [!NOTE]
> The version here may not reflect what the bot is currently running. I tend to test changes before pushing to GitHub.

This project isn't really designed to work out of the box, but serves as an example which can hopefully help others with their own projects. This project is not really designed to work out-of-the-box, but you are welcome to adapt it for your purposes. Nonetheless, you can try and run an instance yourself.

To do this, you will need:
- A MariaDB/MySQL server (for persistent data storage)
- A Discord bot application (https://discord.com/developers/applications)

To configure, copy `.env.TEMPLATE` into `.env`, and modify the values inside it.

Then, run with Python 3.12 (Linux & Bash):
```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python launcher.py
```

## Public Instances
The bot is only in servers that I like. Here are a few of them:
1. [discord.gg/sharpness](https://discord.gg/sharpness)
1. [discord.gg/blotcraft](https://discord.gg/blotcraft)

If you would like to have it added to your server, you may contact me: `@woolyenough`

## Attribution
- [discord.py](https://github.com/Rapptz/discord.py) - a Discord API wrapper
- [R. Danny](https://github.com/Rapptz/RoboDanny) - many of The Woolinator's features & design choices were inspired by the R. Danny bot

## Licence
This project is licensed under the CC0 (Creative Commons Zero) licence. You are free to use, modify, and share it without restriction. Attribution is not required - but if this project helped you out, a shoutout is always appreciated!