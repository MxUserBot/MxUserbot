#			__  ____  ___   _               _           _   
#			|  \/  \ \/ / | | |___  ___ _ __| |__   ___ | |_ 
#			| |\/| |\  /| | | / __|/ _ \ '__| '_ \ / _ \| __|
#			| |  | |/  \| |_| \__ \  __/ |  | |_) | (_) | |_ 
#			|_|  |_/_/\_\\___/|___/\___|_|  |_.__/ \___/ \__| 
#
# 🔒      Licensed under the GNU AGPLv3
# 🌐 https://www.gnu.org/licenses/agpl-3.0.html


class Meta:
    name = "PrefixModule"
    description = "Управление префиксом команд юзербота."
    version = "1.0.1"
    tags = ["settings"]


from mautrix.types import MessageEvent

from mxc.exceptions import UsageError
from mxc import utils
from .. import loader



@loader.tds
class PrefixModule(loader.Module):
    config = {
        "allowed_symbols": loader.ConfigValue(default="!\"./\\,;:@#$%^&*-_+=?|~", description="list allowed symbols"),
    }

    strings = {
        "error_no_args": "❌ | <b>No prefix specified.</b><br>Example: <code>.set_prefix !</code>",
        "error_too_long": "❌ | <b>The prefix must be exactly <u>one</u></b> character long.",
        "error_set_prefix": "❌ | <b>The character <code>{new_prefix}</code> is not allowed.</b><br>"
                            "You can only use: <code>{allowed_symbols}</code>",
        "success_set_prefix": "✅ | <b>Prefix successfully changed to</b>: <code>{new_prefix}</code>"
    }

    @loader.command(security=loader.OWNER)
    async def set_prefix(self, mx, event: MessageEvent):
        """Установить новый префикс (только спец. символы)"""

        args = await utils.get_args(
            mx=mx,
            event=event
        )
    
        if len(args) < 1:
            raise UsageError(self.strings.get("error_no_args"))

        new_prefix = args[0]

        if len(new_prefix) != 1:
            return await utils.answer(mx, self.strings.get("error_too_long"))

        allowed = self.config.get("allowed_symbols")

        if new_prefix not in allowed:
            return await utils.answer(mx, 
                self.strings.get("error_set_prefix").format(
                    new_prefix=new_prefix,
                    allowed_symbols=allowed
                )
            )

        query = [new_prefix]
        await self._db.set("core", "prefix", query)
        mx._prefixes = query

        await utils.answer(mx, 
            self.strings.get("success_set_prefix").format(new_prefix=new_prefix)
        )