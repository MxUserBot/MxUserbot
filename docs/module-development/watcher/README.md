# watcher


```python
@loader.watcher(...)
```


## If very short

`watcher` is needed when you want:

"if the message looks like X — run my code".

That is, this is not just the event `message came`.
This is already event plus pattern.

## How `watcher` differs from `on`

### `on`

Reacts to the fact of the event itself.

Example:

- any message came.

### `watcher`

Reacts only if the message matched the pattern.

Example:

- message contains `hello`;
- message looks like a price;
- message contains a link.

## When watcher is more convenient than on

If you would have to write every time:

```python
if not regex.search(body):
    return
```

then, perhaps, you already need `watcher`.

## Basic example

```python
from ...core import loader


@loader.tds
class DemoModule(loader.Module):
    @loader.watcher(r"hello")
    async def hello_watcher(self, mx, event):
        await event.reply("Hello back!")
```

What this means:

- a message comes;
- loader checks regex `hello`;
- if matched, calls the function.

## What regex is used

Inside `loader.watcher(...)` regex is compiled like this:

```python
re.compile(regex, re.IGNORECASE)
```

That is:

- case doesn't matter;
- `hello`, `Hello`, `HELLO` will be considered a match.


## Example with payload

```python
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from ...core import loader


class LinkPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    text: str

    @model_validator(mode="before")
    @classmethod
    def parse_payload(cls, value: Any):
        if isinstance(value, str):
            return {"text": value}
        return value


@loader.tds
class LinkModule(loader.Module):
    @loader.watcher(r"https?://")
    async def link_watcher(self, mx, event, payload: LinkPayload):
        await event.reply(f"Found link in: {payload.text}")
```

## What else watcher can do

If there are groups in the regex, the callback tries to pass the match to the payload.

The logic is:

- if there are named groups, a dictionary will go;
- if there is one regular group, one value will go;
- if there are several groups, a tuple will go;
- if there are no groups, the whole text will go.

## Example with group

```python
from pydantic import BaseModel, Field

from ...core import loader


class PricePayload(BaseModel):
    amount: float = Field(gt=0)


@loader.tds
class PriceModule(loader.Module):
    @loader.watcher(r"(\\d+(?:\\.\\d+)?)\\s*usd")
    async def price_watcher(self, mx, event, payload: PricePayload):
        await event.reply(f"Price detected: {payload.amount}")
```

Here the regex catches a number.
If the number is normal, Pydantic will assemble the payload.

## Why is this convenient

Without watcher you would write:

```python
body = getattr(event.content, "body", "") or ""
match = regex.search(body)
if not match:
    return
```

With watcher you take this "guard at the entrance" out to the loader itself.

That is, the module code becomes shorter and cleaner.

## When watcher is not needed

Don't take watcher if:

- you care about any message, not a pattern;
- this should be a command;
- this is a step-by-step dialog.

Then better:

- `on`
- `command`
- `fsm`

## Important honesty

In the current repository there are almost no live modules with `@loader.watcher(...)`.
But the decorator itself and its support in the callback exist.

That is, the documentation here describes the real mechanics of the core,
not just a dream for the future.

## What to look at next

- [Main page of the section](../README.md)
- [on](../on/README.md)
- [fsm](../fsm/README.md)
