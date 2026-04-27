# Module Development

Hello.

If you just opened this project for the first time and your brain is melting from words like `loader`, `state`, `Pydantic`, `watcher`, it's normal.

This folder is not made for "experienced architects". It is made so that you can:

1. quickly understand what is generally in the system;
2. not confuse which tool is needed when;
3. take a ready example and start writing a module.

## The Shortest Map

You have 4 main things:

1. [ConfigValue](./ConfigValue/README.md)
2. [on](./on/README.md)
3. [watcher](./watcher/README.md)
4. [fsm](./fsm/README.md)


## What is all this anyway

### `ConfigValue`

These are module settings.

Example:

- API token;
- limit;
- is the module enabled or disabled;
- operating mode.

### `on`

This is "listen to event and react".

Example:

- a message came;
- someone put a reaction;
- someone entered the room.

### `watcher`

This is "catch messages by pattern".

Example:

- if the text contains the word `hello`;
- if the message has a link;
- if someone wrote a price like `100 usd`.

### `fsm`

This is "scenario from several steps".

Example:

- bot asked for name;
- then asked for age;
- then asked for confirmation.

## How to read this documentation

If you are from scratch:

1. first open [ConfigValue](./ConfigValue/README.md);
2. then [on](./on/README.md);
3. then [watcher](./watcher/README.md);
4. then [fsm](./fsm/README.md).

If you need to quickly make a module:

1. look at the needed section;
2. copy the example;
3. change the text, names and logic for yourself.

## The Most Important Idea of the Project

- arguments are described in a Pydantic model;
- the model itself validates the data;
- callback itself passes the payload to your function;
- in your function there remains only useful logic.

That is, you write not "how to parse a string".
You write "what to do with already normal data".

And this greatly simplifies life.

## Validation of Command Arguments

Since version 2.1, the `get_args` function was removed because now a new module writing scheme is used with automatic validation via Pydantic.

There are two main ways to validate command arguments:

### 1. Direct indication of types in function parameters

You can specify types directly in the function signature. Pydantic will automatically validate the arguments.

Example:

```python
@loader.command()
async def example(self, mx, event: MessageEvent, age: int = None):
    """[age] - age"""

    await utils.answer(mx, f"Age: {age}")

```

Here `age: int = None` means that the argument should be an integer or absent.

### 2. Through Pydantic models

For more complex validation, use Pydantic classes.

Example from `afk.py`:

```python
class AFKPayload(BaseModel):
    reason: str = Field(default="", description="AFK reason")

    @model_validator(mode='before')
    @classmethod
    def parse_payload(cls, v):
        if isinstance(v, str):
            return {"reason": v.strip()}
        return v

@loader.command()
async def afk(self, mx, event, payload: AFKPayload):
    """[reason] - Set AFK status"""
    # payload.reason is already validated and processed
```

This method allows flexible parsing and validation of input data.

## Minimal Module

Here is the smallest working template:

```python
from typing import Any

from mautrix.types import MessageEvent
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...core import loader, utils


class Meta:
    name = "HelloModule"
    description = "Very small example module"
    version = "1.0.0"
    tags = ["example"]


class HelloPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def parse_payload(cls, value: Any):
        if isinstance(value, str):
            return {"name": value}
        return value


@loader.tds
class HelloModule(loader.Module):
    @loader.command()
    async def hello(self, mx, event: MessageEvent, payload: HelloPayload):
        """<name> - say hello"""
        await utils.answer(mx, f"Hello, {payload.name}!")
```

## What must be in the module

### `class Meta`

Always needed.

Required fields:

- `name`
- `description`
- `version`
- `tags`

### Module class

Always needed.

Important:

- class name must contain `Module`;
- class must inherit from `loader.Module`;
- better to use `@loader.tds`.

## Where live examples are located

Look:

- [config_example.py](../test_modules/config_example.py)
- [event_handler_example.py](../test_modules/event_handler_example.py)
- [state_management_example.py](../test_modules/state_management_example.py)

## If you want to understand the project even wider

Also look:

- [dev.md](../dev.md)
- [utils-reference.md](../utils-reference.md)
- [security.md](../security.md)
