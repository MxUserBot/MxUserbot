# ©️ Pasha Hatsune, 2025-2026
# This file is a part of MXUserbot
# 🌐 https://github.com/MxUserBot/MXUserbot
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import asyncio
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..__main__ import MXUserBot

from loguru import logger
from mautrix.types import (
    EventType,
    Membership,
    MessageEvent,
    StateEvent,
    TrustState,
)
from mxc.callback import BaseCallBack
from pydantic import ValidationError

from mxc import utils
from mxc.exceptions import UsageError
from mxc.fsm import FSMContext


class CallBack(BaseCallBack):
    def __init__(self, mx: 'MXUserBot'):
        super().__init__(mx)
        self.mx = mx
        self._encrypted_warned: set[str] = set()

    async def get_perm_module(self, mod):
        return self.mx if getattr(mod, "_is_core", False) else self.mx.interface

    async def message_cb(self, evt: MessageEvent):
        if evt.event_id in self.mx._ignore_ids:
            self.mx._ignore_ids.remove(evt.event_id)
            return

        if self.mx.start_time and evt.timestamp < self.mx.start_time:
            return

        if evt.type == EventType.ROOM_ENCRYPTED:
            success = await utils.decrypt_event(self.mx, evt)

            if success:
                evt.__class__ = MessageEvent
            elif not success:
                if evt.room_id not in self._encrypted_warned:
                    self._encrypted_warned.add(evt.room_id)
                    try:
                        device = await self.mx.client.crypto.crypto_store.get_device(
                            self.mx.client.mxid, self.mx.client.device_id
                        )
                        if device and device.trust < TrustState.VERIFIED:
                            from mautrix.types import TextMessageEventContent
                            content = TextMessageEventContent(
                                body="⚠️ Cannot process commands in encrypted rooms: device not verified. Verify it in your client or use an unencrypted room.",
                                msgtype="m.notice",
                            )
                            await self.mx.client.send_message(evt.room_id, content)
                    except Exception:
                        pass
                return


        if not getattr(evt.content, "body", None) or utils.should_ignore_event(self.mx, evt):
            return

        body = evt.content.body.strip()
        prefix = await utils.get_prefix(self.mx)
        if isinstance(prefix, (list, tuple, set)):
            prefix = next((str(item) for item in prefix if item and body.startswith(str(item))), None)
        else:
            prefix = str(prefix) if prefix and body.startswith(str(prefix)) else None


        wrapped = await self._wrap_event(evt)
        current_state = self.mx.fsm.get_state(evt, ignore_ids=self.mx._ignore_ids)
        if current_state:
            if prefix:
                self.mx.fsm.finish(evt)
            else:
                for mod in self.mx.active_modules.values():
                    if not mod.enabled:
                        continue
                    for attr_name in dir(mod):
                        func = getattr(mod, attr_name)
                        if callable(func) and getattr(func, "is_state", False):
                            if getattr(func, "target_state", None) == current_state:
                                ctx = FSMContext(self.mx.fsm, evt)
                                asyncio.create_task(
                                    self._safe_run(
                                        mod,
                                        func,
                                        wrapped,
                                        reserved_count=4,
                                        extra_args=[ctx],
                                        reply_on_validation_error=True,
                                    )
                                )
                                return

        if prefix:
            cmd_payload = body[len(prefix):].strip().split(maxsplit=1)
            if not cmd_payload:
                return

            cmd_name = cmd_payload[0].lower()
            args_str = cmd_payload[1] if len(cmd_payload) > 1 else ""

            cmd_info = self.mx.all_modules.command_registry.get(cmd_name)

            if not cmd_info:
                return

            mod = cmd_info["module"]
            func = cmd_info["func"]

            if not await self.mx.security.check_access(evt.sender, func, cmd_name):
                return

            if hasattr(mod, "config") and hasattr(mod.config, "get_missing_required"):
                missing = mod.config.get_missing_required()
                if missing:
                    desc = mod.config.get_description(missing)
                    await wrapped.reply(
                        f"❌ <b>Config required:</b> {mod.name}<br>"
                        f"Key <code>{missing}</code> ({desc}) is empty.<br>"
                        f"Use: <code>{prefix}cfg {mod.name} {missing} [value]</code>"
                    )
                    return

            reply_text = await wrapped.get_reply_text()

            try:
                token = self.mx.interface._current_event.set(wrapped)
                try:
                    cmd_args = args_str if args_str else (reply_text or "")
                    await self._invoke_validated(
                        func=func,
                        reserved_args=[await self.get_perm_module(mod), wrapped],
                        reserved_count=3,
                        raw_input=cmd_args,
                    )
                finally:
                    self.mx.interface._current_event.reset(token)
                return

            except (ValidationError, UsageError):
                orig_f = getattr(func, "__func__", func)
                raw_doc = getattr(orig_f, "__doc__", "") or ""
                clean = raw_doc.replace("<", "&lt;").replace(">", "&gt;")

                await wrapped.reply(f"ℹ️ <b>Usage:</b> <code>{prefix}{cmd_name} {clean}</code>")
                return
            except Exception as e:
                logger.exception(f"Command execution error: {cmd_name}")
                await wrapped.reply(f"❌ <b>Error:</b> <code>{e}</code>")
                return

        for mod in self.mx.active_modules.values():
            if not mod.enabled or not getattr(mod, "_is_ready", False):
                continue

            for w_func in getattr(mod, "_watchers", []):
                match = w_func.regex.search(body)
                if match:
                    if await self.mx.security.check_access(evt.sender, w_func, w_func.__name__):
                        asyncio.create_task(
                            self._safe_run(
                                mod,
                                w_func,
                                wrapped,
                                match=match,
                            )
                        )

        await self._dispatch_event(evt)

    async def invite_cb(self, evt: StateEvent) -> None:
        if self.mx.start_time and evt.timestamp < self.mx.start_time:
            return

        if evt.type != EventType.ROOM_MEMBER or evt.content.membership != Membership.INVITE:
            return

        if evt.state_key != self.mx.client.mxid:
            return

    async def memberevent_cb(self, evt: StateEvent) -> None:
        if self.mx.start_time and evt.timestamp < self.mx.start_time:
            return

        if evt.type != EventType.ROOM_MEMBER:
            return

        await self._dispatch_event(evt)
