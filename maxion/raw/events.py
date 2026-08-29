"""События сервера: разбор NOTIF_*-кадров в типизированные объекты."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .opcodes import Opcode
from .protocol import Packet
from .types import Chat, Message, Presence, User

if TYPE_CHECKING:  # pragma: no cover
    from .client import MaxClient


class Update:
    """Базовое событие. Всегда хранит исходный пакет."""

    #: имя события для роутера
    event: str = "raw"

    __slots__ = ("client", "packet")

    def __init__(self, client: "MaxClient", packet: Packet):
        self.client = client
        self.packet = packet

    @property
    def payload(self) -> dict[str, Any]:
        return self.packet.payload

    @property
    def opcode(self) -> int:
        return self.packet.opcode

    @property
    def name(self) -> str:
        return self.packet.name

    def get(self, key: str, default: Any = None) -> Any:
        return self.payload.get(key, default)

    @property
    def chat_id(self) -> int | None:
        value = self.payload.get("chatId")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name} payload={self.payload!r}>"


class NewMessage(Update):
    """NOTIF_MESSAGE (128) — новое или изменённое сообщение."""

    event = "message"

    @property
    def message(self) -> Message:
        return Message(self.payload.get("message") or {}, self.client)

    # --- частые обращения напрямую ----------------------------------------

    @property
    def text(self) -> str:
        return self.message.text

    @property
    def sender_id(self) -> int | None:
        return self.message.sender_id

    @property
    def outgoing(self) -> bool:
        return self.message.outgoing

    @property
    def is_edit(self) -> bool:
        return bool(self.payload.get("prevMessageId") or self.payload.get("edited"))

    async def reply(self, text: str = "", **kwargs) -> Message:
        return await self.message.reply(text, **kwargs)

    async def answer(self, text: str = "", **kwargs) -> Message:
        return await self.message.answer(text, **kwargs)

    async def read(self) -> None:
        await self.message.read()

    def __repr__(self) -> str:
        return f"<NewMessage chat={self.chat_id} text={self.message.text[:40]!r}>"


class MessageDeleted(Update):
    """NOTIF_MSG_DELETE (142)."""

    event = "message_deleted"

    @property
    def message_ids(self) -> list[str]:
        ids = self.payload.get("messageIds") or self.payload.get("ids") or []
        return [str(i) for i in ids]


class MessageRangeDeleted(Update):
    """NOTIF_MSG_DELETE_RANGE (140)."""

    event = "message_range_deleted"


class DelayedMessage(Update):
    """NOTIF_MSG_DELAYED (154) — отложенная публикация."""

    event = "message_delayed"


class Typing(Update):
    """NOTIF_TYPING (129)."""

    event = "typing"

    @property
    def user_id(self) -> int | None:
        value = self.payload.get("userId") or self.payload.get("sender")
        return int(value) if value is not None else None

    @property
    def type(self) -> str | None:
        return self.payload.get("type")


class ReadMark(Update):
    """NOTIF_MARK (130) — прочтение сообщений."""

    event = "mark"

    @property
    def mark(self) -> int | None:
        value = self.payload.get("mark")
        return int(value) if value is not None else None

    @property
    def type(self) -> str | None:
        return self.payload.get("type")


class ContactUpdate(Update):
    """NOTIF_CONTACT (131)."""

    event = "contact"

    @property
    def user(self) -> User | None:
        raw = self.payload.get("contact") or self.payload.get("contacts")
        if isinstance(raw, list):
            raw = raw[0] if raw else None
        return User.parse(raw, self.client)


class PresenceUpdate(Update):
    """NOTIF_PRESENCE (132)."""

    event = "presence"

    @property
    def presences(self) -> dict[int, Presence]:
        raw = self.payload.get("presence") or {}
        return {int(k): Presence(v, self.client) for k, v in raw.items()}


class ChatUpdate(Update):
    """NOTIF_CHAT (135) — изменение чата, вход/выход участников."""

    event = "chat"

    @property
    def chat(self) -> Chat | None:
        raw = self.payload.get("chat") or self.payload.get("chats")
        if isinstance(raw, list):
            raw = raw[0] if raw else None
        return Chat.parse(raw, self.client)


class AttachUpdate(Update):
    """NOTIF_ATTACH (136) — сервер дообработал загруженное медиа."""

    event = "attach"

    @property
    def video_id(self) -> int | None:
        value = self.payload.get("videoId")
        return int(value) if value is not None else None

    @property
    def file_id(self) -> int | None:
        value = self.payload.get("fileId")
        return int(value) if value is not None else None


class ConfigUpdate(Update):
    """NOTIF_CONFIG (134)."""

    event = "config"


class ProfileUpdate(Update):
    """NOTIF_PROFILE (159)."""

    event = "profile"


class ReactionsChanged(Update):
    """NOTIF_MSG_REACTIONS_CHANGED (155)."""

    event = "reactions"

    @property
    def message_id(self) -> str | None:
        value = self.payload.get("messageId")
        return str(value) if value is not None else None


class YouReacted(Update):
    """NOTIF_MSG_YOU_REACTED (156)."""

    event = "you_reacted"


class CallStart(Update):
    """NOTIF_CALL_START (137)."""

    event = "call"


class CallHistoryUpdate(Update):
    """NOTIF_CALL_HISTORY (165)."""

    event = "call_history"


class CallbackAnswer(Update):
    """NOTIF_CALLBACK_ANSWER (143) — ответ бота на нажатие кнопки."""

    event = "callback"


class LocationUpdate(Update):
    """NOTIF_LOCATION (147)."""

    event = "location"


class LocationRequest(Update):
    """NOTIF_LOCATION_REQUEST (148)."""

    event = "location_request"


class DraftUpdate(Update):
    """NOTIF_DRAFT (152) / NOTIF_DRAFT_DISCARD (153)."""

    event = "draft"


class FoldersUpdate(Update):
    """NOTIF_FOLDERS (277)."""

    event = "folders"


class StoriesUpdate(Update):
    """NOTIF_STORIES_UPDATE (216)."""

    event = "stories"


class AssetsUpdate(Update):
    """NOTIF_ASSETS_UPDATE (150)."""

    event = "assets"


class TranscriptionUpdate(Update):
    """NOTIF_TRANSCRIPTION (293)."""

    event = "transcription"


class BannersUpdate(Update):
    """NOTIF_BANNERS (292)."""

    event = "banners"


class ContactSortUpdate(Update):
    """NOTIF_CONTACT_SORT (139)."""

    event = "contact_sort"


class Reconnect(Update):
    """RECONNECT (3) — сервер просит переподключиться."""

    event = "reconnect"

    @property
    def host(self) -> str | None:
        return self.payload.get("redirectHost")


UPDATE_CLASSES: dict[int, type[Update]] = {
    Opcode.NOTIF_MESSAGE: NewMessage,
    Opcode.NOTIF_TYPING: Typing,
    Opcode.NOTIF_MARK: ReadMark,
    Opcode.NOTIF_CONTACT: ContactUpdate,
    Opcode.NOTIF_PRESENCE: PresenceUpdate,
    Opcode.NOTIF_CONFIG: ConfigUpdate,
    Opcode.NOTIF_CHAT: ChatUpdate,
    Opcode.NOTIF_ATTACH: AttachUpdate,
    Opcode.NOTIF_CALL_START: CallStart,
    Opcode.NOTIF_CONTACT_SORT: ContactSortUpdate,
    Opcode.NOTIF_MSG_DELETE_RANGE: MessageRangeDeleted,
    Opcode.NOTIF_MSG_DELETE: MessageDeleted,
    Opcode.NOTIF_CALLBACK_ANSWER: CallbackAnswer,
    Opcode.NOTIF_LOCATION: LocationUpdate,
    Opcode.NOTIF_LOCATION_REQUEST: LocationRequest,
    Opcode.NOTIF_ASSETS_UPDATE: AssetsUpdate,
    Opcode.NOTIF_DRAFT: DraftUpdate,
    Opcode.NOTIF_DRAFT_DISCARD: DraftUpdate,
    Opcode.NOTIF_MSG_DELAYED: DelayedMessage,
    Opcode.NOTIF_MSG_REACTIONS_CHANGED: ReactionsChanged,
    Opcode.NOTIF_MSG_YOU_REACTED: YouReacted,
    Opcode.NOTIF_PROFILE: ProfileUpdate,
    Opcode.NOTIF_CALL_HISTORY: CallHistoryUpdate,
    Opcode.NOTIF_FOLDERS: FoldersUpdate,
    Opcode.NOTIF_STORIES_UPDATE: StoriesUpdate,
    Opcode.NOTIF_TRANSCRIPTION: TranscriptionUpdate,
    Opcode.NOTIF_BANNERS: BannersUpdate,
    Opcode.RECONNECT: Reconnect,
}

EVENT_NAMES: frozenset[str] = frozenset(
    {cls.event for cls in UPDATE_CLASSES.values()} | {"raw", "edited_message"}
)


def parse_update(client: "MaxClient", packet: Packet) -> Update:
    """Оборачивает входящий кадр в подходящий класс события."""
    return UPDATE_CLASSES.get(packet.opcode, Update)(client, packet)
