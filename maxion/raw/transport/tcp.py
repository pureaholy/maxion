"""TLS-транспорт (протокол мобильных клиентов, бинарные кадры).

Мобильное приложение держит обычный TLS-сокет к ``api.oneme.ru:443`` и гоняет
по нему кадры ``[ver][cmd][seq][opcode][cof][len][msgpack]``. Отличия от
web-версии: MsgPack вместо JSON, LZ4 для крупных payload, протокол 10 и
доступные только приложению методы (например, авторизация по номеру).
"""

from __future__ import annotations

import asyncio
import logging
import ssl as ssl_module
from typing import Any

from ..const import RPC_VERSION_TCP, TCP_HOST, TCP_PORT
from ..errors import TransportError
from ..protocol import Packet
from .base import BaseTransport

log = logging.getLogger(__name__)


class TcpTransport(BaseTransport):
    """Бинарный транспорт поверх TLS."""

    rpc_version = RPC_VERSION_TCP
    device_type = "ANDROID"

    def __init__(
        self,
        host: str = TCP_HOST,
        port: int = TCP_PORT,
        *,
        ssl: bool | ssl_module.SSLContext = True,
        compress: bool = True,
        connect_timeout: float = 20.0,
    ):
        self.host = host
        self.port = port
        self.ssl = ssl
        self.compress = compress
        self.connect_timeout = connect_timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._buffer = bytearray()
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        context: Any = self.ssl
        if context is True:
            context = ssl_module.create_default_context()
        log.debug("TCP connect %s:%s", self.host, self.port)
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port, ssl=context or None),
                timeout=self.connect_timeout,
            )
        except Exception as exc:
            raise TransportError(
                f"Не удалось подключиться к {self.host}:{self.port}: {exc}"
            ) from exc
        self._buffer.clear()

    async def close(self) -> None:
        writer, self._writer = self._writer, None
        self._reader = None
        if writer is not None:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                log.debug("ошибка при закрытии TCP", exc_info=True)

    async def send(self, packet: Packet) -> None:
        if self._writer is None:
            raise TransportError("TCP-соединение не установлено")
        packet.ver = packet.ver or self.rpc_version
        data = packet.to_bytes(compress=self.compress)
        async with self._lock:
            try:
                self._writer.write(data)
                await self._writer.drain()
            except Exception as exc:
                raise TransportError(f"Не удалось отправить кадр: {exc}") from exc

    async def recv(self) -> Packet:
        if self._reader is None:
            raise TransportError("TCP-соединение не установлено")
        while True:
            packet, consumed = Packet.parse_stream(bytes(self._buffer))
            if packet is not None:
                del self._buffer[:consumed]
                return packet
            try:
                chunk = await self._reader.read(65536)
            except Exception as exc:
                raise TransportError(f"Соединение закрыто: {exc}") from exc
            if not chunk:
                raise TransportError("Соединение закрыто сервером")
            self._buffer.extend(chunk)
