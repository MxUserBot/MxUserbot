import asyncio
import signal
import functools
from .bot import Bot

import traceback
import sys


from .modules.core.init_client import init_client
from . import handle_exit, run, shutdown


async def main():
    bot = Bot()
    init_client()

    loop = asyncio.get_running_loop()

    for signame in {'SIGINT', 'SIGTERM'}:
        loop.add_signal_handler(
            getattr(signal, signame),
            functools.partial(handle_exit, signame, loop))

    await run(bot)
    await shutdown()


try:
    asyncio.run(main())
except Exception as e:
    traceback.print_exc(file=sys.stderr)
