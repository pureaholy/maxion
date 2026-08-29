"""Типы высокого уровня: User, Chat, Message, ChatMember, Dialog.

Это тонкие обёртки над разобранными моделями протокола: сырой payload всегда
доступен в ``obj.raw``, а низкоуровневая модель — в ``obj._raw``.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Sequence

from .enums import ChatMemberStatus, ChatType, MessageEntityType, UserStatus
from .raw.types import Chat as RawChat
from .raw.types import Member as RawMember
from .raw.types import Message as RawMessage
from .raw.types import User as RawUser

if TYPE_CHECKING:  # pragma: no cover
    from .client import Client


class Object:
    """Общий предок: хранит сырые данные и клиент."""

    __slots__ = ("_client", "_raw")

    def __init__(self, client: "Client | None", raw: Any):
        self._client = client
        self._raw = raw

    @property
    def raw(self) -> dict[str, Any]:
        """Сырой payload как пришёл от сервера."""
        return self._raw.raw if hasattr(self._raw, "raw") else dict(self._raw or {})

    @property
    def client(self) -> "Client":
        if self._client is None:
            raise RuntimeError("Объект не привязан к клиенту")
        return self._client

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.raw!r}>"


class User(Object):
    """Пользователь."""

    @property
    def id(self) -> int | None:
        return self._raw.id

    @property
    def first_name(self) -> str | None:
        return self._raw.first_name

    @property
    def last_name(self) -> str | None:
        return self._raw.last_name

    @property
    def full_name(self) -> str:
        return self._raw.name

    @property
    def username(self) -> str | None:
        """Короткая ссылка (@имя)."""
        return self._raw.link

    @property
    def phone_number(self) -> str | None:
        return self._raw.phone

    @property
    def is_bot(self) -> bool:
        return self._raw.is_bot

    @property
    def is_verified(self) -> bool:
        return self._raw.is_verified

    @property
    def is_self(self) -> bool:
        me = self._client.me if self._client else None
        return bool(me and me.id == self.id)

    @property
    def status(self) -> UserStatus | None:
        raw = self.raw.get("presence") or {}
        value = raw.get("status") or raw.get("on")
        if value in ("ONLINE", "ON"):
            return UserStatus.ONLINE
        return UserStatus.OFFLINE if value else None

    @property
    def photo_url(self) -> str | None:
        return self._raw.photo_url

    @property
    def mention(self) -> str:
        return f"@{self.username}" if self.username else self.full_name

    async def send_message(self, text: str, **kwargs) -> "Message":
        """Пишет пользователю в личку."""
        return await self.client.send_message(self.id, text, **kwargs)

    async def block(self) -> None:
        await self.client.block_user(self.id)

    async def unblock(self) -> None:
        await self.client.unblock_user(self.id)

    def __repr__(self) -> str:
        return f"<User id={self.id} name={self.full_name!r}>"


class Chat(Object):
    """Чат, диалог или канал."""

    @property
    def id(self) -> int | None:
        return self._raw.id

    @property
    def type(self) -> ChatType | None:
        return ChatType.from_raw(self._raw.type)

    @property
    def title(self) -> str | None:
        return self._raw.title

    @property
    def username(self) -> str | None:
        return self._raw.link

    @property
    def description(self) -> str | None:
        return self._raw.description

    @property
    def members_count(self) -> int | None:
        return self._raw.participants_count

    @property
    def is_verified(self) -> bool:
        return bool(self.raw.get("options", {}).get("VERIFIED"))

    @property
    def unread_count(self) -> int:
        return self._raw.new_messages

    async def send_message(self, text: str, **kwargs) -> "Message":
        return await self.client.send_message(self.id, text, **kwargs)

    async def leave(self) -> None:
        await self.client.leave_chat(self.id)

    async def get_member(self, user_id: int) -> "ChatMember | None":
        members = await self.client.get_chat_members(self.id, query=None, limit=200)
        for member in members:
            if member.user_id == user_id:
                return member
        return None

    async def set_title(self, title: str) -> None:
        await self.client.set_chat_title(self.id, title)

    def __repr__(self) -> str:
        return f"<Chat id={self.id} type={self.type} title={self.title!r}>"


class MessageEntity(Object):
    """Участок форматирования в тексте."""

    def __init__(self, client: "Client | None", raw: dict[str, Any]):
        super().__init__(client, raw)

    @property
    def type(self) -> MessageEntityType | None:
        return MessageEntityType.from_raw(self.raw.get("type"))

    @property
    def offset(self) -> int:
        return int(self.raw.get("from", 0))

    @property
    def length(self) -> int:
        return int(self.raw.get("length", 0))

    @property
    def url(self) -> str | None:
        return self.raw.get("url")

    @property
    def user_id(self) -> int | None:
        value = self.raw.get("userId")
        return int(value) if value is not None else None


class Message(Object):
    """Сообщение."""

    @property
    def id(self) -> str | None:
        return self._raw.id

    @property
    def message_id(self) -> str | None:
        """Устаревший алиас :attr:`id`."""
        return self.id

    @property
    def date(self) -> datetime | None:
        return self._raw.time

    @property
    def text(self) -> str:
        return self._raw.text

    @property
    def caption(self) -> str | None:
        """Подпись к медиа — у MAX это тот же текст."""
        return self._raw.text if self.media else None

    @property
    def chat(self) -> Chat | None:
        chat_id = self._raw.chat_id
        if chat_id is None:
            return None
        cached = self.client._raw.chats_cache.get(chat_id) if self._client else None
        return Chat(self._client, cached or RawChat({"id": chat_id}))

    @property
    def from_user(self) -> User | None:
        user_id = self._raw.sender_id
        if user_id is None:
            return None
        cached = self.client._raw.contacts_cache.get(user_id) if self._client else None
        return User(self._client, cached or RawUser({"id": user_id}))

    @property
    def outgoing(self) -> bool:
        return self._raw.outgoing

    @property
    def entities(self) -> list[MessageEntity]:
        return [MessageEntity(self._client, e.to_dict()) for e in self._raw.elements]

    @property
    def reply_to_message_id(self) -> str | None:
        return self._raw.reply_to_id

    @property
    def reply_to_message(self) -> "Message | None":
        raw = self._raw.reply_to
        return Message(self._client, raw) if raw else None

    @property
    def forward_from_message(self) -> "Message | None":
        raw = self._raw.forwarded_from
        return Message(self._client, raw) if raw else None

    @property
    def media(self) -> str | None:
        """Тип первого вложения либо ``None``."""
        attaches = self._raw.attaches
        return attaches[0].type if attaches else None

    @property
    def photo(self):
        return self._attach("PHOTO")

    @property
    def video(self):
        return self._attach("VIDEO")

    @property
    def audio(self):
        return self._attach("AUDIO")

    @property
    def document(self):
        return self._attach("FILE")

    @property
    def sticker(self):
        return self._attach("STICKER")

    @property
    def location(self):
        return self._attach("LOCATION")

    @property
    def poll(self):
        return self._attach("POLL")

    def _attach(self, kind: str):
        for attach in self._raw.attaches:
            if attach.type == kind:
                return attach
        return None

    @property
    def views(self) -> int | None:
        return self._raw.views

    # --- действия ----------------------------------------------------------

    async def reply_text(self, text: str, *, quote: bool = True, **kwargs) -> "Message":
        """Отвечает на сообщение; короткий синоним — :meth:`reply`."""
        return await self.client.send_message(
            self._raw.chat_id,
            text,
            reply_to_message_id=self.id if quote else None,
            **kwargs,
        )

    reply = reply_text

    async def reply_photo(self, photo, caption: str = "", **kwargs) -> "Message":
        return await self.client.send_photo(
            self._raw.chat_id, photo, caption=caption, **kwargs
        )

    async def reply_document(self, document, caption: str = "", **kwargs) -> "Message":
        return await self.client.send_document(
            self._raw.chat_id, document, caption=caption, **kwargs
        )

    async def edit_text(self, text: str, **kwargs) -> "Message":
        return await self.client.edit_message_text(
            self._raw.chat_id, self.id, text, **kwargs
        )

    edit = edit_text

    async def delete(self, revoke: bool = True) -> None:
        await self.client.delete_messages(self._raw.chat_id, [self.id], revoke=revoke)

    async def forward(self, chat_id: int) -> "Message":
        results = await self.client.forward_messages(
            chat_id, self._raw.chat_id, [self.id]
        )
        return results[0]

    async def react(self, emoji: str = "❤️") -> Any:
        return await self.client.send_reaction(self._raw.chat_id, self.id, emoji)

    async def pin(self, *, disable_notification: bool = False) -> None:
        await self.client.pin_chat_message(
            self._raw.chat_id, self.id, disable_notification=disable_notification
        )

    async def read(self) -> None:
        await self.client.read_chat_history(self._raw.chat_id, self.id)

    async def download(self, file_name: str | None = None):
        return await self.client.download_media(self, file_name=file_name)

    def __repr__(self) -> str:
        preview = self.text[:40].replace("\n", " ")
        return f"<Message id={self.id} chat={self._raw.chat_id} text={preview!r}>"


class ChatMember(Object):
    """Участник чата."""

    @property
    def user_id(self) -> int | None:
        return self._raw.id

    @property
    def user(self) -> User | None:
        if self.user_id is None:
            return None
        cached = self.client._raw.contacts_cache.get(self.user_id) if self._client else None
        return User(self._client, cached or RawUser({"id": self.user_id}))

    @property
    def status(self) -> ChatMemberStatus:
        return ChatMemberStatus.from_raw(self._raw.type)

    @property
    def joined_date(self) -> datetime | None:
        return self._raw.joined_at

    @property
    def permissions(self) -> list[str]:
        return self._raw.permissions

    def __repr__(self) -> str:
        return f"<ChatMember id={self.user_id} status={self.status}>"


class Dialog(Object):
    """Строка списка чатов."""

    @property
    def chat(self) -> Chat:
        return Chat(self._client, self._raw)

    @property
    def top_message(self) -> Message | None:
        raw = self._raw.last_message
        return Message(self._client, raw) if raw else None

    @property
    def unread_messages_count(self) -> int:
        return self._raw.new_messages

    @property
    def is_pinned(self) -> bool:
        return bool(self.raw.get("pinned"))

    def __repr__(self) -> str:
        return f"<Dialog chat={self._raw.id} unread={self.unread_messages_count}>"


def wrap_message(client: "Client", raw: RawMessage) -> Message:
    return Message(client, raw)


def wrap_chat(client: "Client", raw: RawChat) -> Chat:
    return Chat(client, raw)


def wrap_user(client: "Client", raw: RawUser) -> User:
    return User(client, raw)


def wrap_member(client: "Client", raw: RawMember) -> ChatMember:
    return ChatMember(client, raw)


def wrap_all(client: "Client", items: Sequence[Any], factory) -> list[Any]:
    return [factory(client, item) for item in items]


__all__ = [
    "Object",
    "User",
    "Chat",
    "Message",
    "MessageEntity",
    "ChatMember",
    "Dialog",
]
