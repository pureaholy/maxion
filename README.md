# maxion

Библиотека-клиент мессенджера **MAX** на Python. Покрывает всё сразу:

- **Userbot** — работа от лица обычного аккаунта: удобный `Client` (обработчики,
  фильтры, модели со связанными методами) поверх `maxion.raw` — все 153
  вызываемых опкода внутреннего протокола, сверенные с APK `ru.oneme.app`
  26.29.1.
- **Bot API** — официальные боты через REST `botapi.max.ru` (`maxion.bot`),
  токен бота, long polling и webhook.
- **Звонки** — аудио и видео на WebRTC (`maxion.calls`, extra `maxion[calls]`):
  сигнализация и медиа-инфраструктура сняты с живого звонка.

## Установка

```bash
pip install -e .
```

Зависимости: `websockets`, `aiohttp`, `msgpack`, `lz4`.

## Быстрый старт

```python
from maxion import Client, filters

app = Client("my_account", phone_number="+79991234567")

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply(f"Привет, **{message.from_user.full_name}**!")

app.run()
```

Токен и `deviceId` кладутся в `my_account.session` — второй запуск без SMS.

## Возможности

| | |
| --- | --- |
| клиент | `Client(name, phone_number=...)`, `start`/`stop`/`run`/`idle`, `async with`, `compose` |
| обработчики | `@app.on_message`, `on_edited_message`, `on_deleted_messages`, `on_raw_update`, `add_handler`, группы, `StopPropagation`/`ContinuePropagation` |
| фильтры | `text`, `command`, `regex`, `user`, `chat`, `private`, `group`, `channel`, `me`, `incoming`, `outgoing`, `photo`, `video`, `document`, `sticker`, `reply`, `forwarded`, `create` + операторы `& | ~` |
| типы | `Message`, `Chat`, `User`, `ChatMember`, `Dialog`, `MessageEntity` с связанными методами (`message.reply`, `.edit_text`, `.delete`, `.forward`, `.download`) |
| методы | `send_message`, `send_photo`, `send_video`, `send_document`, `edit_message_text`, `delete_messages`, `forward_messages`, `get_chat`, `get_chat_history`, `get_dialogs`, `get_users`, `get_chat_members`, `promote_chat_member`, `ban_chat_member`, `pin_chat_message`, `download_media`, `send_chat_action`, … |
| разметка | `ParseMode.MARKDOWN` (по умолчанию), `ParseMode.HTML`, `ParseMode.DISABLED` |
| звонки | `maxion.calls`: `Call.incoming(...).answer(microphone=True / camera=True)`, `parse_vcp`, `CallSession`, `OkRtcChannel` — аудио и видео на WebRTC |
| ошибки | `RPCError`, `FloodWait` (с `.value`), `Unauthorized`, `SessionPasswordNeeded` |

## Bot API (боты)

Кроме userbot-клиента, есть отдельный слой для **официальных ботов** —
`maxion.bot`. Работает по документированному REST `botapi.max.ru` с токеном
бота (у @MasterBot), номер телефона не нужен:

```python
from maxion.bot import Bot, filters

bot = Bot("<token>")

@bot.on_message(filters.command("start"))
async def start(bot, update):
    await update.reply("Привет! Я на maxion.")

@bot.on_callback(filters.payload("yes"))
async def yes(bot, update):
    await update.answer("Принято")

bot.run()
```

39 методов: `send_message`, `edit_message`, `get_chats`, `get_members`,
`add_members`, `pin_message`, `answer_callback`, `upload`, `set_commands`,
два способа получать обновления: **long polling** (`polling`/`run`) и
**webhook** — встроенный приёмник `run_webhook(...)` плюс `subscribe`/
`feed_update`. Обновления:
`message`, `callback`, `bot_started`, `bot_added`, `edited_message`,
`user_added` и др. Фильтры: `command`, `text`, `regex`, `payload`, `chat`,
`from_user` с операторами `& | ~`.

## Ниже уровнем

Любой опкод доступен напрямую, минуя высокий слой:

```python
await app.raw.get_stories_feed(count=30)
await app.raw.set_reactions_settings(chat_id, reaction_ids=["❤️"])
await app.invoke("CHAT_SUGGEST", {"folderId": 1})
```

## Профиль устройства

Сервер узнаёт клиента по объекту `userAgent` в SESSION_INIT (6), и от этого
зависит набор доступных методов: **в web-версии авторизация по номеру телефона
вырезана**, поэтому вход по SMS делается с профилем телефона.

