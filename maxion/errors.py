"""Ошибки высокого уровня поверх ошибок протокола MAX.

Классы протокола (``RpcError``, ``AuthError`` и прочие) остаются доступны
в :mod:`maxion.raw.errors`; здесь — короткие имена для повседневного кода.
"""

from __future__ import annotations

from .raw.errors import (
    AuthError,
    MaxError,
    NotAuthorizedError,
    NotConnectedError,
    ProtocolError,
    RpcError,
    SessionExpiredError,
    TimeoutError_,
    TransportError,
    TwoFactorRequired,
)
from .raw.errors import FloodWaitError as _FloodWaitError


class MaxionError(MaxError):
    """Базовая ошибка библиотеки (алиас :class:`MaxError`)."""


#: База всех ошибок, пришедших от сервера.
RPCError = RpcError

#: Слишком частые запросы; ``exc.value`` — сколько секунд ждать.
class FloodWait(_FloodWaitError):
    """Сервер просит подождать. ``value`` — сколько секунд."""

    @property
    def value(self) -> int:
        return self.seconds


#: Не авторизованы: метод требует выполненного входа.
Unauthorized = NotAuthorizedError

#: Сессия истекла: нужен новый вход.
AuthKeyUnregistered = SessionExpiredError

#: Требуется пароль двухфакторной аутентификации.
SessionPasswordNeeded = TwoFactorRequired

#: Соединение не установлено.
ConnectionError_ = NotConnectedError

#: Таймаут ожидания ответа сервера.
Timeout = TimeoutError_

__all__ = [
    "MaxionError",
    "RPCError",
    "FloodWait",
    "Unauthorized",
    "AuthKeyUnregistered",
    "SessionPasswordNeeded",
    "ConnectionError_",
    "Timeout",
    "MaxError",
    "RpcError",
    "AuthError",
    "TransportError",
    "ProtocolError",
    "NotConnectedError",
    "NotAuthorizedError",
    "SessionExpiredError",
    "TwoFactorRequired",
]
