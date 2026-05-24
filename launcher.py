import asyncio
import logging
import os
import signal
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
        if record.levelname == 'WARNING' and 'referencing an unknown' in record.getMessage():
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
            maxBytes=32*1024*1024, # 32 MiB
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
    try:
        pool = await asyncmy.create_pool(
            user=os.getenv('MARIADB_USERNAME'),
            password=os.getenv('MARIADB_PASSWORD'),
            host=os.getenv('MARIADB_HOST'),
            db='Woolinator',
            autocommit=True,
        )
    except Exception:
        log.exception('Failed to connect to the database')
        return

    async with Woolinator() as bot:
        bot.pool = pool

        # Cancel this task on SIGINT/SIGTERM so the `async with` cleanly runs bot.close() once
        main_task = asyncio.current_task()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, main_task.cancel)
            except NotImplementedError:
                pass  # add_signal_handler is unavailable on Windows

        try:
            await bot.start()
        except asyncio.CancelledError:
            log.info('Received exit signal, shutting down')

if __name__ == '__main__':
    load_dotenv()

    with setup_logging():
        asyncio.run(run_bot())
