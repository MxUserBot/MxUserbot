# ©️ Pasha Hatsune, 2025-2026
# This file is a part of MXUserbot
# 🌐 https://github.com/MxUserBot/MXUserbot
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import asyncio
import tempfile
import time

from loguru import logger

from mxc import utils
from mxc.types import Document

from .langs import STRINGS


class MXLog:
    def __init__(self, mx):
        self.mx = mx
        self.strings = STRINGS
        self.queue = asyncio.Queue()
        self._worker_task = asyncio.create_task(self._worker())
        self._last_send = 0.0
        self._send_history = []
        self._consecutive_errors = 0

        self._min_interval = 5.0
        self._max_per_minute = 6

    def write(self, message):
        self.queue.put_nowait(message)

    async def _worker(self):
        while True:
            try:
                batch = []
                batch.append(await self.queue.get())

                while not self.queue.empty():
                    try:
                        batch.append(self.queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break

                if not batch:
                    await asyncio.sleep(0.5)
                    continue

                text = "".join(batch).strip()
                if not text:
                    await asyncio.sleep(0.5)
                    continue

                room_id = await self.mx._db.get("core", "log_room_id")
                if not room_id:
                    await asyncio.sleep(2)
                    continue

                now = time.monotonic()
                self._send_history = [t for t in self._send_history if now - t < 60]
                if len(self._send_history) >= self._max_per_minute:
                    wait = 60 - (now - self._send_history[0])
                    await asyncio.sleep(wait)
                self._send_history.append(now)

                since_last = now - self._last_send
                if since_last < self._min_interval:
                    await asyncio.sleep(self._min_interval - since_last)

                try:
                    if len(text) > 4000:
                        await self._send_as_file(room_id, text)
                    else:
                        await utils.answer(
                            self.mx,
                            text=self.strings.get("log.format").format(text=text),
                            room_id=room_id,
                        )
                    self._last_send = time.monotonic()
                    self._consecutive_errors = 0
                except Exception as e:
                    self._consecutive_errors += 1
                    delay = min(2 ** self._consecutive_errors, 30)
                    logger.warning(f"[MXLog] send failed ({e}), retry in {delay}s")
                    await asyncio.sleep(delay)
                    self.queue.put_nowait(text)

                await asyncio.sleep(2)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"[MXLog] worker error: {e}")
                await asyncio.sleep(5)

    async def _send_as_file(self, room_id: str, text: str):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", encoding="utf-8", delete=False
        ) as f:
            f.write(text)
            f.flush()
            fname = f.name

        try:
            import aiofiles

            async with aiofiles.open(fname, "rb") as f:
                data = await f.read()

            doc = Document(
                url=data,
                filename="error.log",
                mimetype="text/plain",
            )
            await utils.answer(self.mx, room_id=room_id, media=doc)
        finally:
            import os

            try:
                os.unlink(fname)
            except Exception:
                pass
