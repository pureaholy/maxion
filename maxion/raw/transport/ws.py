"""WebSocket-транспорт (протокол web.max.ru, JSON-кадры)."""

from __future__ import annotations

import logging
from typing import Any

from ..const import DEFAULT_USER_AGENT, RPC_VERSION_WS, WEB_ORIGIN, WS_URL
from ..errors import ProtocolError, TransportError
from ..protocol import Packet
from .base import BaseTransport

log = logging.getLogger(__name__)


class WebSocketTransport(BaseTransport):
    """Кадры ходят JSON-текстом внутри WebSocket."""

    rpc_version = RPC_VERSION_WS
    device_type = "WEB"

    def __init__(
        self,
        url: str = WS_URL,
        *,
        origin: str = WEB_ORIGIN,
        user_agent: str = DEFAULT_USER_AGENT,
        proxy: str | None = None,
        ssl_context: Any = None,
        open_timeout: float = 20.0,
    ):
        self.url = url
        self.origin = origin
        self.user_agent = user_agent
        self.proxy = proxy
        self.ssl_context = ssl_context
        self.open_timeout = open_timeout
        self._ws: Any = None

    @property
    def is_connected(self) -> bool:
        return self._ws is not None

    async def connect(self) -> None:
        try:
            import websockets
            from websockets.asyncio.client import connect as ws_connect
        except ImportError as exc:  # pragma: no cover
            raise TransportError(
                "Нужен пакет websockets: pip install websockets"
            ) from exc

        kwargs: dict[str, Any] = {
            "origin": websockets.Origin(self.origin),
            "user_agent_header": self.user_agent,
            "open_timeout": self.open_timeout,
            "max_size": 32 * 1024 * 1024,
        }
        if self.ssl_context is not None:
            kwargs["ssl"] = self.ssl_context
        if self.proxy is not None:
            kwargs["proxy"] = self.proxy

        log.debug("WS connect %s", self.url)
        try:
            self._ws = await ws_connect(self.url, **kwargs)
        except Exception as exc:
            raise TransportError(f"Не удалось подключиться к {self.url}: {exc}") from exc

    async def close(self) -> None:
        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                await ws.close()
            except Exception:  # закрытие не должно ронять вызывающего
                log.debug("ошибка при закрытии WS", exc_info=True)

    async def send(self, packet: Packet) -> None:
        if self._ws is None:
            raise TransportError("WebSocket не подключён")
        packet.ver = packet.ver or self.rpc_version
        try:
            await self._ws.send(packet.to_json())
        except Exception as exc:
            raise TransportError(f"Не удалось отправить кадр: {exc}") from exc

    async def recv(self) -> Packet:
        if self._ws is None:
            raise TransportError("WebSocket не подключён")
        try:
            raw = await self._ws.recv()
        except Exception as exc:
            raise TransportError(f"Соединение закрыто: {exc}") from exc
        if isinstance(raw, (bytes, bytearray)):
            # сервер иногда шлёт бинарь даже в web-режиме
            try:
                return Packet.from_bytes(bytes(raw))
            except ProtocolError:
                raw = bytes(raw).decode("utf-8", "replace")
        return Packet.from_json(raw)
