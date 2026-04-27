# ConfigValue

## If very short

`ConfigValue` is needed for module settings.

That is for everything that:

- you want to change without rewriting code;
- should be stored between restarts;
- relates specifically to the behavior of the module.

## When it is needed

Take `ConfigValue` if you have:

- API key;
- limit;
- on/off switch `True/False`;
- list of rooms;
- operating mode.

Don't take `ConfigValue` if the value:

- lives only inside one command;
- is needed for 2 seconds and then forgotten;
- relates to one FSM dialog, not to the module as a whole.

## How it looks

```python
config = {
    "api_key": loader.ConfigValue("NONE", "API key", required=True),
    "limit": loader.ConfigValue(10, "How many items to load", lambda x: x > 0),
    "enabled": loader.ConfigValue(True, "Enable module"),
}
```

## Parsing in human terms

### `"api_key"`

This is the name of the setting.

By it you will then read it:

```python
token = self.config["api_key"]
```

### `loader.ConfigValue(...)`

This is the description of the setting.

Inside you tell the system:

- what is the default value;
- what is this setting;
- is it required;
- how to validate it.

## `ConfigValue` arguments

### `default`

This is the default value.

Examples:

```python
loader.ConfigValue(False, "Enable feature")
loader.ConfigValue(10, "Items limit")
loader.ConfigValue("NONE", "API key")
```

The type of `default` is very important.
Because by it the system understands what to convert the string to.

For example:

- `"25"` will become `int`, if default was `10`;
- `"true"` will become `bool`, if default was `False`.

### `description`

This is a normal human description.

It is needed:

- for `.help`;
- for `.cfg`;
- so that you yourself don't forget what this field is.

Bad description:

```python
"setting"
```

Normal description:

```python
"Maximum number of images to send"
```

### `validator`

This is a function that says:
"such a value can be accepted" or "such cannot".

Example:

```python
"limit": loader.ConfigValue(10, "Items limit", lambda x: x > 0)
```

What this means:

- `10` is ok;
- `5` is ok;
- `0` is not;
- `-100` is not.

### `required=True`

This means:
"without this setting the module should not work".

Usually marked like this:

- tokens;
- logins;
- external API keys.

Example:

```python
"api_key": loader.ConfigValue("NONE", "API key", required=True)
```

If such a setting is empty, the core itself will not let you run the command
and will prompt the user that it needs to be configured. in the callback there is logic that automatically intercepts required, and if nothing was specified there - tell the user - what and HOW he needs to configure.

### `forbid=True`

This is a rarer thing.

Usually it is needed if the setting should not be changed in the usual way
or if it is a service field.

## How to read settings

### Through square brackets

```python
limit = self.config["limit"]
```

Use this when you are sure the key exists.

### Through `.get(...)`

```python
token = self.config.get("api_key")
```

This is more convenient if you want softer reading.

## How to change settings

```python
ok = self.config.set("limit", "25")
```

What is important here:

- you pass even a string;
- the system itself tries to cast the type;
- then runs the validator;
- if everything is good, saves the value.

If everything is ok, returns `True`.
If not, returns `False`.

## What happens under the hood

When you write:

```python
self.config.set("enabled", "true")
```

the system does approximately like this:

1. looks that `enabled` was `bool` by default;
2. turns the string `"true"` into `True`;
3. checks the validator, if it exists;
4. saves the value.

## Live example

```python
from typing import Any, Literal

from mautrix.types import MessageEvent
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...core import loader, utils


ConfigKey = Literal["limit", "enabled", "api_key"]


class ConfigSetPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    key: ConfigKey
    value: str = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def parse_payload(cls, value: Any):
        if isinstance(value, str):
            parts = value.split(maxsplit=1)
            return {"key": parts[0], "value": parts[1]}
        return value


@loader.tds
class DemoModule(loader.Module):
    config = {
        "limit": loader.ConfigValue(5, "Maximum items", lambda x: x > 0),
        "enabled": loader.ConfigValue(True, "Enable module"),
        "api_key": loader.ConfigValue("NONE", "API key", required=True),
    }

    @loader.command()
    async def cfgdemo(self, mx, event: MessageEvent, payload: ConfigSetPayload):
        """<key> <value> - update config"""
        if self.config.set(payload.key, payload.value):
            await utils.answer(mx, "Saved")
            return

        await utils.answer(mx, "Invalid value")
```

## When `ConfigValue` really helps

Situation:

You wrote a module for API.

Without `ConfigValue` you would have to:

- somewhere manually store the token;
- separately validate values;
- separately remember defaults;
- separately load everything after restart.

With `ConfigValue` this is already built-in.

## What to look at next

- [Main page of the section](../README.md)
- [on](../on/README.md)
- [fsm](../fsm/README.md)
- [config_example.py](../../test_modules/config_example.py)
