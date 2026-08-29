"""Роутер обработчиков событий."""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Iterable

from .events import Update
from .filters import Filter, _wrap

log = logging.getLogger(__name__)

Handler = Callable[..., Coroutine[Any, Any, Any]]


@dataclass(slots=True)
class Registration:
    """Один зарегистрированный обработчик."""

    event: str
    handler: Handler
    filters: list[Filter] = field(default_factory=list)

    async def matches(self, update: Update) -> bool:
        for check in self.filters:
            if not await check(update):
                return False
        return True


class Router:
    """Собирает обработчики и раздаёт им события.

    Пример::

        router = Router()

        @router.on_message(filters.command("ping"))
        async def ping(update):
            await update.reply("pong")

        client.include_router(router)
    """

    def __init__(self, name: str | None = None):
        self.name = name or "router"
        self.handlers: list[Registration] = []
        self.children: list["Router"] = []

    # --- регистрация -------------------------------------------------------

    def on(self, event: str = "raw", *filters: Filter | Callable) -> Callable[[Handler], Handler]:
        """Декоратор: подписка на событие по имени."""

        def decorator(handler: Handler) -> Handler:
            if not inspect.iscoroutinefunction(handler):
                raise TypeError("Обработчик должен быть async-функцией")
            self.handlers.append(
                Registration(event, handler, [_wrap(f) for f in filters])
            )
            return handler

        return decorator

    def on_message(self, *filters: Filter | Callable) -> Callable[[Handler], Handler]:
        """Новое сообщение (NOTIF_MESSAGE)."""
        return self.on("message", *filters)

    def on_edited(self, *filters: Filter | Callable) -> Callable[[Handler], Handler]:
        """Изменённое сообщение."""
        return self.on("edited_message", *filters)

    def on_deleted(self, *filters: Filter | Callable) -> Callable[[Handler], Handler]:
        return self.on("message_deleted", *filters)

    def on_typing(self, *filters: Filter | Callable) -> Callable[[Handler], Handler]:
        return self.on("typing", *filters)

    def on_chat(self, *filters: Filter | Callable) -> Callable[[Handler], Handler]:
        return self.on("chat", *filters)

    def on_presence(self, *filters: Filter | Callable) -> Callable[[Handler], Handler]:
        return self.on("presence", *filters)

    def on_reactions(self, *filters: Filter | Callable) -> Callable[[Handler], Handler]:
        return self.on("reactions", *filters)

    def on_callback(self, *filters: Filter | Callable) -> Callable[[Handler], Handler]:
        return self.on("callback", *filters)

    def on_raw(self, *filters: Filter | Callable) -> Callable[[Handler], Handler]:
        """Любой входящий кадр, включая неизвестные опкоды."""
        return self.on("raw", *filters)

    def include_router(self, router: "Router") -> "Router":
        self.children.append(router)
        return router

    # --- доставка ----------------------------------------------------------

    def collect(self, event: str) -> Iterable[Registration]:
        for registration in self.handlers:
            if registration.event in (event, "raw"):
                yield registration
        for child in self.children:
            yield from child.collect(event)

    async def feed(self, update: Update) -> int:
        """Вызывает подходящие обработчики. Возвращает их количество."""
        called = 0
        for registration in self.collect(update.event):
            try:
                if not await registration.matches(update):
                    continue
            except Exception:
                log.exception("Ошибка в фильтре обработчика %s", registration.handler)
                continue
            called += 1
            asyncio.create_task(self._run(registration.handler, update))
        return called

    @staticmethod
    async def _run(handler: Handler, update: Update) -> None:
        try:
            await handler(update)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Ошибка в обработчике %s", getattr(handler, "__name__", handler))

    def __repr__(self) -> str:
        return f"<Router {self.name} handlers={len(self.handlers)}>"
