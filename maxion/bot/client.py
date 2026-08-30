"""Bot — клиент официального Bot API MAX (botapi.max.ru).

REST поверх HTTP: токен бота в заголовке ``Authorization`` (и, для
совместимости, в query ``access_token``), тело и ответы — JSON. Обновления —
long polling ``GET /updates`` либо webhook-подписки.

Это отдельный от userbot слой: userbot говорит бинарным протоколом с
``oneme.ru`` от лица аккаунта, а :class:`Bot` — документированный REST от лица
бота. Общего транспорта у них нет, поэтому классы независимы.

    from maxion.bot import Bot, filters

    bot = Bot("<token>")

    @bot.on_message(filters.command("start"))
    async def start(bot, update):
        await update.reply("привет")

    bot.run()
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable, Sequence

from .types import BotCommand, Chat, Message, User
from .updates import Update, parse_update

log = logging.getLogger(__name__)

BASE_URL = "https://botapi.max.ru"

Handler = Callable[..., Awaitable[Any]]


class BotApiError(Exception):
    """Ошибка Bot API: неуспешный HTTP-код или тело с ``code``/``message``."""

    def __init__(self, status: int, payload: Any):
        self.status = status
        self.payload = payload
        code = payload.get("code") if isinstance(payload, dict) else None
        message = payload.get("message") if isinstance(payload, dict) else payload
        super().__init__(f"[{status}{'/' + str(code) if code else ''}] {message}")


class _Registration:
    __slots__ = ("event", "handler", "filters")

    def __init__(self, event: str, handler: Handler, filters):
        self.event = event
        self.handler = handler
        self.filters = filters

    async def matches(self, bot, update) -> bool:
        for f in self.filters:
            if not await _call_filter(f, bot, update):
                return False
        return True


class Bot:
    """Клиент Bot API MAX."""

    def __init__(
        self,
        token: str,
        *,
        base_url: str = BASE_URL,
        timeout: float = 40.0,
    ):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session: Any = None
        self._handlers: list[_Registration] = []
        self._polling = False
        self._marker: int | None = None
        self.me: User | None = None

    # --- HTTP --------------------------------------------------------------

    async def _http(self):
        if self._session is None:
            try:
                import aiohttp
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("нужен aiohttp") from exc
            self._session = aiohttp.ClientSession(
                headers={"Authorization": self.token},
                timeout=aiohttp.ClientTimeout(total=self.timeout + 20),
            )
        return self._session

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        """Низкоуровневый вызов Bot API."""
        session = await self._http()
        query = {"access_token": self.token}
        if params:
            query.update({k: v for k, v in params.items() if v is not None})
        url = f"{self.base_url}{path}"
        async with session.request(method, url, params=query, json=json) as resp:
            try:
                payload = await resp.json(content_type=None)
            except Exception:
                payload = await resp.text()
            if resp.status >= 400:
                raise BotApiError(resp.status, payload)
            return payload

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    # --- бот ---------------------------------------------------------------

    async def get_me(self) -> User:
        """GET /me."""
        self.me = User(await self.request("GET", "/me"), self)
        return self.me

    async def set_commands(self, commands: Sequence[dict[str, str]]) -> dict[str, Any]:
        """PATCH /me с меню команд ``[{name, description}]``."""
        return await self.request("PATCH", "/me", json={"commands": list(commands)})

    async def set_my_info(self, **fields: Any) -> User:
        """PATCH /me — имя, описание, команды бота."""
        return User(await self.request("PATCH", "/me", json=clean(fields)), self)

    # --- сообщения ---------------------------------------------------------

    async def send_message(
        self,
        text: str = "",
        *,
        chat_id: int | None = None,
        user_id: int | None = None,
        attachments: Sequence[dict[str, Any]] | None = None,
        reply_to: str | None = None,
        format: str | None = None,
        notify: bool = True,
        disable_link_preview: bool = False,
        **extra: Any,
    ) -> Message:
        """POST /messages. Адресат — ``chat_id`` или ``user_id``."""
        body: dict[str, Any] = {"text": text, "notify": notify}
        if attachments:
            body["attachments"] = list(attachments)
        if format:
            body["format"] = format
        if disable_link_preview:
            body["disable_link_preview"] = True
        if reply_to:
            body["link"] = {"type": "reply", "mid": reply_to}
        body.update(extra)
        payload = await self.request(
            "POST",
            "/messages",
            params={"chat_id": chat_id, "user_id": user_id},
            json=body,
        )
        # ответ: {"message": {...}}
        raw = payload.get("message", payload) if isinstance(payload, dict) else {}
        return Message(raw, self)

    async def edit_message(
        self,
        message_id: str,
        text: str = "",
        *,
        attachments: Sequence[dict[str, Any]] | None = None,
        format: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """PUT /messages?message_id=…"""
        body = clean({"text": text, "attachments": list(attachments) if attachments else None,
                      "format": format, **extra})
        return await self.request(
            "PUT", "/messages", params={"message_id": message_id}, json=body
        )

    async def delete_message(self, message_id: str) -> dict[str, Any]:
        """DELETE /messages?message_id=…"""
        return await self.request("DELETE", "/messages", params={"message_id": message_id})

    async def get_message(self, message_id: str) -> Message:
        """GET /messages/{messageId}."""
        return Message(await self.request("GET", f"/messages/{message_id}"), self)

    async def get_messages(
        self, chat_id: int, *, count: int = 50, **extra: Any
    ) -> list[Message]:
        """GET /messages."""
        payload = await self.request(
            "GET", "/messages", params={"chat_id": chat_id, "count": count, **extra}
        )
        raw = payload.get("messages", []) if isinstance(payload, dict) else []
        return [Message(m, self) for m in raw]

    async def answer_callback(
        self,
        callback_id: str,
        *,
        text: str | None = None,
        notification: str | None = None,
        attachments: Sequence[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """POST /answers — ответ на нажатие inline-кнопки."""
        message = None
        if text is not None or attachments is not None:
            message = clean({"text": text, "attachments":
                             list(attachments) if attachments else None})
        return await self.request(
            "POST",
            "/answers",
            params={"callback_id": callback_id},
            json=clean({"message": message, "notification": notification}),
        )

    # --- чаты --------------------------------------------------------------

    async def get_chats(self, *, count: int = 50, marker: int | None = None) -> list[Chat]:
        """GET /chats."""
        payload = await self.request(
            "GET", "/chats", params={"count": count, "marker": marker}
        )
        raw = payload.get("chats", []) if isinstance(payload, dict) else []
        return [Chat(c, self) for c in raw]

    async def get_chat(self, chat_id: int) -> Chat:
        """GET /chats/{chatId}."""
        return Chat(await self.request("GET", f"/chats/{chat_id}"), self)

    async def edit_chat(self, chat_id: int, **fields: Any) -> Chat:
        """PATCH /chats/{chatId} — title, icon, pin и т.п."""
        return Chat(await self.request("PATCH", f"/chats/{chat_id}", json=clean(fields)), self)

    async def send_action(self, chat_id: int, action: str = "typing_on") -> dict[str, Any]:
        """POST /chats/{chatId}/actions — например ``typing_on``."""
        return await self.request("POST", f"/chats/{chat_id}/actions", json={"action": action})

    async def leave_chat(self, chat_id: int) -> dict[str, Any]:
        """DELETE /chats/{chatId}/members/me."""
        return await self.request("DELETE", f"/chats/{chat_id}/members/me")

    async def get_pinned_message(self, chat_id: int) -> Message | None:
        """GET /chats/{chatId}/pin."""
        payload = await self.request("GET", f"/chats/{chat_id}/pin")
        raw = payload.get("message") if isinstance(payload, dict) else None
        return Message(raw, self) if raw else None

    async def pin_message(
        self, chat_id: int, message_id: str, *, notify: bool = True
    ) -> dict[str, Any]:
        """PUT /chats/{chatId}/pin."""
        return await self.request(
            "PUT", f"/chats/{chat_id}/pin", json={"message_id": message_id, "notify": notify}
        )

    async def unpin_message(self, chat_id: int) -> dict[str, Any]:
        """DELETE /chats/{chatId}/pin."""
        return await self.request("DELETE", f"/chats/{chat_id}/pin")

    async def get_members(
        self, chat_id: int, *, count: int = 50, marker: int | None = None
    ) -> list[User]:
        """GET /chats/{chatId}/members."""
        payload = await self.request(
            "GET", f"/chats/{chat_id}/members", params={"count": count, "marker": marker}
        )
        raw = payload.get("members", []) if isinstance(payload, dict) else []
        return [User(m, self) for m in raw]

    async def add_members(self, chat_id: int, user_ids: Sequence[int]) -> dict[str, Any]:
        """POST /chats/{chatId}/members."""
        return await self.request(
            "POST", f"/chats/{chat_id}/members", json={"user_ids": list(user_ids)}
        )

    async def remove_member(
        self, chat_id: int, user_id: int, *, block: bool = False
    ) -> dict[str, Any]:
        """DELETE /chats/{chatId}/members."""
        return await self.request(
            "DELETE", f"/chats/{chat_id}/members",
            params={"user_id": user_id, "block": block},
        )

    async def get_admins(self, chat_id: int) -> list[User]:
        """GET /chats/{chatId}/members/admins."""
        payload = await self.request("GET", f"/chats/{chat_id}/members/admins")
        raw = payload.get("members", []) if isinstance(payload, dict) else []
        return [User(m, self) for m in raw]

    # --- загрузка ----------------------------------------------------------

    async def get_upload_url(self, upload_type: str = "image") -> dict[str, Any]:
        """POST /uploads — URL для заливки файла (``image``/``video``/``audio``/``file``)."""
        return await self.request("POST", "/uploads", params={"type": upload_type})

    async def upload(self, path: str, upload_type: str = "image") -> dict[str, Any]:
        """Загружает файл и возвращает токен для ``attachments``."""
        import aiohttp

        info = await self.get_upload_url(upload_type)
        url = info.get("url")
        if not url:
            raise BotApiError(0, info)
        session = await self._http()
        with open(path, "rb") as fh:
            data = aiohttp.FormData()
            data.add_field("data", fh, filename=path.rsplit("/", 1)[-1])
            async with session.post(url, data=data) as resp:
                return await resp.json(content_type=None)

    # --- подписки (webhook) ------------------------------------------------

    async def get_subscriptions(self) -> list[dict[str, Any]]:
        """GET /subscriptions."""
        payload = await self.request("GET", "/subscriptions")
        return payload.get("subscriptions", []) if isinstance(payload, dict) else []

    async def subscribe(
        self, url: str, *, update_types: Sequence[str] | None = None, secret: str | None = None
    ) -> dict[str, Any]:
        """POST /subscriptions — включить webhook."""
        return await self.request(
            "POST", "/subscriptions",
            json=clean({"url": url, "update_types": list(update_types) if update_types else None,
                        "secret": secret}),
        )

    async def unsubscribe(self, url: str) -> dict[str, Any]:
        """DELETE /subscriptions."""
        return await self.request("DELETE", "/subscriptions", params={"url": url})

    # --- обновления: long polling ------------------------------------------

    async def get_updates(
        self,
        *,
        limit: int = 100,
        timeout: int = 30,
        marker: int | None = None,
        types: Sequence[str] | None = None,
    ) -> list[Update]:
        """GET /updates — одна порция обновлений (long polling)."""
        payload = await self.request(
            "GET", "/updates",
            params={
                "limit": limit,
                "timeout": timeout,
                "marker": marker if marker is not None else self._marker,
                "types": ",".join(types) if types else None,
            },
        )
        if isinstance(payload, dict):
            self._marker = payload.get("marker", self._marker)
            raw = payload.get("updates", [])
        else:
            raw = []
        return [parse_update(self, u) for u in raw]

    # --- обработчики -------------------------------------------------------

    def add_handler(self, event: str, handler: Handler, *filters) -> Handler:
        if not inspect.iscoroutinefunction(handler):
            raise TypeError("обработчик должен быть async")
        self._handlers.append(_Registration(event, handler, list(filters)))
        return handler

    def on(self, event: str = "raw", *filters):
        def deco(fn):
            self.add_handler(event, fn, *filters)
            return fn
        return deco

    def on_message(self, *filters):
        return self.on("message", *filters)

    def on_callback(self, *filters):
        return self.on("callback", *filters)

    def on_bot_started(self, *filters):
        return self.on("bot_started", *filters)

    def on_edited_message(self, *filters):
        return self.on("edited_message", *filters)

    def on_raw(self, *filters):
        return self.on("raw", *filters)

    async def _dispatch(self, update: Update) -> None:
        for reg in self._handlers:
            if reg.event not in (update.event, "raw"):
                continue
            try:
                if not await reg.matches(self, update):
                    continue
            except Exception:
                log.exception("ошибка в фильтре")
                continue
            asyncio.create_task(self._run(reg.handler, update))

    async def _run(self, handler: Handler, update: Update) -> None:
        try:
            await handler(self, update)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("ошибка в обработчике %s", getattr(handler, "__name__", handler))

    # --- запуск ------------------------------------------------------------

    async def polling(self, *, drop_pending: bool = False) -> None:
        """Бесконечный цикл long polling с раздачей обновлений обработчикам."""
        await self.get_me()
        if drop_pending:
            # маркер вперёд — пропустить накопленное
            await self.get_updates(limit=1, timeout=0)
        log.info("бот @%s: polling запущен", self.me.username if self.me else "?")
        self._polling = True
        try:
            while self._polling:
                try:
                    updates = await self.get_updates()
                except BotApiError as exc:
                    log.warning("Bot API: %s", exc)
                    await asyncio.sleep(3)
                    continue
                except Exception:
                    log.exception("ошибка при получении обновлений")
                    await asyncio.sleep(3)
                    continue
                for update in updates:
                    await self._dispatch(update)
        finally:
            self._polling = False

    def stop(self) -> None:
        self._polling = False

    def run(self, *, drop_pending: bool = False) -> None:
        """Блокирующий запуск — ``bot.run()``."""
        async def main():
            try:
                await self.polling(drop_pending=drop_pending)
            finally:
                await self.close()
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            pass

    async def __aenter__(self) -> "Bot":
        await self.get_me()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()

    def __repr__(self) -> str:
        return f"<Bot @{self.me.username if self.me else '?'}>"


def clean(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


async def _call_filter(f, bot, update) -> bool:
    result = f(bot, update)
    if inspect.isawaitable(result):
        result = await result
    return bool(result)


__all__ = ["Bot", "BotApiError"]
