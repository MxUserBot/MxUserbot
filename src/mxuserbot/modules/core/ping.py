import time

from ...core import loader, utils


class Meta:
    name = "PingPong"
    description = "Simple ping-pong + dm checker"
    version = "1.1.0"
    tags = ["system"]


@loader.tds
class PingPongModule(loader.Module):
    """Ping-pong module"""

    strings = {
        "name": "PingPong",
        "pinging": "<b>🏓 | Pinging...</b>",
        "pong": "<b>🏓 | Pong!</b><br><b>🚀 | Latency:</b> <code>{} ms</code>",
    }

    @loader.command()
    async def ping(self, mx, event):
        """Check bot latency"""
        start = time.perf_counter()

        await utils.answer(mx, self.strings.get("pinging"))

        end = time.perf_counter()
        duration = round((end - start) * 1000, 2)

        await utils.answer(
            mx,
            self.strings.get("pong").format(duration)
        )