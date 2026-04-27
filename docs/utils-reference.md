# Справочник по `core/utils.py`

Источник: `src/mxuserbot/core/utils.py`.

Ниже перечислены все публичные функции файла и их текущее поведение.


## Что помнить на практике

- `answer()` по умолчанию редактирует текущую команду.
- Для новых модулей аргументы лучше разбирать через Pydantic payload, а не через `get_args()`.
- `get_args_raw()` и `get_args()` остаются как legacy-helper и умеют подтягивать текст из reply.
- `request()` возвращает `None` при ошибке, поэтому всегда проверяй ответ.
- `send_image()` — более "строгий" helper: если данных нет, он кидает исключение.

## Общие helpers

### `get_platform() -> str`

- Назначение: собирает краткую информацию о системе.
- Аргументы: нет.
- Возвращает: HTML-строку с hostname, ОС, RAM и загрузкой CPU.
- Типичный сценарий: команда `info`, `status`, `ping`, отладочные модули.
- Caveats:
  - строка уже содержит HTML-теги и backticks;
  - это sync helper.

### `get_commands(cls) -> dict`

- Назначение: ищет у класса методы, помеченные `@loader.command()`.
- Аргументы:
  - `cls` — класс модуля.
- Возвращает: словарь `{command_name: function}`.
- Типичный сценарий: используется loader-ом и `@loader.tds`.
- Caveats:
  - ищет только методы с `is_command = True`;
  - обычно вызывать вручную не нужно.

## Работа с reply и аргументами



### `await get_reply_text(mx, event) -> str | None | bool`

- Назначение: достает текст из reply, включая попытку автодешифровки.
- Аргументы:
  - `mx` — `MXBotInterface`;
  - `event` — исходный `MessageEvent`.
- Возвращает:
  - `False`, если сообщение не является reply;
  - `None`, если текст получить не удалось;
  - `str`, если текст найден.
- Типичный сценарий: команды вида `.tr en` или `.quote`, где текст можно брать из reply.
- Caveats:
  - при ошибке скачивания reply helper сам отвечает в чат;
  - важно различать `False` и `None`.

### `await get_args_raw(mx, event) -> str`

- Назначение: достает аргументы команды как "сырой" текст.
- Аргументы:
  - `mx` — `MXBotInterface`;
  - `event` — `MessageEvent` или строка.
- Возвращает: строку аргументов после имени команды.
- Типичный сценарий: API, где важна оригинальная строка без разбивки на токены.
- Caveats:
  - если аргументов мало или нет, helper может подтянуть текст из reply;
  - при reply умеет склеить явные аргументы и текст сообщения, на которое ответили;
  - не показывает ошибки пользователю, если не смог разобрать reply.
  - в новых community-модулях лучше сначала рассматривать Pydantic payload.

### `await get_args(mx, event) -> list`

- Назначение: достает аргументы команды в виде списка.
- Аргументы:
  - `mx` — `MXBotInterface`;
  - `event` — `MessageEvent`.
- Возвращает: список токенов.
- Типичный сценарий: команды вида `.cfg module key value`.
- Caveats:
  - сначала использует `get_args_raw()`;
  - парсит строку через `shlex.split()`, поэтому понимает кавычки;
  - при ошибке парсинга молча откатывается к простому `split()`.
  - helper полезен для старого кода и миграции, но не обязателен для новых команд.

## Отправка сообщений и медиа

### `await answer(mx, text, html=True, room_id=None, event=None, edit_id=-1, **kwargs) -> str`

- Назначение: отправляет текстовое сообщение или редактирует существующее.
- Аргументы:
  - `mx` — `MXBotInterface`;
  - `text` — текст или HTML;
  - `html` — нужно ли считать текст HTML;
  - `room_id` — комната назначения;
  - `event` — исходный event, из которого можно взять `room_id` и `event_id`;
  - `edit_id` — ID события для редактирования.
- Возвращает: результат `mx.client.send_message(...)`, обычно event ID.
- Типичный сценарий: почти все команды.
- Caveats:
  - `edit_id=-1` означает "попробовать отредактировать текущую команду";
  - чтобы отправить новый message event вместо редактирования, передай `edit_id=None`;
  - из `**kwargs` пробрасываются только `timestamp` и `txn_id`.

### `await send_image(mx, room_id, url=None, file_bytes=None, info=None, file_name=None, caption=None, relates_to=None, html=True, **kwargs)`

- Назначение: отправляет картинку по URL, `mxc://` или уже готовым bytes.
- Аргументы:
  - `mx` — `MXBotInterface`;
  - `room_id` — строка room ID или `MessageEvent`;
  - `url` — HTTP URL, `mxc://...` или даже bytes;
  - `file_bytes` — бинарные данные картинки;
  - `info` — `ImageInfo`;
  - `file_name` — имя файла;
  - `caption` — подпись;
  - `relates_to` — Matrix relation;
  - `html` — считать ли caption HTML.
