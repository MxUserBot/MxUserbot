# fsm

## If very short

FSM is needed for a dialog from several steps.

Not one message.
But a chain of messages.

Example:

1. bot asked for name;
2. user answered;
3. bot asked for age;
4. user answered;
5. bot completed the scenario.

## What FSM means

FSM = finite state machine.

If in human terms:

this is a way to remember
at what step of the conversation the user is currently at.

## When to take FSM

Take FSM if you have:

- questionnaire;
- setup wizard;
- deletion confirmation;
- step-by-step survey;
- form from several messages.

Don't take FSM if everything can be done with one command.

## What parts does FSM consist of

### 1. `StatesGroup`

This is a set of states.

Example:

```python
from ...core.types import State, StatesGroup


class SurveyStates(StatesGroup):
    name = State()
    age = State()
    confirm = State()
```

This is read as:

- there is a scenario `SurveyStates`;
- in it step `name`;
- then step `age`;
- then step `confirm`.

### 2. `FSMContext`

This is an object through which you control the state.

It can:

- `set_state(...)`
- `update_data(...)`
- `get_data()`
- `clear()`

### 3. `@loader.state(...)`

This is a handler for a specific step.

Example:

```python
@loader.state(SurveyStates.name)
async def process_name(self, mx, event, state: FSMContext, payload: NamePayload):
    ...
```

## How a full scenario looks

### Step 1. Describe states

```python
from ...core.types import State, StatesGroup


class SurveyStates(StatesGroup):
    name = State()
    age = State()
    confirm = State()
```

### Step 2. Start the scenario with a command

```python
from mautrix.types import MessageEvent

from ...core import loader, utils
from ...core.types import FSMContext


@loader.command()
async def survey(self, mx, event: MessageEvent):
    """start survey"""
    state = FSMContext(mx.fsm, event)
    await state.clear()
    await state.set_state(SurveyStates.name)
    await utils.answer(mx, "What is your name?")
```

### Step 3. Process the response

```python
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NamePayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=32)

    @model_validator(mode="before")
    @classmethod
    def parse_payload(cls, value: Any):
        if isinstance(value, str):
            return {"name": value}
        return value


@loader.state(SurveyStates.name)
async def process_name(
    self,
    mx,
    event,
    state: FSMContext,
    payload: NamePayload,
):
    await state.update_data(name=payload.name)
    await state.set_state(SurveyStates.age)
    await event.reply("How old are you?")
```

### Step 4. Take the next response

```python
class AgePayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    age: int = Field(ge=1, le=120)

    @model_validator(mode="before")
    @classmethod
    def parse_payload(cls, value: Any):
        if isinstance(value, str):
            return {"age": value}
        return value


@loader.state(SurveyStates.age)
async def process_age(
    self,
    mx,
    event,
    state: FSMContext,
    payload: AgePayload,
):
    await state.update_data(age=payload.age)
    data = await state.get_data()
    await state.clear()
    await event.reply(f"Saved: {data['name']} / {payload.age}")
```

## What is magical here

The user writes ordinary messages without prefix.

But the callback looks:

- does this user have an active state;
- if yes, what exactly is this state;
- which `@loader.state(...)` is bound to it;
- can payload be assembled from the text;
- and only then calls your function.

That is, you write not "how to catch the next message".
You write "what to do at the age step".

This is much simpler.

## How to store data between steps

Through `state.update_data(...)`.

Example:

```python
await state.update_data(name=payload.name)
```

Then on another step:

```python
data = await state.get_data()
name = data["name"]
```

## How to finish the scenario

Through:

```python
await state.clear()
```

This is very important.

If you don't clear the state, the user will remain "locked" in the old step.

## How to cancel the scenario

Usually with a separate command:

```python
@loader.command()
async def cancel(self, mx, event: MessageEvent):
    """cancel survey"""
    state = FSMContext(mx.fsm, event)
    await state.clear()
    await utils.answer(mx, "Cancelled")
```

## Can steps be validated through payload

Yes.

And this is exactly the right way.

Now the callback can itself validate payload for `@loader.state(...)`.

This means:

- number is checked as number;
- empty string is cut off by the model;
- invalid values do not turn into mess inside your function.

## What to write in the state function itself

Leave there only the meaning of the scenario.

Good:

```python
await state.update_data(age=payload.age)
await state.set_state(SurveyStates.confirm)
await event.reply("Confirm?")
```

Bad:

```python
text = event.content.body.strip()
if not text:
    ...
try:
    age = int(text)
except:
    ...
```

Because this is already the work of the payload model.

## Live example

Look:

- [state_management_example.py](../../test_modules/state_management_example.py)

There it is shown:

- how to start the scenario;
- how to accept payload at each step;
- how to move between states;
- how to finish the dialog.

## What to look at next

- [Main page of the section](../README.md)
- [ConfigValue](../ConfigValue/README.md)
- [on](../on/README.md)
