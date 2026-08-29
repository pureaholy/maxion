"""Строковые перечисления протокола MAX.

В протоколе они передаются строками (``EnumAsString`` в разборе клиента),
поэтому все классы наследуют ``str``: их можно класть в payload как есть.
"""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - тривиально
        return self.value

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            for member in cls:
                if member.value.lower() == value.lower():
                    return member
        return None


# --- авторизация -----------------------------------------------------------

class Cmd(int, Enum):
    REQUEST = 0
    RESPONSE = 1
    ERROR = 3


class AuthType(StrEnum):
    START_AUTH = "START_AUTH"
    CHECK_CODE = "CHECK_CODE"
    RESEND_CODE = "RESEND_CODE"
    CALL_RESET = "CALL_RESET"
    START_PHONE_BIND = "START_PHONE_BIND"


class AuthTokenType(StrEnum):
    CHECK_CODE = "CHECK_CODE"
    CHECK_PASSWORD = "CHECK_PASSWORD"
    LOGIN = "LOGIN"
    QR = "QR"


class LoginTokenType(StrEnum):
    LOGIN = "LOGIN"
    CONFIRM = "CONFIRM"
    REGISTRATION = "REGISTRATION"


class PushDeviceType(StrEnum):
    """Канал пуш-уведомлений (enum La3e; из APK 26.29.1)."""

    GCM = "GCM"
    HUAWEI = "HUAWEI"
    RUSTORE = "RUSTORE"


class DeviceType(StrEnum):
    WEB = "WEB"
    ANDROID = "ANDROID"
    IOS = "IOS"
    DESKTOP = "DESKTOP"


# --- чаты ------------------------------------------------------------------

class ChatType(StrEnum):
    DIALOG = "DIALOG"
    CHAT = "CHAT"
    CHANNEL = "CHANNEL"


class AccessType(StrEnum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"


class ChatStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REMOVED = "REMOVED"
    LEFT = "LEFT"
    CLOSED = "CLOSED"
    HIDDEN = "HIDDEN"


class MemberType(StrEnum):
    MEMBER = "MEMBER"
    ADMIN = "ADMIN"
    OWNER = "OWNER"
    BLOCKED = "BLOCKED"
    PENDING = "PENDING"


class MarkType(StrEnum):
    READ_MESSAGE = "READ_MESSAGE"
    READ_MENTION = "READ_MENTION"
    SET_AS_UNREAD = "SET_AS_UNREAD"
    NOTIFY = "NOTIFY"


class ItemType(StrEnum):
    MESSAGE = "MESSAGE"
    COMMENT = "COMMENT"


class TypingType(StrEnum):
    TEXT = "TEXT"
    PHOTO = "PHOTO"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    FILE = "FILE"


# --- сообщения -------------------------------------------------------------

class MessageStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REMOVED = "REMOVED"
    EDITED = "EDITED"


class MessageType(StrEnum):
    USER = "USER"
    SYSTEM = "SYSTEM"
    CONTROL = "CONTROL"


class AttachType(StrEnum):
    PHOTO = "PHOTO"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    FILE = "FILE"
    STICKER = "STICKER"
    SHARE = "SHARE"
    CONTROL = "CONTROL"
    INLINE_KEYBOARD = "INLINE_KEYBOARD"
    LOCATION = "LOCATION"
    CONTACT = "CONTACT"
    APP = "APP"
    CALL = "CALL"
    PRESENT = "PRESENT"
    REPLY_KEYBOARD = "REPLY_KEYBOARD"
    POLL = "POLL"


class ElementType(StrEnum):
    """Тип форматирования участка текста."""

    STRONG = "STRONG"
    EMPHASIZED = "EMPHASIZED"
    MONOSPACED = "MONOSPACED"
    UNDERLINE = "UNDERLINE"
    STRIKETHROUGH = "STRIKETHROUGH"
    LINK = "LINK"
    USER_MENTION = "USER_MENTION"
    HEADING = "HEADING"
    CODE_BLOCK = "CODE_BLOCK"
    QUOTE = "QUOTE"


class ReactionType(StrEnum):
    EMOJI = "EMOJI"
    STICKER = "STICKER"


# --- контакты --------------------------------------------------------------

class ContactUpdateAction(StrEnum):
    ADD = "ADD"
    REMOVE = "REMOVE"
    BLOCK = "BLOCK"
    UNBLOCK = "UNBLOCK"
    RENAME = "RENAME"


class StatusType(StrEnum):
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    REMOVED = "REMOVED"


class PresenceStatus(StrEnum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


# --- ассеты ----------------------------------------------------------------

class AssetType(StrEnum):
    STICKER = "STICKER"
    STICKER_SET = "STICKER_SET"
    ANIMOJI = "ANIMOJI"
    ANIMOJI_SET = "ANIMOJI_SET"
    BACKGROUND = "BACKGROUND"
    FAVORITE = "FAVORITE"
    RECENT = "RECENT"


class AvatarType(StrEnum):
    DEFAULT = "DEFAULT"
    NEURO = "NEURO"
    PRESET = "PRESET"


# --- прочее ----------------------------------------------------------------

class ComplaintType(StrEnum):
    SPAM = "SPAM"
    PORNO = "PORNO"
    VIOLENCE = "VIOLENCE"
    CHILD_ABUSE = "CHILD_ABUSE"
    ILLEGAL = "ILLEGAL"
    OTHER = "OTHER"


class StoryReaction(StrEnum):
    LIKE = "LIKE"
    NONE = "NONE"
