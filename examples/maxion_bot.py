"""Юзербот на maxion: обработчики, фильтры и связанные методы.

    python examples/maxion_bot.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maxion import Client, ContinuePropagation, enums, filters

app = Client("my_account", phone_number=None)  # номер спросит при первом входе


@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply(
        f"Привет, **{message.from_user.full_name}**!\n"
        f"Твой id: `{message.from_user.id}`"
    )


@app.on_message(filters.command("id"))
async def chat_id(client, message):
    await message.reply(
        f"chat_id: `{message.chat.id}`\n"
        f"тип: `{message.chat.type}`\n"
        f"message_id: `{message.id}`"
    )


@app.on_message(filters.command("html"))
async def html_demo(client, message):
    await message.reply(
        'Это <b>жирный</b>, <i>курсив</i> и <a href="https://max.ru">ссылка</a>',
        parse_mode=enums.ParseMode.HTML,
    )


@app.on_message(filters.regex(r"(?i)погода в (\w+)"))
async def weather(client, message):
    city = message.matches[0].group(1)
    await message.reply(f"За погодой в городе {city} — не ко мне 🙂")


@app.on_message(filters.text & filters.incoming, group=1)
async def log_everything(client, message):
    """Отдельная группа: срабатывает даже если сообщение уже обработали выше."""
    print(f"[{message.chat.id}] {message.from_user.full_name}: {message.text}")
    raise ContinuePropagation


@app.on_message(filters.photo)
async def save_photo(client, message):
    path = await message.download()
    await message.reply(f"Сохранил в `{path}`")


async def show_dialogs(client: Client) -> None:
    """Пример прямого вызова, без обработчиков."""
    async for dialog in client.get_dialogs(limit=10):
        unread = f" ({dialog.unread_messages_count})" if dialog.unread_messages_count else ""
        print(f"{dialog.chat.id:>18}  {dialog.chat.title or '—'}{unread}")


if __name__ == "__main__":
    app.run()
