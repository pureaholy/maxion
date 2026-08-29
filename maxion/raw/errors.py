"""Иерархия ошибок протокола."""

from __future__ import annotations

from typing import Any, Mapping


class MaxError(Exception):
    """Базовая ошибка библиотеки."""


class TransportError(MaxError):
    """Проблема на уровне соединения (сокет, TLS, кадрирование)."""


class NotConnectedError(TransportError):
    """Операция требует активного соединения."""


class ProtocolError(MaxError):
    """Кадр не соответствует ожидаемому формату."""


class TimeoutError_(MaxError):
    """Сервер не ответил за отведённое время."""


Timeout = TimeoutError_


class AuthError(MaxError):
    """Сбой авторизации."""


class NotAuthorizedError(AuthError):
    """Метод требует выполненного логина."""


class SessionExpiredError(AuthError):
    """Сохранённый токен больше не действителен."""


class TwoFactorRequired(AuthError):
    """Аккаунт защищён паролем — требуется второй фактор."""

    def __init__(self, challenge: Mapping[str, Any] | None = None):
        super().__init__("Требуется пароль двухфакторной аутентификации")
        self.challenge = dict(challenge or {})


class RpcError(MaxError):
    """Сервер вернул ``cmd=3`` либо payload с полем ``error``.

    Структура ошибки MAX: ``error``, ``message``, ``localizedMessage``,
    опционально ``title`` и ``description``.
    """

    def __init__(self, opcode: int, payload: Mapping[str, Any]):
        self.opcode = int(opcode)
        self.payload = dict(payload)
        self.code: str = str(payload.get("error") or "unknown")
        self.message: str = str(
            payload.get("localizedMessage")
            or payload.get("message")
            or payload.get("description")
            or payload.get("title")
            or ""
        )
        from .opcodes import opcode_name

        text = f"[{opcode_name(self.opcode)}] {self.code}"
        if self.message:
            text += f": {self.message}"
        super().__init__(text)


class FloodWaitError(RpcError):
    """Слишком частые запросы."""

    @property
    def seconds(self) -> int:
        for key in ("retryAfter", "timeout", "wait", "duration"):
            if key in self.payload:
                try:
                    return int(self.payload[key])
                except (TypeError, ValueError):
                    pass
        return 0


_ERROR_CLASSES: dict[str, type[RpcError]] = {
    "flood": FloodWaitError,
    "too.many.requests": FloodWaitError,
}


def rpc_error(opcode: int, payload: Mapping[str, Any]) -> RpcError:
    """Подбирает конкретный класс ошибки по коду из payload."""
    code = str(payload.get("error") or "").lower()
    return _ERROR_CLASSES.get(code, RpcError)(opcode, payload)
