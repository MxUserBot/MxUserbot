import asyncio

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...core import loader, utils


class Meta:
    name = "Shell"
    description = "Execute shell commands"
    version = "1.0.0"
    tags = ["system"]


class ShellPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    command: str = Field(default="", min_length=1)

    @model_validator(mode="before")
    @classmethod
    def check_sudo(cls, v):
        # normalize input
        if isinstance(v, str):
            cmd = v.strip()
            if "sudo" in cmd.split():
                if "-n" not in cmd.split():
                    raise ValueError("Command contains sudo; if you need sudo use the -n flag (NOPASSWD) or configure sudoers accordingly")
            return {"command": cmd}
        return {"command": ""}


class ShellExecutor:
    TIMEOUT = 60.0
    MAX_OUTPUT_LENGTH = 4000

    @classmethod
    async def run(cls, command: str) -> str:
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
        if len(result) > cls.MAX_OUTPUT_LENGTH:
            result = result[: cls.MAX_OUTPUT_LENGTH] + "\n... (output truncated)"

        return result


@loader.tds
class ShellModule(loader.Module):

    strings = {
        "name": "Shell",
        "executing": "<b>⚙️ | Executing command...</b>",
        "result": "<b>📟 | Command:</b> <code>{}</code><br><b>📤 | Output:</b><br><code>{}</code>",
        "error": "<b>❌ | Error executing command:</b><br><pre>{}</pre>",
        "timeout": "<b>⏱️ | Command execution timeout (60s)</b>",
    }

    @loader.command(security=loader.OWNER)
    async def sh(self, mx, event, payload: ShellPayload):
        """<command>
        in sudo: echo <pass> | sudo S my_command."""

        await utils.answer(mx, self.strings.get("executing"))

        try:
            result = await ShellExecutor.run(payload.command)

            await utils.answer(
                mx,
                self.strings.get("result").format(payload.command, result),
            )
        except asyncio.TimeoutError:
            await utils.answer(mx, self.strings.get("timeout"))
            return
        except Exception as e:
            raise e

