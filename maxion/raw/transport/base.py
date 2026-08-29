"""Абстракция транспорта: как кадры уходят и приходят."""

from __future__ import annotations

import abc

from ..protocol import Packet


class BaseTransport(abc.ABC):
    """Единый интерфейс для WebSocket- и TLS-транспортов."""

    #: значение поля ``ver`` в кадрах этого транспорта
    rpc_version: int = 11

    #: как транспорт представляется серверу в SESSION_INIT
    device_type: str = "WEB"

    @abc.abstractmethod
    async def connect(self) -> None:
        """Устанавливает соединение."""

    @abc.abstractmethod
    async def close(self) -> None:
        """Закрывает соединение; повторный вызов безопасен."""

    @abc.abstractmethod
    async def send(self, packet: Packet) -> None:
        """Отправляет кадр."""

    @abc.abstractmethod
    async def recv(self) -> Packet:
        """Ждёт следующий кадр.

        :raises maxion.raw.errors.TransportError: если соединение закрыто.
        """

    @property
    @abc.abstractmethod
    def is_connected(self) -> bool: ...

    async def __aenter__(self) -> "BaseTransport":
        await self.connect()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()
