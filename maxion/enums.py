"""Перечисления высокого уровня.

Значения внутреннего протокола MAX отличаются от телеграмных, поэтому у
каждого элемента есть ``.raw`` — то, что реально уходит на провод.
"""

from __future__ import annotations

from enum import Enum


class AutoName(Enum):
    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}.{self.name}"


class ChatType(AutoName):
    """Тип чата. ``raw`` — значение поля ``type`` в протоколе MAX."""

    PRIVATE = "DIALOG"
    GROUP = "CHAT"
    SUPERGROUP = "CHAT"
    CHANNEL = "CHANNEL"

    @property
    def raw(self) -> str:
        return self.value

    @classmethod
    def from_raw(cls, value: str | None) -> "ChatType | None":
        return {
            "DIALOG": cls.PRIVATE,
            "CHAT": cls.GROUP,
            "CHANNEL": cls.CHANNEL,
        }.get(str(value or ""))


class ParseMode(AutoName):
    """Как разбирать разметку текста."""

    DEFAULT = "default"
    MARKDOWN = "markdown"
    HTML = "html"
    DISABLED = "disabled"


class ChatAction(AutoName):
    """Действие в чате для :meth:`Client.send_chat_action`."""

    TYPING = "TEXT"
    UPLOAD_PHOTO = "PHOTO"
    UPLOAD_VIDEO = "VIDEO"
    UPLOAD_AUDIO = "AUDIO"
    UPLOAD_DOCUMENT = "FILE"

    @property
    def raw(self) -> str:
        return self.value


class MessageEntityType(AutoName):
    """Тип форматирования участка текста. ``raw`` — как в протоколе."""

    BOLD = "STRONG"
    ITALIC = "EMPHASIZED"
    UNDERLINE = "UNDERLINE"
    STRIKETHROUGH = "STRIKETHROUGH"
    CODE = "MONOSPACED"
    PRE = "CODE_BLOCK"
    BLOCKQUOTE = "QUOTE"
    TEXT_LINK = "LINK"
    TEXT_MENTION = "USER_MENTION"
    HEADING = "HEADING"

    @property
    def raw(self) -> str:
        return self.value

    @classmethod
    def from_raw(cls, value: str | None) -> "MessageEntityType | None":
        for member in cls:
            if member.value == value:
                return member
        return None


class UserStatus(AutoName):
    """Онлайн-статус пользователя."""

    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


class ChatMemberStatus(AutoName):
    """Роль участника чата."""

    OWNER = "OWNER"
    ADMINISTRATOR = "ADMIN"
    MEMBER = "MEMBER"
    RESTRICTED = "PENDING"
    BANNED = "BLOCKED"

    @property
    def raw(self) -> str:
        return self.value

    @classmethod
    def from_raw(cls, value: str | None) -> "ChatMemberStatus":
        for member in cls:
            if member.value == value:
                return member
        return cls.MEMBER


__all__ = [
    "ChatType",
    "ParseMode",
    "ChatAction",
    "MessageEntityType",
    "UserStatus",
    "ChatMemberStatus",
]
