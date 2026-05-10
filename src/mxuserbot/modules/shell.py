#			__  ____  ___   _               _           _   
#			|  \/  \ \/ / | | |___  ___ _ __| |__   ___ | |_ 
#			| |\/| |\  /| | | / __|/ _ \ '__| '_ \ / _ \| __|
#			| |  | |/  \| |_| \__ \  __/ |  | |_) | (_) | |_ 
#			|_|  |_/_/\_\\___/|___/\___|_|  |_.__/ \___/ \__| 
#
# 🔒      Licensed under the GNU AGPLv3
# 🌐 https://www.gnu.org/licenses/agpl-3.0.html


class Meta:
    name = "Shell"
    description = "Execute shell commands"
    version = "1.1.0"
    tags = ["system"]


import asyncio

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mxc import utils
from .. import loader


class ShellPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    command: str = Field(default="", min_length=1)

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, v):
        if isinstance(v, str):
            return {"command": v.strip()}
        return {"command": ""}


class ShellExecutor:
    TIMEOUT = 60.0
    MAX_INLINE_LINES = 1000

    @classmethod
    async def run(cls, command: str) -> tuple[str, bool]:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE,
        )

        try:
            process.stdin.close()
        except Exception:
            pass

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=cls.TIMEOUT,
        )

        output = stdout.decode("utf-8", errors="replace")
        error = stderr.decode("utf-8", errors="replace")

        result = output if output else error
        if not result:
            result = "Command executed successfully (no output)"

        lines = result.splitlines()
        is_large = len(lines) > cls.MAX_INLINE_LINES

        return result, is_large


@loader.tds
class ShellModule(loader.Module):

    strings = {
        "name": "Shell",
        "executing": "<b>⚙️ | Executing command...</b>",
        "confirm": "⚠️ | <b>Security Confirmation</b><br>You are about to execute:<br><code>{}</code><br><br><b>Do you want to proceed?</b>",
        "cancelled": "❌ | <b>Command execution cancelled.</b>",
        "result": "<b>📟 | Command:</b> <code>{}</code><br><b>📤 | Output:</b><br><code>{}</code>",
        "error": "<b>❌ | Error executing command:</b><br><pre>{}</pre>",
        "timeout": "<b>⏱️ | Command execution timeout (60s)</b>",
    }

    @loader.command(security=loader.OWNER)
    async def sh(self, mx, event, payload: ShellPayload):
        """<command>"""

        async def _exec(edit_target=None):
            nonlocal mx, event, payload
            if edit_target:
                await _edit(edit_target, self.strings.get("executing"))

            try:
                result, is_large = await ShellExecutor.run(payload.command)
            except asyncio.TimeoutError:
                msg = self.strings.get("timeout")
                if edit_target:
                    await _edit(edit_target, msg)
                else:
                    await utils.answer(mx, msg, event=event)
                return
            except Exception as e:
                msg = self.strings.get("error").format(e)
                if edit_target:
                    await _edit(edit_target, msg)
                else:
                    await utils.answer(mx, msg, event=event)
                return

            if is_large:
                from mxc.types import Document

                output_bytes = result.encode("utf-8")
                media = Document(url=output_bytes, filename="output.txt", mimetype="text/plain")
                caption = f"<b>📟 | Command:</b> <code>{payload.command}</code><br><b>📄 | Output ({len(result.splitlines())} lines) — sent as file:</b>"
                if edit_target:
                    await _edit(edit_target, caption)
                await utils.answer(mx, text=caption, media=media, event=event)
            else:
                msg = self.strings.get("result").format(payload.command, result)
                if edit_target:
                    await _edit(edit_target, msg)
                else:
                    await utils.answer(mx, msg, event=event)

        async def _edit(target, text):
            if hasattr(target, "edit"):
                await target.edit(text)
            else:
                await utils.answer(mx, text, event=event, edit_id=target)

        has_sudo = "sudo" in payload.command.split()

        if has_sudo:
            async def _on_confirm(ctx):
                if ctx.payload == "yes":
                    await _exec(edit_target=ctx)
                else:
                    await ctx.edit(self.strings.get("cancelled"))
                await ctx.close(clear_reactions=True)

            markup = utils.EmojiKeyBoard(
                rows=[[
                    utils.EmojiButton("✅", "yes"),
                    utils.EmojiButton("❌", "no"),
                ]],
                callback=_on_confirm,
                allowed_senders=event.sender,
                single_use=True,
            )

            await utils.answer(
                mx,
                self.strings.get("confirm").format(payload.command),
                event=event,
                reply_markup=markup,
            )
        else:
            sent = await utils.answer(mx, self.strings.get("executing"), event=event)
            await _exec(edit_target=sent)
