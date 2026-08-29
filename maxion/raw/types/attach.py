"""Вложения сообщений."""

from __future__ import annotations

from typing import Any, Mapping

from ..enums import AttachType
from .base import Model


class Attach(Model):
    """Базовое вложение. Тип лежит в ключе ``_type``."""

    @property
    def type(self) -> str:
        return str(self.raw.get("_type") or self.raw.get("type") or "")

    @classmethod
    def wrap(cls, raw: Mapping[str, Any] | None, client=None) -> "Attach":
        """Возвращает подходящий подкласс вложения."""
        raw = dict(raw or {})
        kind = str(raw.get("_type") or raw.get("type") or "")
        return _ATTACH_CLASSES.get(kind, Attach)(raw, client)

    @classmethod
    def wrap_list(cls, raw, client=None) -> list["Attach"]:
        return [cls.wrap(item, client) for item in (raw or []) if isinstance(item, Mapping)]

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.type}>"


class PhotoAttach(Attach):
    @property
    def photo_id(self) -> int | None:
        return self._int("photoId", "id")

    @property
    def token(self) -> str | None:
        return self._str("photoToken", "token")

    @property
    def url(self) -> str | None:
        return self._str("baseUrl", "url")

    @property
    def width(self) -> int | None:
        return self._int("width")

    @property
    def height(self) -> int | None:
        return self._int("height")


class VideoAttach(Attach):
    @property
    def video_id(self) -> int | None:
        return self._int("videoId", "id")

    @property
    def token(self) -> str | None:
        return self._str("token")

    @property
    def duration(self) -> int | None:
        return self._int("duration")

    @property
    def preview_url(self) -> str | None:
        return self._str("previewUrl", "baseUrl")


class AudioAttach(Attach):
    @property
    def audio_id(self) -> int | None:
        return self._int("audioId", "id")

    @property
    def duration(self) -> int | None:
        return self._int("duration")

    @property
    def transcription(self) -> str | None:
        return self._str("transcription")


class FileAttach(Attach):
    @property
    def file_id(self) -> int | None:
        return self._int("fileId", "id")

    @property
    def name(self) -> str | None:
        return self._str("name", "fileName")

    @property
    def size(self) -> int | None:
        return self._int("size")


class StickerAttach(Attach):
    @property
    def sticker_id(self) -> int | None:
        return self._int("stickerId", "id")

    @property
    def url(self) -> str | None:
        return self._str("url", "baseUrl")

    @property
    def lottie_url(self) -> str | None:
        return self._str("lottieUrl")


class ShareAttach(Attach):
    """Превью ссылки."""

    @property
    def url(self) -> str | None:
        return self._str("url")

    @property
    def title(self) -> str | None:
        return self._str("title")

    @property
    def description(self) -> str | None:
        return self._str("description")


class LocationAttach(Attach):
    @property
    def latitude(self) -> float | None:
        value = self.raw.get("latitude", self.raw.get("lat"))
        return float(value) if value is not None else None

    @property
    def longitude(self) -> float | None:
        value = self.raw.get("longitude", self.raw.get("lon"))
        return float(value) if value is not None else None

    @property
    def is_live(self) -> bool:
        return bool(self.raw.get("live"))


class ContactAttach(Attach):
    @property
    def contact_id(self) -> int | None:
        return self._int("contactId", "userId")

    @property
    def name(self) -> str | None:
        return self._str("name")

    @property
    def vcf(self) -> str | None:
        return self._str("vcfData", "vcf")


class ControlAttach(Attach):
    """Системное событие в ленте чата (вход/выход/смена названия)."""

    @property
    def event(self) -> str | None:
        return self._str("event")

    @property
    def user_ids(self) -> list[int]:
        return [int(u) for u in (self.raw.get("userIds") or []) if u is not None]

    @property
    def chat_type(self) -> str | None:
        return self._str("chatType")


class CallAttach(Attach):
    @property
    def call_id(self) -> str | None:
        return self._str("callId", "conversationId")

    @property
    def duration(self) -> int | None:
        return self._int("duration")

    @property
    def hangup_type(self) -> str | None:
        return self._str("hangupType")


class KeyboardAttach(Attach):
    """Inline-клавиатура бота."""

    @property
    def buttons(self) -> list[list[dict[str, Any]]]:
        rows = self.raw.get("buttons") or []
        return [[b for b in row if isinstance(b, dict)] for row in rows if isinstance(row, list)]

    def find(self, text: str) -> dict[str, Any] | None:
        """Ищет кнопку по подписи."""
        for row in self.buttons:
            for button in row:
                if str(button.get("text", "")) == text:
                    return button
        return None


class PollAttach(Attach):
    @property
    def poll_id(self) -> int | None:
        return self._int("pollId", "id")

    @property
    def question(self) -> str | None:
        return self._str("question", "title")

    @property
    def answers(self) -> list[dict[str, Any]]:
        return [a for a in (self.raw.get("answers") or []) if isinstance(a, dict)]

    @property
    def total_voted(self) -> int | None:
        return self._int("totalVoted", "votedTotal")


_ATTACH_CLASSES: dict[str, type[Attach]] = {
    AttachType.PHOTO.value: PhotoAttach,
    AttachType.VIDEO.value: VideoAttach,
    AttachType.AUDIO.value: AudioAttach,
    AttachType.FILE.value: FileAttach,
    AttachType.STICKER.value: StickerAttach,
    AttachType.SHARE.value: ShareAttach,
    AttachType.LOCATION.value: LocationAttach,
    AttachType.CONTACT.value: ContactAttach,
    AttachType.CONTROL.value: ControlAttach,
    AttachType.CALL.value: CallAttach,
    AttachType.INLINE_KEYBOARD.value: KeyboardAttach,
    AttachType.REPLY_KEYBOARD.value: KeyboardAttach,
    AttachType.POLL.value: PollAttach,
}
