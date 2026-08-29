"""Чаты, диалоги, каналы и их участники."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..enums import AccessType, ChatType, MemberType
from .base import Model
from .message import Message
from .user import User


class Member(Model):
    """Участник чата."""

    @property
    def id(self) -> int | None:
        return self._int("userId", "id", "contactId")

    @property
    def type(self) -> str:
        return str(self.raw.get("type") or MemberType.MEMBER.value)

    @property
    def is_admin(self) -> bool:
        return self.type in (MemberType.ADMIN.value, MemberType.OWNER.value) or bool(
            self.raw.get("permissions")
        )

    @property
    def is_owner(self) -> bool:
        return self.type == MemberType.OWNER.value or bool(self.raw.get("owner"))

    @property
    def permissions(self) -> list[str]:
        return [str(p) for p in (self.raw.get("permissions") or [])]

    @property
    def joined_at(self) -> datetime | None:
        return _ts(self._int("joinTime", "time"))

    @property
    def user(self) -> User | None:
        if self._client is None or self.id is None:
            return None
        return self._client.contacts_cache.get(self.id)


class Chat(Model):
    """Диалог, групповой чат или канал."""

    # --- поля --------------------------------------------------------------

    @property
    def id(self) -> int | None:
        return self._int("id", "chatId")

    @property
    def type(self) -> str | None:
        return self._str("type")

    @property
    def is_dialog(self) -> bool:
        return self.type == ChatType.DIALOG.value

    @property
    def is_channel(self) -> bool:
        return self.type == ChatType.CHANNEL.value

    @property
    def is_group(self) -> bool:
        return self.type == ChatType.CHAT.value

    @property
    def title(self) -> str | None:
        return self._str("title", "name")

    @property
    def description(self) -> str | None:
        return self._str("description")

    @property
    def link(self) -> str | None:
        return self._str("link")

    @property
    def owner_id(self) -> int | None:
        return self._int("owner", "ownerId")

    @property
    def participants(self) -> dict[int, int]:
        """``{user_id: время вступления}`` для небольших чатов."""
        raw = self.raw.get("participants") or {}
        result: dict[int, int] = {}
        for key, value in raw.items():
            try:
                result[int(key)] = int(value)
            except (TypeError, ValueError):
                continue
        return result

    @property
    def participants_count(self) -> int | None:
        return self._int("participantsCount", "membersCount")

    @property
    def dialog_partner_id(self) -> int | None:
        """Собеседник в диалоге."""
        if not self.is_dialog:
            return None
        value = self.raw.get("participantId") or self.raw.get("dialogWithUser")
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
        me = self._client.user_id if self._client else None
        for user_id in self.participants:
            if user_id != me:
                return user_id
        return None

    @property
    def access(self) -> str | None:
        return self._str("access")

    @property
    def is_public(self) -> bool:
        return self.access == AccessType.PUBLIC.value

    @property
    def status(self) -> str | None:
        return self._str("status")

    @property
    def new_messages(self) -> int:
        return self._int("newMessages", "unread") or 0

    @property
    def last_message(self) -> Message | None:
        return Message.parse(self.raw.get("lastMessage"), self._client)

    @property
    def pinned_message(self) -> Message | None:
        return Message.parse(self.raw.get("pinnedMessage"), self._client)

    @property
    def options(self) -> dict[str, Any]:
        value = self.raw.get("options")
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            return {str(item): True for item in value}
        return {}

    @property
    def muted_until(self) -> int | None:
        return self._int("dontDisturbUntil")

    @property
    def is_muted(self) -> bool:
        value = self.muted_until
        return value is not None and value != 0

    @property
    def created_at(self) -> datetime | None:
        return _ts(self._int("created", "createTime"))

    @property
    def base_icon_url(self) -> str | None:
        return self._str("baseIconUrl", "baseRawIconUrl")

    # --- действия ----------------------------------------------------------

    async def send(self, text: str = "", **kwargs) -> Message:
        return await self.client.send_message(self.id, text, **kwargs)

    async def history(self, limit: int = 50, **kwargs) -> list[Message]:
        return await self.client.get_history(self.id, limit=limit, **kwargs)

    async def members(self, **kwargs) -> list[Member]:
        return await self.client.get_members(self.id, **kwargs)

    async def leave(self) -> None:
        await self.client.leave_chat(self.id)

    async def delete(self) -> None:
        await self.client.delete_chat(self.id)

    async def mute(self, until: int = -1) -> None:
        await self.client.mute_chat(self.id, until)

    async def unmute(self) -> None:
        await self.client.unmute_chat(self.id)

    async def read_all(self) -> None:
        message = self.last_message
        if message and message.id:
            await self.client.read_message(self.id, message.id)

    async def typing(self, kind: str = "TEXT") -> None:
        await self.client.send_typing(self.id, kind)

    async def refresh(self) -> "Chat | None":
        return await self.client.get_chat(self.id)

    def __repr__(self) -> str:
        return f"<Chat id={self.id} type={self.type} title={self.title!r}>"


class Folder(Model):
    """Папка чатов."""

    @property
    def id(self) -> int | None:
        return self._int("id", "folderId")

    @property
    def name(self) -> str | None:
        return self._str("name", "title")

    @property
    def chat_ids(self) -> list[int]:
        return [int(c) for c in (self.raw.get("chatIds") or []) if c is not None]

    @property
    def emoji(self) -> str | None:
        return self._str("emoji", "icon")


def _ts(value: int | None) -> datetime | None:
    if not value:
        return None
    seconds = value / 1000 if value > 10_000_000_000 else value
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None