```python
MaxClient.mobile("my.session")                     # как мобильное приложение
MaxClient.web("my.session")                        # как браузер
MaxClient("my.session", device="android")          # телефон на Android
MaxClient("my.session", device=Device.ios())       # телефон на iOS
MaxClient("my.session", device=Device.desktop())   # десктопное приложение
MaxClient("my.session")                            # браузер (по умолчанию)
MaxClient("my.session", transport="tcp")           # профиль телефона сам
```

Профиль настраивается по частям, а `user_agent=` кладётся поверх:

```python
MaxClient(
    "my.session",
    device=Device.android(device_name="Pixel 8", android_version="14"),
    user_agent={"timezone": "Asia/Tashkent", "locale": "uz"},
)
```

Мобильные и десктопные профили дополнительно шлют `clientSessionId` и
`mt_instanceid`. Если запросить код с браузерным профилем и сервер откажет,
`request_code` заменит ошибку на подсказку с готовым решением.

Профиль виден и в списке сессий (`client.get_sessions()`) — там будут
`device_name` и `app_version` отсюда.

Android-профиль **снят с APK** `ru.oneme.app` 26.29.1 (класс `Lhti;`, сборщик
`Liti;->a()`), поэтому набор полей у него другой, чем у браузера:

| поле | значение | откуда в клиенте |
| --- | --- | --- |
| `deviceType` | `ANDROID` | константа |
| `appVersion` | `26.29.1` | константа |
| `buildNumber` | `6808` | константа, int |
| `osVersion` | `Android 13` | `String.format("Android %s", Build.VERSION.RELEASE)` |
| `arch` | `arm64-v8a` | `Build.SUPPORTED_ABIS[0]`, иначе `UNKNOWN` |
| `deviceName` | `Xiaomi Redmi Note 12` | `MANUFACTURER + " " + MODEL` |
| `screen` | `xxhdpi 480dpi 1080x2400` | бакет плотности + dpi + ширина×высота |
| `pushDeviceType` | `GCM` | enum: `GCM`, `HUAWEI`, `RUSTORE` |
| `timezone` | `Europe/Moscow` | `TimeZone.getDefault().getID()` |

`headerUserAgent` мобильный клиент не шлёт вовсе — это поле только web-версии.
`screen` собирается из размеров: `Device.android(width=1440, height=3200, dpi=640)`.
Профили iOS и desktop дампом не подтверждены.

## Протокол

Один RPC в двух представлениях, оба реализованы:

| | web | приложение |
| --- | --- | --- |
| адрес | `wss://ws-api.oneme.ru/websocket` | `api.oneme.ru:443` (TLS) |
| кадр | JSON | `[ver:1][cmd:1][seq:2][opcode:2][cof:1][len:3][payload]` |
| payload | JSON | MsgPack, LZ4 при длине > 32 байт |
| `ver` | 11 | 10 |
| транспорт | `WebSocketTransport` | `TcpTransport` |

```python
MaxClient("my.session", transport="tcp")   # бинарный протокол приложения
```

`cmd`: `0` — запрос, `1` — ответ, `3` — ошибка. `seq` связывает запрос с ответом;
кадры с опкодами `NOTIF_*` приходят сами по себе и превращаются в события.

Кадры разбираются и собираются напрямую:

```python
from maxion.raw import Packet

p = Packet.from_bytes(raw)          # бинарный кадр приложения
p = Packet.from_json(text)          # JSON-кадр web-версии
raw = Packet(opcode=64, payload={...}, seq=1, ver=10).to_bytes()
```

## Что умеет клиент

**Все 153 вызываемых опкода обёрнуты именованными методами**, из них 144 — с
разобранными параметрами, а не `**payload`. Остальные 29 опкодов — события
`NOTIF_*`, для них не методы, а классы событий. Полнота держится тестами:
новый опкод без обёртки или обёртка без сигнатуры роняют сборку. Основное:

```python
# чаты
chats, marker = await client.get_chats(count=40)
async for chat in client.iter_chats(): ...
chat = await client.get_chat(chat_id)
await client.join_chat("https://max.ru/durov")
await client.create_chat([user_id], title="Тестовая")
await client.set_chat_title(chat_id, "Новое имя")
await client.mute_chat(chat_id)               # навсегда
await client.add_members(chat_id, [user_id])
await client.promote_members(chat_id, user_id)

# сообщения
msg = await client.send_message(chat_id, "**жирно**", markdown=True)
await msg.reply("ответ")
await msg.react("🔥")
await client.edit_message(chat_id, msg.id, "новый текст")
await client.delete_messages(chat_id, [msg.id])
await client.pin_message(chat_id, msg.id)
history = await client.get_history(chat_id, limit=200)
async for m in client.iter_history(chat_id, limit=1000): ...

# медиа
await client.send_photo(chat_id, "cat.jpg", "котик")
await client.send_file(chat_id, "report.pdf")
url = await client.get_file_url(chat_id, msg.id, file_id)
await client.download(url, "report.pdf")

# контакты
user = await client.get_contact_by_phone("+79991234567")
await client.block_user(user.id)
presence = await client.get_presence([user.id])

# профиль и безопасность
await client.update_profile(first_name="Артур", description="…")
await client.set_hidden(True)
for s in await client.get_sessions():
    print(s.device_name, s.ip, s.last_active)
```

