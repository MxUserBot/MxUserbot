import inspect
import asyncio
from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    from ..__main__ import MXUserBot

from loguru import logger
from pydantic import validate_call, ValidationError, ConfigDict

from mautrix.types import (
    StateEvent, 
    MessageEvent, 
    Membership, 
    EventType
)

from . import utils, loader
from .exceptions import UsageError


pd_config = ConfigDict(arbitrary_types_allowed=True)
join_on_invite = True


class CallBack:
    def __init__(self, mx: 'MXUserBot'):
        self.mx = mx


    async def _wrap_event(
        self,
        evt: Any
    ) -> Any:
        async def reply(text: str, html: bool = True):
            event_id = await utils.answer(self.mx.interface, text, html=html, event=evt)
            
            self.mx._ignore_ids.add(event_id)
            
            return event_id

        async def react(
            key: str
        ):
            return await self.mx.client.react(evt.room_id, evt.event_id, key)


        async def get_reply_text(

        ) -> EventType:
            return await utils.get_reply_text(self.mx.interface, evt)

        if hasattr(evt, "room_id") and hasattr(evt, "event_id"):
            evt.reply = reply
            evt.react = react
            evt.get_reply_text = get_reply_text
        
        return evt


    async def _dispatch_event(
        self,
        event_type:
        EventType,
        evt: Any
    ) -> None:
        wrapped_evt = evt
        if isinstance(evt, MessageEvent):
            wrapped_evt = await self._wrap_event(evt)

        for mod in self.mx.active_modules.values():
            if not mod.enabled or not getattr(mod, "_is_ready", False):
                continue
            
            handlers = getattr(mod, "_event_handlers", {}).get(event_type,[])
            for handler in handlers:
                asyncio.create_task(self._safe_run_handler(mod, handler, wrapped_evt))


    async def _safe_run_handler(
        self,
        mod: Any,
        func: callable,
        wrapped_evt: Any
    ) -> None:
        try:
            await func(self.mx.interface, wrapped_evt)
        except Exception as e:
            logger.exception(f"Error in event handler '{func.__name__}' of module '{mod.name}': {e}")


    async def _safe_run_watcher(
        self,
        mod: Any,
        func: callable,
        wrapped_evt: Any
    ) -> None:
        try:
            await func(self.mx.interface, wrapped_evt)
        except Exception as e:
            logger.exception(f"Error in watcher '{func.__name__}' of module '{mod.name}': {e}")


    async def message_cb(
        self,
        evt: MessageEvent
    ):
        if evt.event_id in self.mx._ignore_ids:
            self.mx._ignore_ids.remove(evt.event_id) 
            return

        if self.mx.start_time and evt.timestamp < self.mx.start_time:
            return
        if not evt.content.body or self.mx.should_ignore_event(evt):
            return

        body = evt.content.body.strip()
        prefixes = await self.mx._db.get("core", "prefix")
        prefix = next((p for p in prefixes if body.startswith(p)), None)

        wrapped = await self._wrap_event(evt)


        current_state = self.mx.fsm.get_state(evt)

        if current_state:
            if prefix:
                self.mx.fsm.finish(evt) 
                for mod in self.mx.active_modules.values():
                    if not mod.enabled: continue
                    for attr_name in dir(mod):
                        func = getattr(mod, attr_name)
                        if callable(func) and getattr(func, "is_state", False):
                            if getattr(func, "target_state", None) == current_state:
                                ctx = loader.FSMContext(self.mx.fsm, evt)
                                asyncio.create_task(func(self.mx.interface, wrapped, ctx))
                                return
                            

        if prefix:
            cmd_payload = body[len(prefix):].strip().split(maxsplit=1)
            if not cmd_payload:
                return

            cmd_name = cmd_payload[0].lower()
            args_str = cmd_payload[1] if len(cmd_payload) > 1 else ""

            # for mod in self.mx.active_modules.values():
            #     if not mod.enabled or cmd_name not in mod.commands:
            #         continue
                
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

            orig_f = getattr(func, "__func__", func)
            sig = inspect.signature(orig_f)
            params = list(sig.parameters.values())[3:]
            
            kwargs = {}
            mandatory = [p for p in params if p.default in (inspect.Parameter.empty, None)]
            words = args_str.split(maxsplit=len(params)-1) if args_str and params else []
            reply_text = await wrapped.get_reply_text()

            if len(words) == len(mandatory) and not reply_text:
                for i, p in enumerate(mandatory): kwargs[p.name] = words[i]
            else:
                for i, word in enumerate(words):
                    if i < len(params): kwargs[params[i].name] = word

            if reply_text:
                for p in reversed(mandatory):
                    if p.name not in kwargs:
                        kwargs[p.name] = reply_text
                        break

            try:
                for p in mandatory:
                    if p.name not in kwargs or kwargs[p.name] is None:
                        raise UsageError()

                v_func = validate_call(func, config=pd_config)
                token = self.mx.interface._current_event.set(wrapped)
                try:
                    await v_func(self.mx.interface, wrapped, **kwargs)
                finally:
                    self.mx.interface._current_event.reset(token)
                return 

            except (ValidationError, UsageError):
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
                if w_func.regex.search(body):
                    if await self.mx.security.check_access(evt.sender, w_func, w_func.__name__):
                        asyncio.create_task(self._safe_run_watcher(mod, w_func, wrapped))

        await self._dispatch_event(EventType.ROOM_MESSAGE, evt)


    async def invite_cb(
        self,
        evt: StateEvent
    ) -> None:
        if self.mx.start_time and evt.timestamp < self.mx.start_time:
            return

        if evt.type != EventType.ROOM_MEMBER or evt.content.membership != Membership.INVITE:
            return

        if evt.state_key != self.mx.client.mxid:
            return

        # sender = evt.sender
        # room_id = evt.room_id
        # via_server = sender.split(":")[-1]

        # if join_on_invite or await self.mx.is_owner(evt):
        #     try:
        #         await self.mx.client.join_room(room_id, servers=[via_server])
        #         logger.info(f"Successfully joined room '{room_id}' (invited by '{sender}')")
        #     except Exception as e:
        #         logger.error(f"Failed to join room {room_id}: {e}")


    async def memberevent_cb(
        self,
        evt: StateEvent
    ) -> None:
        if self.mx.start_time and evt.timestamp < self.mx.start_time:
            return

        if evt.type != EventType.ROOM_MEMBER:
            return

        await self._dispatch_event(EventType.ROOM_MEMBER, evt)

        # content = evt.content
        # room_id = evt.room_id
        # target_user = evt.state_key 

        # if target_user == self.mx.client.mxid:
        #     return

        # if content.membership == Membership.LEAVE:
        #     try:
        #         members = await self.mx.client.get_joined_members(room_id)
        #         if len(members) == 1:
        #             logger.info(f"Leaving {room_id} as the bot is the only remaining member.")
        #             await self.mx.client.leave_room(room_id)
        #     except Exception as e:
        #         logger.warning(f"Failed to verify member count in {room_id}: {e}")