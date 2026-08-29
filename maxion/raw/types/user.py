"""Пользователи, контакты, профиль, присутствие."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..enums import PresenceStatus
from .base import Model


class User(Model):
    """Контакт (ContactInfo). Данные лежат в ``raw['names']`` и ``raw['contact']``."""

    @property
    def id(self) -> int | None:
        return self._int("id", "userId", "accountId", "contactId")

    @property
    def _contact(self) -> dict[str, Any]:
        contact = self.raw.get("contact")
        return contact if isinstance(contact, dict) else self.raw

    @property
    def phone(self) -> str | None:
        value = self._contact.get("phone")
        return str(value) if value is not None else None

    @property
    def names(self) -> list[dict[str, Any]]:
        names = self._contact.get("names") or self.raw.get("names") or []
        return [n for n in names if isinstance(n, dict)]

    @property
    def first_name(self) -> str | None:
        for entry in self.names:
            if entry.get("firstName"):
                return str(entry["firstName"])
        return self._str("firstName")

    @property
    def last_name(self) -> str | None:
        for entry in self.names:
            if entry.get("lastName"):
                return str(entry["lastName"])
        return self._str("lastName")

    @property
    def name(self) -> str:
        """Отображаемое имя."""
        for entry in self.names:
            if entry.get("name"):
                return str(entry["name"])
        parts = [p for p in (self.first_name, self.last_name) if p]
        return " ".join(parts) or (self.link or f"id{self.id}")

    @property
    def link(self) -> str | None:
        """Короткая ссылка (@username)."""
        return self._contact.get("link") or self.raw.get("link")

    @property
    def username(self) -> str | None:
        return self.link

    @property
    def description(self) -> str | None:
        return self._contact.get("description") or self.raw.get("description")

    @property
    def photo_url(self) -> str | None:
        base = self._contact.get("baseUrl") or self.raw.get("baseUrl")
        return str(base) if base else None

    @property
    def photo_id(self) -> int | None:
        value = self._contact.get("photoId") or self.raw.get("photoId")
        return int(value) if value is not None else None

    @property
    def is_bot(self) -> bool:
        options = self._contact.get("options") or self.raw.get("options") or []
        return "BOT" in options or bool(self.raw.get("bot"))

    @property
    def is_verified(self) -> bool:
        options = self._contact.get("options") or self.raw.get("options") or []
        return "VERIFIED" in options or "OFFICIAL" in options

    @property
    def options(self) -> list[str]:
        options = self._contact.get("options") or self.raw.get("options") or []
        return [str(o) for o in options]

    @property
    def updated_at(self) -> datetime | None:
        value = self._int("updateTime")
        return _ts(value)

    def mention(self, text: str | None = None) -> dict[str, Any]:
        """Готовый элемент упоминания для ``elements``."""
        label = text or self.name
        return {"type": "USER_MENTION", "from": 0, "length": len(label), "userId": self.id}

    def __repr__(self) -> str:
        return f"<User id={self.id} name={self.name!r}>"


class Profile(User):
    """Собственный профиль (payload.profile)."""

    @property
    def id(self) -> int | None:
        contact = self.raw.get("contact")
        if isinstance(contact, dict) and contact.get("id") is not None:
            return int(contact["id"])
        return self._int("id", "userId", "accountId")

    @property
    def settings(self) -> dict[str, Any]:
        value = self.raw.get("settings")
        return value if isinstance(value, dict) else {}

    @property
    def hidden(self) -> bool:
        return bool(self.settings.get("HIDDEN"))

    @property
    def phone(self) -> str | None:
        contact = self.raw.get("contact")
        if isinstance(contact, dict):
            value = contact.get("phone")
            if value is not None:
                return str(value)
        return self._str("phone")


class Presence(Model):
    """Онлайн-статус пользователя."""

    @property
    def status(self) -> PresenceStatus | str | None:
        value = self._str("status", "on")
        return PresenceStatus(value) if value in ("ONLINE", "OFFLINE") else value

    @property
    def is_online(self) -> bool:
        return self.raw.get("on") == "ON" or self.status == PresenceStatus.ONLINE

    @property
    def seen_at(self) -> datetime | None:
        return _ts(self._int("seen", "lastSeen", "time"))

    @property
    def device_type(self) -> str | None:
        return self._str("deviceType")


class DeviceSession(Model):
    """Активная сессия аккаунта (SESSIONS_INFO)."""

    @property
    def id(self) -> int | None:
        return self._int("id", "sessionId")

    @property
    def device_name(self) -> str | None:
        return self._str("deviceName", "name")

    @property
    def app_version(self) -> str | None:
        return self._str("appVersion")

    @property
    def os_version(self) -> str | None:
        return self._str("osVersion")

    @property
    def ip(self) -> str | None:
        return self._str("ip", "remoteAddress")

    @property
    def is_current(self) -> bool:
        return bool(self.raw.get("current") or self.raw.get("isCurrent"))

    @property
    def last_active(self) -> datetime | None:
        return _ts(self._int("lastActiveTime", "time", "lastSeen"))


def _ts(value: int | None) -> datetime | None:
    if not value:
        return None
    seconds = value / 1000 if value > 10_000_000_000 else value
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None
