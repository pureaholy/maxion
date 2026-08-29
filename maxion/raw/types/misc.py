"""Прочие модели: стикеры, истории, звонки, опросы, ссылки."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .base import Model


class Sticker(Model):
    @property
    def id(self) -> int | None:
        return self._int("id", "stickerId")

    @property
    def set_id(self) -> int | None:
        return self._int("stickerSetId", "setId")

    @property
    def url(self) -> str | None:
        return self._str("url", "baseUrl")

    @property
    def lottie_url(self) -> str | None:
        return self._str("lottieUrl")

    @property
    def emoji(self) -> str | None:
        return self._str("emoji", "tags")

    def as_attach(self) -> dict[str, Any]:
        return {"_type": "STICKER", "stickerId": self.id}


class StickerSet(Model):
    @property
    def id(self) -> int | None:
        return self._int("id")

    @property
    def name(self) -> str | None:
        return self._str("name", "title")

    @property
    def sticker_ids(self) -> list[int]:
        return [int(s) for s in (self.raw.get("stickers") or []) if s is not None]


class Story(Model):
    @property
    def id(self) -> int | None:
        return self._int("id", "storyId")

    @property
    def owner_id(self) -> int | None:
        return self._int("ownerId", "owner")

    @property
    def created_at(self) -> datetime | None:
        return _ts(self._int("createTime", "time"))

    @property
    def expires_at(self) -> datetime | None:
        return _ts(self._int("expireTime"))

    @property
    def views(self) -> int | None:
        return self._int("viewsCount", "views")

    @property
    def is_viewed(self) -> bool:
        return bool(self.raw.get("viewed"))


class Call(Model):
    """Параметры звонка.

    Состав полей восстановлен из клиента ``ru.oneme.app`` 26.29.1: DTO
    параметров разговора печатает себя как ``{conversationId, callerId,
    chatId, turnServer, sdpOffer, type}``, расширенный вариант добавляет
    ``callType``, ``isContact`` и ``country``.

    Дальше звонок идёт мимо опкодов MAX: медиа — стоковый WebRTC
    (``libjingle_peerconnection``), сигнализация — JSON-сообщения типов
    ``sdp``/``candidate``/``signaling``. Библиотека покрывает только
    сигнальные опкоды: начать, войти, положить трубку, прочитать журнал.
    """

    @property
    def id(self) -> str | None:
        return self._str("id", "conversationId", "callId")

    @property
    def conversation_id(self) -> str | None:
        """Идентификатор разговора — им оперирует медиа-часть."""
        return self._str("conversationId")

    @property
    def chat_id(self) -> int | None:
        return self._int("chatId")

    @property
    def caller_id(self) -> int | None:
        """Кто звонит."""
        return self._int("callerId", "initiatorId", "userId")

    @property
    def initiator_id(self) -> int | None:
        """Синоним :attr:`caller_id`."""
        return self.caller_id

    @property
    def type(self) -> str | None:
        """``AUDIO`` или ``VIDEO``."""
        return self._str("type", "callType")

    @property
    def turn_server(self) -> Any:
        """Параметры TURN/STUN для установки медиа-соединения."""
        return self.raw.get("turnServer")

    @property
    def sdp_offer(self) -> str | None:
        """SDP-предложение вызывающей стороны, если сервер его прислал."""
        return self._str("sdpOffer")

    @property
    def is_contact(self) -> bool | None:
        value = self.raw.get("isContact")
        return bool(value) if value is not None else None

    @property
    def country(self) -> str | None:
        return self._str("country")

    @property
    def started_at(self) -> datetime | None:
        return _ts(self._int("startTime", "time"))

    @property
    def duration(self) -> int | None:
        return self._int("duration")

    @property
    def is_video(self) -> bool:
        return self.type == "VIDEO" or bool(self.raw.get("video"))

    @property
    def join_link(self) -> str | None:
        return self._str("joinLink", "link")


class Poll(Model):
    @property
    def id(self) -> int | None:
        return self._int("id", "pollId")

    @property
    def question(self) -> str | None:
        return self._str("question", "title")

    @property
    def answers(self) -> list[dict[str, Any]]:
        return [a for a in (self.raw.get("answers") or []) if isinstance(a, dict)]

    @property
    def total_voted(self) -> int | None:
        return self._int("totalVoted")

    @property
    def is_anonymous(self) -> bool:
        return bool(self.raw.get("anonymous"))

    @property
    def multiple(self) -> bool:
        return bool(self.raw.get("multiple"))


class LinkInfo(Model):
    """Ответ LINK_INFO / CHAT_CHECK_LINK."""

    @property
    def url(self) -> str | None:
        return self._str("url", "link")

    @property
    def title(self) -> str | None:
        return self._str("title")

    @property
    def description(self) -> str | None:
        return self._str("description")

    @property
    def chat_id(self) -> int | None:
        chat = self.raw.get("chat")
        if isinstance(chat, dict):
            value = chat.get("id")
            return int(value) if value is not None else None
        return self._int("chatId")


class Organization(Model):
    @property
    def id(self) -> int | None:
        return self._int("id", "organizationId")

    @property
    def name(self) -> str | None:
        return self._str("name", "title")

    @property
    def verified(self) -> bool:
        return bool(self.raw.get("verified"))


class UploadedFile(Model):
    """Результат загрузки медиа: готовое вложение для отправки."""

    @property
    def attach(self) -> dict[str, Any]:
        return dict(self.raw)

    @property
    def type(self) -> str:
        return str(self.raw.get("_type") or "")

    def __repr__(self) -> str:
        return f"<UploadedFile {self.type}>"


def _ts(value: int | None) -> datetime | None:
    if not value:
        return None
    seconds = value / 1000 if value > 10_000_000_000 else value
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None
