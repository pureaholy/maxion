"""Сообщения и связанные с ними сущности."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from ..enums import AttachType, MessageStatus, MessageType
from ..utils import Element, elements_from
from .attach import Attach
from .base import Model
from .user import User

if TYPE_CHECKING:  # pragma: no cover
    from .chat import Chat


class Reaction(Model):
    """Реакция на сообщение."""

    @property
    def type(self) -> str:
        return str(self.raw.get("reactionType") or self.raw.get("type") or "EMOJI")

    @property
    def id(self) -> str | None:
        return self._str("id", "emoji", "reaction")

    @property
    def count(self) -> int:
        return self._int("count") or 0

    def __repr__(self) -> str:
        return f"<Reaction {self.id!r} x{self.count}>"


class ReactionInfo(Model):
    """Сводка реакций сообщения."""

    @property
    def total(self) -> int:
        return self._int("totalCount", "total") or 0

    @property
    def counters(self) -> list[Reaction]:
        return Reaction.parse_list(self.raw.get("counters"), self._client)

    @property
    def my_reaction(self) -> Reaction | None:
        return Reaction.parse(self.raw.get("yourReaction"), self._client)


class Message(Model):
    """Сообщение чата."""

    # --- идентификаторы ----------------------------------------------------

    @property
    def id(self) -> str | None:
        value = self.raw.get("id")
        return str(value) if value is not None else None

    @property
    def chat_id(self) -> int | None:
        return self._int("chatId")

    @property
    def sender_id(self) -> int | None:
        return self._int("sender", "senderId", "userId")

    @property
    def cid(self) -> int | None:
        return self._int("cid")

    # --- содержимое --------------------------------------------------------

    @property
    def text(self) -> str:
        return str(self.raw.get("text") or "")

    @property
    def elements(self) -> list[Element]:
        return elements_from(self.raw.get("elements"))

    @property
    def attaches(self) -> list[Attach]:
        return Attach.wrap_list(self.raw.get("attaches") or self.raw.get("attachments"))

    @property
    def type(self) -> str | None:
        return self._str("type")

    @property
    def status(self) -> str | None:
        return self._str("status")

    @property
    def is_deleted(self) -> bool:
        return self.status == MessageStatus.REMOVED.value

    @property
    def is_edited(self) -> bool:
        return bool(self.raw.get("updateTime") or self.raw.get("edited"))

    @property
    def is_system(self) -> bool:
        return self.type == MessageType.SYSTEM.value or any(
            a.type == AttachType.CONTROL.value for a in self.attaches
        )

    @property
    def time(self) -> datetime | None:
        value = self._int("time")
        if not value:
            return None
        try:
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None

    @property
    def link(self) -> dict[str, Any] | None:
        """Блок ``link``: ответ, пересылка или комментарий."""
        value = self.raw.get("link")
        return value if isinstance(value, dict) else None

    @property
    def reply_to(self) -> "Message | None":
        link = self.link
        if link and link.get("type") == "REPLY":
            return Message.parse(link.get("message"), self._client)
        return None

    @property
    def reply_to_id(self) -> str | None:
        link = self.link
        if link and link.get("type") == "REPLY":
            value = link.get("messageId") or (link.get("message") or {}).get("id")
            return str(value) if value is not None else None
        return None

    @property
    def forwarded_from(self) -> "Message | None":
        link = self.link
        if link and link.get("type") == "FORWARD":
            return Message.parse(link.get("message"), self._client)
        return None

    @property
    def reactions(self) -> ReactionInfo | None:
        return ReactionInfo.parse(self.raw.get("reactionInfo"), self._client)

    @property
    def views(self) -> int | None:
        return self._int("views")

    @property
    def sender(self) -> User | None:
        """Автор, если клиент знает контакт из кеша."""
        if self._client is None or self.sender_id is None:
            return None
        return self._client.contacts_cache.get(self.sender_id)

    @property
    def outgoing(self) -> bool:
        return bool(
            self._client is not None
            and self._client.user_id is not None
            and self.sender_id == self._client.user_id
        )

    # --- действия ----------------------------------------------------------

    async def reply(self, text: str = "", **kwargs) -> "Message":
        """Отвечает на это сообщение."""
        return await self.client.send_message(
            self.chat_id, text, reply_to=self.id, **kwargs
        )

    async def answer(self, text: str = "", **kwargs) -> "Message":
        """Пишет в тот же чат без цитирования."""
        return await self.client.send_message(self.chat_id, text, **kwargs)

    async def edit(self, text: str = "", **kwargs) -> "Message":
        return await self.client.edit_message(self.chat_id, self.id, text, **kwargs)

    async def delete(self, for_me: bool = False) -> None:
        await self.client.delete_messages(self.chat_id, [self.id], for_me=for_me)

    async def forward(self, chat_id: int, **kwargs) -> "Message":
        return await self.client.forward_message(chat_id, self.chat_id, self.id, **kwargs)

    async def react(self, emoji: str = "❤️") -> ReactionInfo | None:
        return await self.client.set_reaction(self.chat_id, self.id, emoji)

    async def unreact(self) -> ReactionInfo | None:
        return await self.client.remove_reaction(self.chat_id, self.id)

    async def pin(self, notify: bool = True) -> "Chat | None":
        return await self.client.pin_message(self.chat_id, self.id, notify=notify)

    async def read(self) -> None:
        await self.client.read_message(self.chat_id, self.id)

    async def get_chat(self) -> "Chat | None":
        return await self.client.get_chat(self.chat_id)

    def __repr__(self) -> str:
        preview = self.text[:40].replace("\n", " ")
        return f"<Message id={self.id} chat={self.chat_id} text={preview!r}>"
