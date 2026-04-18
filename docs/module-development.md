



Для написания модуля вам нужно:

1. Естественно, уже установленный MxUserbot.
2. Создайте `.py` файл в папке `src/mxuserbot/modules/community`. Например, это будет: `test.py`

### Создание модулей:

1. Импортируйте обязательные модули:
```python
from ...core import loader, utils
```

2. Создайте `class Meta`:
```python
class Meta:
    name = "TestMoModule"
    _cls_doc = "Скидывает случайные изображения Астольфо с astolfo.rocks" 
    version = "1.1"
    tags = ["api"]
```
**Обязательно:** `name` / `_cls_doc` / `version` / `tags`
**Необязательно:** `dependencies` - зависимости. идет так: dependencies = ["pillow", "av", ...]

3. Создаём основной класс:
```python

@loader.tds # импортируем 
class TestModule(loader.Module):
    strings = {"error": "Ошибка при получении няшности"}

    config = {
        "limit": loader.ConfigValue(10, "Лимит запросов", lambda x: x > 0),
        "api_key": loader.ConfigValue("NONE", "Ключ доступа"),
        "silent": loader.ConfigValue(False, "Тихий режим")
    }
```

**Чуть подробнее:**
* При названии вашего класса ядро будет смотреть на название `Module` — это и будет основной модуль, что бот импортирует.
* `strings` обязателен. Указывайте туда значение `key: value` для текста. Если нет желания его заполнять — можно оставить пустым.
* `config` необязательно. Позволяет настраивать модули, если тот требует, например, ключ api, или настроить модуль. `key: ConfigValue(default, description, type)`.Для задействования , используйте loader.ConfigValue`.

После инициализации класса мы можем реализовать первую команду:

```python
    @loader.command()
    async def test(self, mx, event):
        """тест модуль для получения картинок"""
```

`@loader.command()` — так ядро понимает, что ваша функция — это команда. Вы можете изменить команду при помощи `name="miku"`, и вместо `test` Юзерботбот будет реагировать на команду `miku`.

При названии своей функции вам нужно учитывать, что юзербот по умолчанию считает название функции как за имя выполняемой команды.

Принимает функция три обязательных аргумента:
* `self` — сам класс 
* `mx` — интерфейс (ограниченный клиент)
* `event` — EventMessage от mautrix-python

Если вы используете функцию в качестве команды, то нужно обязательно указывать док-стринг, то есть после названия функции вы в кавычках описываете, зачем нужна эта функция, иначе модуль просто не загрузится.

```python
        api_url = "https://astolfo.rocks/api/images/random"
        data = await utils.request(api_url, params={"rating": "safe"})

        if not data:
            return await utils.answer(event, self.strings.get("error"))

        img_url = f"https://astolfo.rocks/astolfo/{data['id']}.{data['file_extension']}"

        image_bytes = await utils.request(img_url, return_type="bytes")

        await utils.send_image(mx, event, image_bytes, file_name=f"{data['id']}.jpg")
```

`utils` здесь в роли помощника для облегчения написания модулей. Разберем:
* `utils.request` — отправляет реквест запрос через aiohttp.
* `utils.answer` — отправляет сообщение в чат. Обязательно передать `mx`, вторым аргументом можно указать текст. Например, здесь мы берем текст из `strings`. Рекомендуется делать это через `.get`.
* `utils.send_image` — отправка изображения в чат. Обязательно `mx`/`event`, после чего или ссылку на изображение, или же `bytes`, `file_name` не обязателен.

Ваш модуль будет выглядеть примерно так:

```python
from ...core import loader, utils
from ...core.types import ConfigValue

class Meta:
    name = "TestMoModule"
    _cls_doc = "Скидывает случайные изображения Астольфо с astolfo.rocks" 
    version = "1.1"
    tags = ["api"]

@loader.tds
class TestModule(loader.Module):
    strings = {"error": "Ошибка при получении няшности"}

    config = {
        "limit": ConfigValue(10, "Лимит запросов", lambda x: x > 0),
        "api_key": ConfigValue("NONE", "Ключ доступа"),
        "silent": ConfigValue(False, "Тихий режим")
    }

    @loader.command()
    async def test(self, mx, event):
        """тест модуль для получения картинок"""
        api_url = "https://astolfo.rocks/api/images/random"
        data = await utils.request(api_url, params={"rating": "safe"})

        if not data:
            return await utils.answer(mx, self.strings.get("error"), event=event)

        img_url = f"https://astolfo.rocks/astolfo/{data['id']}.{data['file_extension']}"

        image_bytes = await utils.request(img_url, return_type="bytes")

        await utils.send_image(mx, event, image_bytes, file_name=f"{data['id']}.jpg")
```

Остальные доступные методы смотрите здесь: src/mxuserbot/core/utils.py
Если вам впадлу разбираться, я сгенерил utils доку через нейроку: [utils docs](utils-reference.md). Сорри. впадлу было описывать всё) 
