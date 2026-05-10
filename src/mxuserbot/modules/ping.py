#			__  ____  ___   _               _           _   
#			|  \/  \ \/ / | | |___  ___ _ __| |__   ___ | |_ 
#			| |\/| |\  /| | | / __|/ _ \ '__| '_ \ / _ \| __|
#			| |  | |/  \| |_| \__ \  __/ |  | |_) | (_) | |_ 
#			|_|  |_/_/\_\\___/|___/\___|_|  |_.__/ \___/ \__| 
#
# 🔒      Licensed under the GNU AGPLv3
# 🌐 https://www.gnu.org/licenses/agpl-3.0.html


class Meta:
    name = "PingPong"
    description = "Simple ping-pong + dm checker"
    version = "1.1.0"
    tags = ["system"]


import time

from mxc import utils
from .. import loader


@loader.tds
class PingPongModule(loader.Module):
    """Ping-pong module"""

    strings = {
        "name": "PingPong",
        "pinging": "<b>🏓 | Pinging...</b>",
        "pong": "<b>🏓 | Pong!</b><br><b>🚀 | Latency:</b> <code>{} ms</code>",
    }

    @loader.command(security=loader.OWNER)
    async def ping(self, mx, event):
        """Check bot latency"""
        start = time.perf_counter()

        status_id = await utils.answer(mx, self.strings.get("pinging"))

        end = time.perf_counter()
        duration = round((end - start) * 1000, 2)

        await utils.answer(
            mx,
            self.strings.get("pong").format(duration),
            edit_id=status_id
        )