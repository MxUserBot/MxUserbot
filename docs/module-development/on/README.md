# on

## If very short

`@loader.on(...)` is needed when the module should react to an event.

Not to a command.
Not to an FSM step.
Exactly to an event.

Example:

- someone wrote a message;
- someone put a reaction;
- someone entered the room.

## When to take `on`

Take `on` if your module should "listen to the world".

That is, not wait for `.command`, but notice itself that something happened.

## Simple metaphor

Command — this is when the user knocks on the door and says:
"do this".

`on` — this is when the door opened itself, and you want to react to it.

## Basic example

```python
from mautrix.types import EventType, MessageEvent

from ...core import loader


@loader.tds
class DemoModule(loader.Module):
    @loader.on(EventType.ROOM_MESSAGE)
    async def handle_message(self, mx, event: MessageEvent):
        body = getattr(event.content, "body", "") or ""
        self.log.info(f"Message: {body}")
```

## What happens here

### `@loader.on(EventType.ROOM_MESSAGE)`

This tells the loader:

"run this function when a regular message comes".

### `event: MessageEvent`

This is the event itself.

From it you can get:

- `event.sender`
- `event.room_id`
- `event.content.body`

## What events are really available

Currently core dispatches:

- `EventType.ROOM_MESSAGE`
- `EventType.REACTION`
- `EventType.ROOM_REDACTION`
- `EventType.ROOM_TOMBSTONE`
- `EventType.ROOM_MEMBER`

## Very important question: why is this needed at all

Without `on` you can only react to commands.

But many modules should live "by themselves":

- auto-responder;
- logger;
- anti-spam;
- statistics;
- welcome module;
- text analyzer.

All such things are built around `on`.

## Example: count messages

```python
from mautrix.types import EventType, MessageEvent

from ...core import loader


@loader.tds
class CounterModule(loader.Module):
    async def _matrix_start(self, mx):
        self.message_count = 0

    @loader.on(EventType.ROOM_MESSAGE)
    async def on_message(self, mx, event: MessageEvent):
        if event.sender == mx.client.mxid:
            return

        body = getattr(event.content, "body", "") or ""
        if body.startswith(tuple(await mx.get_prefix())):
            return

        self.message_count += 1
```


`Pydantic` removes validation garbage.
But should not remove the common sense of the module.

## Can payload be used in `on`

Yes.

Now the callback can validate arguments for `on` too.

Example:

```python
from typing import Any

from mautrix.types import EventType, MessageEvent
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...core import loader


class PricePayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    text: str = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def parse_payload(cls, value: Any):
        if isinstance(value, str):
            return {"text": value}
        return value


@loader.tds
class PriceModule(loader.Module):
    @loader.on(EventType.ROOM_MESSAGE)
    async def on_message(
        self,
        mx,
        event: MessageEvent,
        payload: PricePayload,
    ):
        self.logger.info(payload.text)
```

In this example:

- callback itself takes `event.content.body`;
- itself tries to assemble `payload`;
- itself validates;
- and only then calls your function.

## What is convenient in `ROOM_MESSAGE`

For message events the callback adds helper methods:

- `await event.reply(text)`
- `await event.react(key)`
- `await event.get_reply_text()`

This is very convenient.

Example:

```python
@loader.on(EventType.ROOM_MESSAGE)
async def wave(self, mx, event: MessageEvent):
    body = getattr(event.content, "body", "") or ""
    if "hello" in body.lower():
        await event.reply("Hi!")
```

## When `on` is not needed

Don't take `on` if:

- the action should be launched only by command;
- this is part of a dialog from several steps.

Then better:

- `@loader.command(...)`
- `@loader.state(...)`

## What to look at next

- [Main page of the section](../README.md)
- [watcher](../watcher/README.md)
- [fsm](../fsm/README.md)
- [event_handler_example.py](../../test_modules/event_handler_example.py)
