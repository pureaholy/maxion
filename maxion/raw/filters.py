"""Фильтры для обработчиков событий.

Фильтр — это вызываемый объект ``(update) -> bool`` (можно и корутину).
Комбинируются через ``&``, ``|`` и ``~``.
"""

from __future__ import annotations

import inspect
import re
from typing import Any, Awaitable, Callable, Iterable

from .events import NewMessage, Update

FilterFunc = Callable[[Update], bool | Awaitable[bool]]


class Filter:
    """Обёртка вокруг предиката с поддержкой логических операций."""

    def __init__(self, func: FilterFunc, name: str | None = None):
        self.func = func
        self.name = name or getattr(func, "__name__", "filter")

    async def __call__(self, update: Update) -> bool:
        result = self.func(update)
        if inspect.isawaitable(result):
            result = await result
        return bool(result)

    def __and__(self, other: "Filter | FilterFunc") -> "Filter":
        other = _wrap(other)

        async def _and(update: Update) -> bool:
            return await self(update) and await other(update)

        return Filter(_and, f"({self.name} & {other.name})")

    def __or__(self, other: "Filter | FilterFunc") -> "Filter":
        other = _wrap(other)

        async def _or(update: Update) -> bool:
            return await self(update) or await other(update)

        return Filter(_or, f"({self.name} | {other.name})")

    def __invert__(self) -> "Filter":
        async def _not(update: Update) -> bool:
            return not await self(update)

        return Filter(_not, f"~{self.name}")

    def __repr__(self) -> str:
        return f"<Filter {self.name}>"


def _wrap(value: "Filter | FilterFunc") -> Filter:
    return value if isinstance(value, Filter) else Filter(value)


# --- готовые фильтры -------------------------------------------------------


def text(value: str, *, ignore_case: bool = True) -> Filter:
    """Точное совпадение текста сообщения."""

    def check(update: Update) -> bool:
        body = getattr(update, "text", "") or ""
        return body.lower() == value.lower() if ignore_case else body == value

    return Filter(check, f"text({value!r})")


def contains(value: str, *, ignore_case: bool = True) -> Filter:
    """Подстрока в тексте."""

    def check(update: Update) -> bool:
        body = getattr(update, "text", "") or ""
        return value.lower() in body.lower() if ignore_case else value in body

    return Filter(check, f"contains({value!r})")


def regex(pattern: str | re.Pattern[str]) -> Filter:
    """Совпадение по регулярному выражению."""
    compiled = re.compile(pattern) if isinstance(pattern, str) else pattern

    def check(update: Update) -> bool:
        return bool(compiled.search(getattr(update, "text", "") or ""))

    return Filter(check, f"regex({compiled.pattern!r})")


def command(*names: str, prefixes: str = "/!") -> Filter:
    """Команда вида ``/start`` в начале сообщения."""
    wanted = {n.lstrip("/!").lower() for n in names}

    def check(update: Update) -> bool:
        body = (getattr(update, "text", "") or "").strip()
        if not body or body[0] not in prefixes:
            return False
        head = body[1:].split(maxsplit=1)[0].split("@")[0].lower()
        return head in wanted if wanted else True

    return Filter(check, f"command({'/'.join(sorted(wanted))})")


def from_user(*user_ids: int) -> Filter:
    """Автор сообщения входит в список."""
    wanted = set(user_ids)

    def check(update: Update) -> bool:
        sender = getattr(update, "sender_id", None)
        return sender in wanted

    return Filter(check, f"from_user({sorted(wanted)})")


def in_chat(*chat_ids: int) -> Filter:
    """Событие произошло в одном из чатов."""
    wanted = set(chat_ids)

    def check(update: Update) -> bool:
        return update.chat_id in wanted

    return Filter(check, f"in_chat({sorted(wanted)})")


def has_attach(*types: str) -> Filter:
    """В сообщении есть вложение указанного типа."""
    wanted = {t.upper() for t in types}

    def check(update: Update) -> bool:
        if not isinstance(update, NewMessage):
            return False
        attaches = update.message.attaches
        if not wanted:
            return bool(attaches)
        return any(a.type in wanted for a in attaches)

    return Filter(check, f"has_attach({sorted(wanted)})")


def opcode(*codes: int) -> Filter:
    """Фильтр по номеру опкода — для сырых событий."""
    wanted = {int(c) for c in codes}
    return Filter(lambda u: u.opcode in wanted, f"opcode({sorted(wanted)})")


#: Только входящие сообщения (не свои).
incoming = Filter(lambda u: not getattr(u, "outgoing", False), "incoming")

#: Только собственные сообщения.
outgoing = Filter(lambda u: bool(getattr(u, "outgoing", False)), "outgoing")

#: Личная переписка.
private = Filter(
    lambda u: bool(u.chat_id is not None and u.chat_id > 0), "private"
)

#: Групповой чат или канал (у них отрицательные id).
group = Filter(lambda u: bool(u.chat_id is not None and u.chat_id < 0), "group")


def custom(func: FilterFunc, name: str | None = None) -> Filter:
    """Оборачивает произвольную функцию в фильтр."""
    return Filter(func, name)


def all_of(filters: Iterable[Filter | FilterFunc]) -> Filter:
    """Логическое И для списка фильтров."""
    items = [_wrap(f) for f in filters]

    async def check(update: Update) -> bool:
        for item in items:
            if not await item(update):
                return False
        return True

    return Filter(check, "all_of")


def any_of(filters: Iterable[Filter | FilterFunc]) -> Filter:
    """Логическое ИЛИ для списка фильтров."""
    items = [_wrap(f) for f in filters]

    async def check(update: Update) -> bool:
        for item in items:
            if await item(update):
                return True
        return False

    return Filter(check, "any_of")


__all__ = [
    "Filter",
    "text",
    "contains",
    "regex",
    "command",
    "from_user",
    "in_chat",
    "has_attach",
    "opcode",
    "incoming",
    "outgoing",
    "private",
    "group",
    "custom",
    "all_of",
    "any_of",
]