- Возвращает: результат `send_message_event(...)`.
- Типичный сценарий: отправка карточек, баннеров, картинок API или обложек.
- Caveats:
  - если комната зашифрована, helper сам использует `encrypt_attachment()`;
  - если `url` содержит bytes и `file_bytes` не передан, bytes будут использованы как тело файла;
  - при отсутствии байтов helper кидает `ValueError`;
  - предназначен именно для изображений.

## HTTP и RPC

### `await request(url, method="GET", return_type="json", params=None, headers=None, **kwargs) -> dict | str | bytes | aiohttp.ClientResponse | None`

- Назначение: универсальный HTTP helper поверх `aiohttp`.
- Аргументы:
  - `url` — адрес запроса;
  - `method` — HTTP метод;
  - `return_type` — `"json"`, `"text"`, `"bytes"` или любой другой маркер для возврата самого response;
  - `params` — query params;
  - `headers` — заголовки;
  - `**kwargs` — дополнительные аргументы `session.request()`.
- Возвращает:
  - `dict`, `str`, `bytes`, `aiohttp.ClientResponse` или `None`.
- Типичный сценарий: обращение к внешним API из community-модулей.
- Caveats:
  - на любой ошибке возвращает `None`, а не кидает исключение;
  - создает новую `ClientSession` на каждый вызов;
  - ветка с возвратом "сырого" `aiohttp.ClientResponse` сейчас не очень полезна: объект возвращается уже после выхода из `async with`, то есть как стабильный публичный контракт на нее лучше не рассчитывать.

### `await set_rpc_media(mx, artist, album, track, length=None, complete=None, cover_art=None, player=None, streaming_link=None)`

- Назначение: ставит статус rich presence типа `m.rpc.media`.
- Аргументы:
  - `artist`, `album`, `track` — основные поля статуса;
  - `length`, `complete` — прогресс;
  - `cover_art` — `mxc://`, HTTP URL или bytes;
  - `player` — имя плеера;
  - `streaming_link` — внешняя ссылка.
- Возвращает: результат `mx.client.api.request(...)`.
- Типичный сценарий: музыкальные модули вроде Last.fm.
- Caveats:
  - если `cover_art` — URL или bytes, helper сам загрузит файл в Matrix media store;
  - требует доступа к profile endpoint текущего аккаунта.

### `await set_rpc_activity(mx, name, details=None, image=None)`

- Назначение: ставит статус rich presence типа `m.rpc.activity`.
- Аргументы:
  - `name` — основное название активности;
  - `details` — подробности;
  - `image` — ссылка на картинку.
- Возвращает: результат `mx.client.api.request(...)`.
- Типичный сценарий: idle-статус, произвольная activity-индикация.
- Caveats:
  - helper просто собирает payload и отправляет PUT-запрос.

### `await clear_rpc(mx)`

- Назначение: полностью удаляет RPC-статус из профиля.
- Аргументы:
  - `mx` — `MXBotInterface`.
- Возвращает: результат `mx.client.api.request(...)`.
- Типичный сценарий: остановка музыкального статуса или cleanup.
- Caveats:
  - удаляет весь namespace `RPC_NAMESPACE`, а не только одно поле.

## Экранирование и пути

### `escape_html(text) -> str`

- Назначение: экранирует `&`, `<`, `>`.
- Аргументы:
  - `text` — любая строка.
- Возвращает: безопасную HTML-строку.
- Типичный сценарий: вставка пользовательского ввода в `formatted_body`.
- Caveats:
  - не экранирует кавычки.

### `escape_quotes(text) -> str`

- Назначение: экранирует HTML-символы и двойные кавычки.
- Аргументы:
  - `text` — любая строка.
- Возвращает: строку, безопасную для HTML-атрибутов.
- Типичный сценарий: если строишь HTML вручную и подставляешь текст внутрь атрибутов.
- Caveats:
  - вызывает `escape_html()` внутри.

### `get_base_dir() -> str`

- Назначение: возвращает абсолютный путь к директории самого `utils.py`.
- Аргументы: нет.
- Возвращает: абсолютный путь.
- Типичный сценарий: редкий helper для поиска файлов рядом с модулем/ядром.
- Caveats:
  - почти всегда полезнее `get_dir(__file__)` в своем модуле.

### `get_dir(mod: str) -> str`

- Назначение: возвращает директорию произвольного файла/модуля.
- Аргументы:
  - `mod` — путь вроде `__file__`.
- Возвращает: абсолютный путь к директории.
- Типичный сценарий: поиск локальных ресурсов рядом с файлом модуля.
- Caveats:
  - helper ничего не проверяет: если передать странный путь, просто нормализует его через `os.path.abspath`.
