"""Типы официального Bot API MAX (botapi.max.ru).

Тонкие обёртки над JSON REST-ответами: сырой словарь всегда в ``obj.raw``.
Схема — по документации dev.max.ru/docs-api.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from .client import Bot


class BotObject:
    """Общий предок: сырые данные + ссылка на клиент."""

    __slots__ = ("raw", "_bot")

    def __init__(self, raw: dict[str, Any] | None = None, bot: "Bot | None" = None):
        self.raw: dict[str, Any] = dict(raw or {})
        self._bot = bot

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)

    @property
    def bot(self) -> "Bot":
        if self._bot is None:
            raise RuntimeError("объект не привязан к боту")
        return self._bot

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.raw!r}>"


class User(BotObject):
    """Пользователь или бот."""

    @property
    def user_id(self) -> int | None:
        v = self.raw.get("user_id")
        return int(v) if v is not None else None

    @property
    def id(self) -> int | None:
        return self.user_id

    @property
    def name(self) -> str | None:
        return self.raw.get("name")

    @property
    def username(self) -> str | None:
        return self.raw.get("username")

    @property
    def is_bot(self) -> bool:
        return bool(self.raw.get("is_bot"))

    @property
    def last_activity_time(self) -> datetime | None:
        return _ts(self.raw.get("last_activity_time"))

    def __repr__(self) -> str:
        return f"<User id={self.user_id} name={self.name!r}>"


class Chat(BotObject):
    """Диалог, группа или канал."""

    @property
    def chat_id(self) -> int | None:
        v = self.raw.get("chat_id")
        return int(v) if v is not None else None

    @property
    def id(self) -> int | None:
        return self.chat_id

    @property
    def type(self) -> str | None:
        return self.raw.get("type")

    @property
    def status(self) -> str | None:
        return self.raw.get("status")

    @property
    def title(self) -> str | None:
        return self.raw.get("title")

    @property
    def members_count(self) -> int | None:
        v = self.raw.get("participants_count")
        return int(v) if v is not None else None

    @property
    def owner_id(self) -> int | None:
        v = self.raw.get("owner_id")
        return int(v) if v is not None else None

    async def send(self, text: str, **kwargs) -> "Message":
        return await self.bot.send_message(text, chat_id=self.chat_id, **kwargs)

    def __repr__(self) -> str:
        return f"<Chat id={self.chat_id} type={self.type} title={self.title!r}>"


class Recipient(BotObject):
    """Получатель сообщения — ``chat_id`` или ``user_id``."""

    @property
    def chat_id(self) -> int | None:
        v = self.raw.get("chat_id")
        return int(v) if v is not None else None

    @property
    def user_id(self) -> int | None:
        v = self.raw.get("user_id")
        return int(v) if v is not None else None

    @property
    def chat_type(self) -> str | None:
        return self.raw.get("chat_type")


class MessageBody(BotObject):
    """Тело сообщения: id, текст, вложения."""

    @property
    def mid(self) -> str | None:
        return self.raw.get("mid")

    @property
    def seq(self) -> int | None:
        v = self.raw.get("seq")
        return int(v) if v is not None else None

    @property
    def text(self) -> str:
        return self.raw.get("text") or ""

    @property
    def attachments(self) -> list[dict[str, Any]]:
        return [a for a in (self.raw.get("attachments") or []) if isinstance(a, dict)]


class Message(BotObject):
    """Сообщение Bot API."""

    @property
    def sender(self) -> User | None:
        raw = self.raw.get("sender")
        return User(raw, self._bot) if isinstance(raw, dict) else None

    @property
    def recipient(self) -> Recipient | None:
        raw = self.raw.get("recipient")
        return Recipient(raw, self._bot) if isinstance(raw, dict) else None

    @property
    def body(self) -> MessageBody:
        return MessageBody(self.raw.get("body") or {}, self._bot)

    @property
    def timestamp(self) -> datetime | None:
        return _ts(self.raw.get("timestamp"))

    # частые обращения напрямую
    @property
    def mid(self) -> str | None:
        return self.body.mid

    @property
    def text(self) -> str:
        return self.body.text

    @property
    def chat_id(self) -> int | None:
        r = self.recipient
        return r.chat_id if r else None

    @property
    def from_user(self) -> User | None:
        return self.sender

    @property
    def link(self) -> dict[str, Any] | None:
        """Блок ``link``: ответ или пересылка."""
        v = self.raw.get("link")
        return v if isinstance(v, dict) else None

    # --- действия ----------------------------------------------------------

    async def reply(self, text: str, **kwargs) -> "Message":
        return await self.bot.send_message(
            text, chat_id=self.chat_id, reply_to=self.mid, **kwargs
        )

    async def answer(self, text: str, **kwargs) -> "Message":
        return await self.bot.send_message(text, chat_id=self.chat_id, **kwargs)

    async def edit(self, text: str, **kwargs) -> dict[str, Any]:
        return await self.bot.edit_message(self.mid, text, **kwargs)

    async def delete(self) -> dict[str, Any]:
        return await self.bot.delete_message(self.mid)

    def __repr__(self) -> str:
        return f"<Message mid={self.mid} text={self.text[:40]!r}>"


class BotCommand(BotObject):
    """Команда бота из меню."""

    @property
    def name(self) -> str | None:
        return self.raw.get("name")

    @property
    def description(self) -> str | None:
        return self.raw.get("description")


def _ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None
    seconds = v / 1000 if v > 10_000_000_000 else v
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None


__all__ = ["BotObject", "User", "Chat", "Recipient", "MessageBody", "Message", "BotCommand"]
