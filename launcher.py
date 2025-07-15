import asyncio
import logging
import os
import signal
import sys
import contextlib
from logging.handlers import RotatingFileHandler

import asyncmy
import discord
from dotenv import load_dotenv

from bot import Woolinator


log = logging.getLogger(__name__)


class RemoveNoise(logging.Filter):

    def __init__(self):
        super().__init__(name='discord.state')

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelname == 'WARNING' and 'referencing an unknown' in record.msg:
            return False
        return True


@contextlib.contextmanager
def setup_logging():
    log = logging.getLogger()

    try:
        discord.utils.setup_logging()

        logging.getLogger('discord').setLevel(logging.INFO)
        logging.getLogger('discord.http').setLevel(logging.WARNING)
        logging.getLogger('discord.state').addFilter(RemoveNoise())

        log.setLevel(logging.INFO)
        handler = RotatingFileHandler(
            filename='woolinator.log',
            encoding='utf-8',
            mode='w',
            maxBytes=64*1024*1024, # 64 MiB
            backupCount=5
        )

        fmt = logging.Formatter('[{asctime}] [{levelname:<7}] {name}: {message}', '%Y-%m-%d %H:%M:%S', style='{')
        handler.setFormatter(fmt)
        log.addHandler(handler)

        yield

    finally:
        handlers = log.handlers[:]
        for hdlr in handlers:
            hdlr.close()
            log.removeHandler(hdlr)

async def run_bot():
    log = logging.getLogger()
    try:
        pool = await asyncmy.create_pool(
                user=os.getenv('MARIADB_USERNAME'),
                password=os.getenv('MARIADB_PASSWORD'),
                host=os.getenv('MARIADB_HOST'),
                db='Woolinator',
                autocommit=True,
        )
    except Exception as e:
        log.exception('Failed to connect to the database', exc_info=e)
        return

    async with Woolinator() as bot:
        bot.pool = pool

        # Catch CTRL+C (SIGINT) to exit gracefully
        def signal_handler(signal, frame):
            log.info('Received exit signal %s:', signal)
            asyncio.create_task(bot.close())
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)

        await bot.start()

if __name__ == '__main__':
    load_dotenv()

    with setup_logging():
        asyncio.run(run_bot())
