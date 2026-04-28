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
    EventType,
    TextMessageEventContent,
    MessageType
)

from . import utils
from .types import FSMContext
from .exceptions import UsageError


pd_config = ConfigDict(arbitrary_types_allowed=True)
join_on_invite = True


class CallBack:
    def __init__(self, mx: 'MXUserBot'):
        self.mx = mx


    async def _wrap_event(
        self,
        evt: MessageEvent
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

    def _get_handler_params(
        self,
        func: callable,
        reserved_count: int,
    ) -> list[inspect.Parameter]:
        orig_f = getattr(func, "__func__", func)
        sig = inspect.signature(orig_f)
        return list(sig.parameters.values())[reserved_count:]

    def _extract_validation_message(
        self,
        error: ValidationError,
    ) -> str:
        try:
            first_error = error.errors(include_url=False)[0]
            return str(first_error.get("msg", "Validation error"))
        except Exception:
            return "Validation error"

    def _build_handler_kwargs(
            self,
            params: list[inspect.Parameter],
            raw_input: Any = None,
            reply_text: str | None = None,
        ) -> dict[str, Any]:
            if not params:
                return {}

            kwargs: dict[str, Any] = {}
            source = raw_input

            if len(params) == 1:
                if source in (None, "") and reply_text:
                    source = reply_text

                if source in (None, ""):
                    if params[0].default is inspect.Parameter.empty:
                        kwargs[params[0].name] = ""
                    
                    return kwargs

                kwargs[params[0].name] = source
                return kwargs


            if isinstance(source, str):
                words = source.split(maxsplit=len(params) - 1) if source else []
            elif source is None:
                words = []
            else:
                words = [source]

            for i, word in enumerate(words):
                if i < len(params):
                    kwargs[params[i].name] = word

            if reply_text:
                mandatory = [
                    p
                    for p in params
                    if p.default in (inspect.Parameter.empty, None)
                ]
                for p in reversed(mandatory):
                    if p.name not in kwargs:
                        kwargs[p.name] = reply_text
                        break

            return kwargs

    async def _invoke_validated(
        self,
        func: callable,
        reserved_args: list[Any],
        reserved_count: int,
        raw_input: Any = None,
        reply_text: str | None = None,
    ) -> None:
        params = self._get_handler_params(func, reserved_count)
        kwargs = self._build_handler_kwargs(
            params=params,
            raw_input=raw_input,
            reply_text=reply_text,
        )

        v_func = validate_call(func, config=pd_config)
        await v_func(*reserved_args, **kwargs)


    async def _safe_run_handler(
        self,
        mod: Any,
        func: callable,
        wrapped_evt: Any
    ) -> None:
        try:
            raw_input = getattr(getattr(wrapped_evt, "content", None), "body", None)
            if raw_input is None:
                raw_input = getattr(wrapped_evt, "content", None)

            token = self.mx.interface._current_event.set(wrapped_evt)
            try:
                await self._invoke_validated(
                    func=func,
                    reserved_args=[self.mx.interface, wrapped_evt],
                    reserved_count=3,
                    raw_input=raw_input,
                )
            finally:
                self.mx.interface._current_event.reset(token)
        except ValidationError as e:
            logger.debug(
                f"Validation skipped event handler '{func.__name__}' "
                f"of module '{mod.name}': {self._extract_validation_message(e)}"
            )
        except Exception as e:
            logger.exception(
                f"Error in event handler '{func.__name__}' "
                f"of module '{mod.name}': {e}"
            )


    async def _safe_run_watcher(
        self,
        mod: Any,
        func: callable,
        wrapped_evt: Any,
        match: Any = None,
    ) -> None:
        try:
            raw_input = getattr(getattr(wrapped_evt, "content", None), "body", None)
            if match:
                groups = match.groups()
                raw_input = (
                    match.groupdict()
                    or (groups[0] if len(groups) == 1 else groups)
                    or match.group(0)
                )

            token = self.mx.interface._current_event.set(wrapped_evt)
            try:
                await self._invoke_validated(
                    func=func,
                    reserved_args=[self.mx.interface, wrapped_evt],
                    reserved_count=3,
                    raw_input=raw_input,
                )
            finally:
                self.mx.interface._current_event.reset(token)
        except ValidationError as e:
            logger.debug(
                f"Validation skipped watcher '{func.__name__}' "
                f"of module '{mod.name}': {self._extract_validation_message(e)}"
            )
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

        if evt.type == EventType.ROOM_ENCRYPTED:
            decrypted_text = await utils.decrypt_event(self.mx, evt)
            if not decrypted_text:
                return 
            
            evt.content = TextMessageEventContent(
                msgtype=MessageType.TEXT,
                body=decrypted_text
            )
            evt.type = EventType.ROOM_MESSAGE

        if not getattr(evt.content, "body", None) or self.mx.should_ignore_event(evt):
            return
        
        body = evt.content.body.strip()
        prefixes = await self.mx.get_prefix()
        prefix = next((p for p in prefixes if body.startswith(p)), None)

        wrapped = await self._wrap_event(evt)
        current_state = self.mx.fsm.get_state(evt)
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
                                    self._safe_run_state_handler(
                                        mod,
                                        func,
                                        wrapped,
                                        ctx,
                                    )
                                )
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

            reply_text = await wrapped.get_reply_text()

            try:
                token = self.mx.interface._current_event.set(wrapped)
                try:
                    await self._invoke_validated(
                        func=func,
                        reserved_args=[self.mx.interface, wrapped],
                        reserved_count=3,
                        raw_input=args_str,
                        reply_text=reply_text,
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
                            self._safe_run_watcher(
                                mod,
                                w_func,
                                wrapped,
                                match=match,
                            )
                        )

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

    async def _safe_run_state_handler(
        self,
        mod: Any,
        func: callable,
        wrapped_evt: Any,
        ctx: FSMContext,
    ) -> None:
        try:
            raw_input = getattr(getattr(wrapped_evt, "content", None), "body", None)

            token = self.mx.interface._current_event.set(wrapped_evt)
            try:
                await self._invoke_validated(
                    func=func,
                    reserved_args=[self.mx.interface, wrapped_evt, ctx],
                    reserved_count=4,
                    raw_input=raw_input,
                )
            finally:
                self.mx.interface._current_event.reset(token)
        except ValidationError as e:
            msg = self._extract_validation_message(e)
            await wrapped_evt.reply(f"❌ <b>Validation:</b> <code>{msg}</code>")
        except Exception as e:
            logger.exception(
                f"Error in state handler '{func.__name__}' "
                f"of module '{mod.name}': {e}"
            )

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