Метода ещё нет в библиотеке — вызывается напрямую по имени или номеру:

```python
await client.call("CHAT_SUGGEST", {"count": 10})
await client.call(300, {"count": 10})
```

### Форматирование

```python
from maxion.raw import Text

await client.send_message(chat_id, Text("Привет, ")
    .bold("мир").text("! ")
    .link("документация", "https://max.ru")
    .mention("Артур", user_id))

await client.send_message(chat_id, "это **важно** и `код`", markdown=True)
```

### События

```python
from maxion.raw import Router, filters

router = Router()

@router.on_message(filters.group & filters.regex(r"(?i)привет"))
async def hello(update):
    await update.reply(f"и тебе привет, {update.message.sender_id}")

@router.on("chat")
async def chat_changed(update):
    print("чат изменился:", update.chat)

@router.on_raw(filters.opcode(155))          # любой опкод, даже неизвестный
async def raw(update):
    print(update.name, update.payload)

client.include_router(router)
```

События: `message`, `message_deleted`, `typing`, `mark`, `chat`, `contact`,
`presence`, `reactions`, `callback`, `location`, `folders`, `stories`, `profile`,
`config`, `attach`, `call`, `raw`.

Фильтры: `command`, `text`, `contains`, `regex`, `from_user`, `in_chat`,
`has_attach`, `opcode`, `incoming`, `outgoing`, `private`, `group`, `custom`
— комбинируются через `&`, `|`, `~`.

### Устойчивость

Пинг каждые 30 с, автопереподключение с нарастающей задержкой и повторным
логином по токену, обработка `RECONNECT` (3) от сервера. Отключается через
`MaxClient(..., auto_reconnect=False)`.

## Ошибки

```python
from maxion.raw import RpcError, FloodWaitError, TwoFactorRequired

try:
    await client.send_message(chat_id, "…")
except FloodWaitError as exc:
    await asyncio.sleep(exc.seconds)
except RpcError as exc:
    print(exc.code, exc.message)
```

`TwoFactorRequired` при входе обрабатывается автоматически, если передать
`password=` в `client.start()`.

## Откуда взяты опкоды и поля

Протокол не документирован публично, поэтому таблица опкодов и имена полей
payload сняты с самого клиента `ru.oneme.app` 26.29.1 (versionCode 6808), а
кадрирование проверено побайтово на реальном пакете. Полнота покрытия и
совпадение имён держатся тестами: обёртка без сигнатуры или опкод без метода
роняют сборку.

Где данных не нашлось, об этом честно написано в докстроке метода, а не
придуманы правдоподобные имена параметров.

## Примеры

```bash
python examples/maxion_bot.py                     # userbot: команды, фильтры, связанные методы
python examples/echo_bot.py +79991234567          # userbot: /ping, /id, /echo, реакции
python examples/bot_echo.py <TOKEN>               # официальный бот на Bot API
python examples/answer_call.py                    # приём входящего звонка (maxion[calls])
python examples/dump_account.py --history <chat>  # выгрузка чатов, контактов, сессий, истории
python examples/send_media.py <chat> cat.jpg      # отправка медиа и скачивание вложений
python examples/stories_feed.py --details --view  # лента историй: посмотреть и отметить
```

`stories_feed.py` умеет складывать сырые ответы в JSONL (`--dump`) — их сразу
можно скормить `tools/infer_schema.py` и уточнить схемы тех опкодов, у которых
поля пока выведены по соглашениям.

## Структура

```
maxion/
  client.py       userbot Client, types, filters, handlers, parser
  raw/            низкий слой протокола
    protocol.py     кадрирование обоих транспортов
    opcodes.py      все 182 опкода
    client.py       соединение, RPC, диспетчеризация, реконнект
    transport/      ws.py (JSON) и tcp.py (MsgPack+LZ4)
    methods/        обёртки опкодов по доменам
    types/          модели: Chat, Message, User, Attach, …
    events.py       NOTIF_* → типизированные события
  bot/            официальный Bot API: Bot, updates, filters, types
  calls/          звонки: signaling, okrtc, session (aiortc), Call
```

## Тесты

```bash
pytest -q
```
