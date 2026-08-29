"""Фильтры событий.

Фильтр — вызываемый объект ``(client, update) -> bool``; комбинируется через
``&``, ``|`` и ``~``. Пишутся так::

    @app.on_message(filters.command("start") & filters.private)
    async def start(client, message):
        await message.reply("привет")
"""

from __future__ import annotations

import inspect
import re
from typing import Any, Callable

from .enums import ChatType


class Filter:
    """Базовый фильтр с логическими операциями."""

    def __init__(self, func: Callable[..., Any], name: str | None = None):
        self.func = func
        self.name = name or getattr(func, "__name__", "filter")

    async def __call__(self, client, update) -> bool:
        result = self.func(client, update)
        if inspect.isawaitable(result):
            result = await result
        return bool(result)

    def __and__(self, other: "Filter") -> "Filter":
        async def check(client, update):
            return await self(client, update) and await other(client, update)

        return Filter(check, f"({self.name} & {other.name})")

    def __or__(self, other: "Filter") -> "Filter":
        async def check(client, update):
            return await self(client, update) or await other(client, update)

        return Filter(check, f"({self.name} | {other.name})")

    def __invert__(self) -> "Filter":
        async def check(client, update):
            return not await self(client, update)

        return Filter(check, f"~{self.name}")

    def __repr__(self) -> str:
        return f"<Filter {self.name}>"


def create(func: Callable[..., Any], name: str | None = None) -> Filter:
    """Создаёт фильтр из произвольной функции."""
    return Filter(func, name)


def _simple(check: Callable[[Any], bool], name: str) -> Filter:
    return Filter(lambda _client, update: check(update), name)


# --- по содержимому --------------------------------------------------------

#: Сообщение с непустым текстом.
text = _simple(lambda m: bool(getattr(m, "text", "")), "text")

#: Есть любое вложение.
media = _simple(lambda m: getattr(m, "media", None) is not None, "media")

photo = _simple(lambda m: getattr(m, "photo", None) is not None, "photo")
video = _simple(lambda m: getattr(m, "video", None) is not None, "video")
audio = _simple(lambda m: getattr(m, "audio", None) is not None, "audio")
document = _simple(lambda m: getattr(m, "document", None) is not None, "document")
sticker = _simple(lambda m: getattr(m, "sticker", None) is not None, "sticker")
location = _simple(lambda m: getattr(m, "location", None) is not None, "location")
poll = _simple(lambda m: getattr(m, "poll", None) is not None, "poll")

#: Ответ на другое сообщение.
reply = _simple(lambda m: getattr(m, "reply_to_message_id", None) is not None, "reply")

#: Пересланное сообщение.
forwarded = _simple(
    lambda m: getattr(m, "forward_from_message", None) is not None, "forwarded"
)


# --- по направлению и типу чата -------------------------------------------

#: Входящие (не свои) сообщения.
incoming = _simple(lambda m: not getattr(m, "outgoing", False), "incoming")

#: Свои сообщения.
outgoing = _simple(lambda m: bool(getattr(m, "outgoing", False)), "outgoing")

#: Синоним ``outgoing``: сообщения от своего имени.
me = Filter(outgoing.func, "me")


def _chat_type(update) -> ChatType | None:
    chat = getattr(update, "chat", None)
    return chat.type if chat is not None else None


private = _simple(lambda m: _chat_type(m) is ChatType.PRIVATE, "private")
group = _simple(lambda m: _chat_type(m) is ChatType.GROUP, "group")
channel = _simple(lambda m: _chat_type(m) is ChatType.CHANNEL, "channel")


# --- параметризованные ------------------------------------------------------


def command(
    commands: str | list[str], prefixes: str | list[str] = "/", *, case_sensitive: bool = False
) -> Filter:
    """Команда в начале сообщения: ``/start``, ``!help``.

    Совпавшая команда и её аргументы кладутся списком в ``message.command``.
    """
    if isinstance(commands, str):
        commands = [commands]
    if isinstance(prefixes, str):
        prefixes = list(prefixes)
    wanted = {c if case_sensitive else c.lower() for c in commands}

    def check(_client, update) -> bool:
        body = (getattr(update, "text", "") or "").strip()
        if not body or not any(body.startswith(p) for p in prefixes):
            return False
        parts = body[1:].split()
        if not parts:
            return False
        head = parts[0].split("@")[0]
        if (head if case_sensitive else head.lower()) not in wanted:
            return False
        try:
            update.command = [head, *parts[1:]]
        except AttributeError:  # объект со слотами
            pass
        return True

    return Filter(check, f"command({'/'.join(sorted(wanted))})")


def regex(pattern: str | re.Pattern[str], flags: int = 0) -> Filter:
    """Регулярное выражение по тексту; совпадение кладётся в ``message.matches``."""
    compiled = re.compile(pattern, flags) if isinstance(pattern, str) else pattern

    def check(_client, update) -> bool:
        body = getattr(update, "text", "") or ""
        matches = list(compiled.finditer(body))
        if matches:
            try:
                update.matches = matches
            except AttributeError:
                pass
        return bool(matches)

    return Filter(check, f"regex({compiled.pattern!r})")


def user(users: int | str | list[int | str]) -> Filter:
    """Автор входит в список (id или @имя)."""
    if not isinstance(users, list):
        users = [users]
    ids = {u for u in users if isinstance(u, int)}
    names = {str(u).lstrip("@").lower() for u in users if not isinstance(u, int)}

    def check(_client, update) -> bool:
        author = getattr(update, "from_user", None)
        if author is None:
            return False
        if author.id in ids:
            return True
        return bool(author.username and author.username.lower() in names)

    return Filter(check, f"user({sorted(ids)})")


def chat(chats: int | str | list[int | str]) -> Filter:
    """Событие произошло в одном из чатов."""
    if not isinstance(chats, list):
        chats = [chats]
    ids = {c for c in chats if isinstance(c, int)}
    names = {str(c).lstrip("@").lower() for c in chats if not isinstance(c, int)}

    def check(_client, update) -> bool:
        where = getattr(update, "chat", None)
        if where is None:
            return False
        if where.id in ids:
            return True
        return bool(where.username and where.username.lower() in names)

    return Filter(check, f"chat({sorted(ids)})")


#: Пропускает всё.
all = Filter(lambda _c, _u: True, "all")


__all__ = [
    "Filter",
    "create",
    "text",
    "media",
    "photo",
    "video",
    "audio",
    "document",
    "sticker",
    "location",
    "poll",
    "reply",
    "forwarded",
    "incoming",
    "outgoing",
    "me",
    "private",
    "group",
    "channel",
    "command",
    "regex",
    "user",
    "chat",
    "all",
]
