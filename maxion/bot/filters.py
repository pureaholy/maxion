"""Фильтры обработчиков Bot API. Вызов ``(bot, update) -> bool``, операторы & | ~."""

from __future__ import annotations

import inspect
import re
from typing import Any, Callable


class Filter:
    def __init__(self, func: Callable[..., Any], name: str | None = None):
        self.func = func
        self.name = name or getattr(func, "__name__", "filter")

    async def __call__(self, bot, update) -> bool:
        r = self.func(bot, update)
        if inspect.isawaitable(r):
            r = await r
        return bool(r)

    def __and__(self, other: "Filter") -> "Filter":
        async def f(bot, u):
            return await self(bot, u) and await other(bot, u)
        return Filter(f, f"({self.name} & {other.name})")

    def __or__(self, other: "Filter") -> "Filter":
        async def f(bot, u):
            return await self(bot, u) or await other(bot, u)
        return Filter(f, f"({self.name} | {other.name})")

    def __invert__(self) -> "Filter":
        async def f(bot, u):
            return not await self(bot, u)
        return Filter(f, f"~{self.name}")


def _text(update) -> str:
    return getattr(update, "text", "") or ""


text = Filter(lambda b, u: bool(_text(u)), "text")


def command(*names: str, prefixes: str = "/") -> Filter:
    wanted = {n.lstrip("/").lower() for n in names}

    def check(bot, update) -> bool:
        body = _text(update).strip()
        if not body or body[0] not in prefixes:
            return False
        head = body[1:].split(maxsplit=1)[0].split("@")[0].lower()
        if wanted and head not in wanted:
            return False
        try:
            update.command = body[1:].split()
        except AttributeError:
            pass
        return True

    return Filter(check, f"command({'/'.join(sorted(wanted)) or '*'})")


def regex(pattern: str | re.Pattern[str]) -> Filter:
    rx = re.compile(pattern) if isinstance(pattern, str) else pattern

    def check(bot, update) -> bool:
        m = list(rx.finditer(_text(update)))
        if m:
            try:
                update.matches = m
            except AttributeError:
                pass
        return bool(m)

    return Filter(check, f"regex({rx.pattern!r})")


def payload(*values: str) -> Filter:
    """Callback с конкретным payload кнопки."""
    wanted = set(values)

    def check(bot, update) -> bool:
        p = getattr(update, "payload", None)
        return p in wanted if wanted else p is not None

    return Filter(check, f"payload({sorted(wanted)})")


def chat(*chat_ids: int) -> Filter:
    ids = set(chat_ids)
    return Filter(lambda b, u: getattr(u, "chat_id", None) in ids, f"chat({sorted(ids)})")


def from_user(*user_ids: int) -> Filter:
    ids = set(user_ids)

    def check(bot, update) -> bool:
        u = getattr(update, "message", None)
        sender = u.from_user if u and hasattr(u, "from_user") else getattr(update, "user", None)
        return bool(sender and sender.id in ids)

    return Filter(check, f"from_user({sorted(ids)})")


def create(func: Callable[..., Any], name: str | None = None) -> Filter:
    return Filter(func, name)


__all__ = ["Filter", "text", "command", "regex", "payload", "chat", "from_user", "create"]
