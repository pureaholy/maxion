"""Транспорты протокола MAX."""

from .base import BaseTransport
from .tcp import TcpTransport
from .ws import WebSocketTransport

__all__ = ["BaseTransport", "TcpTransport", "WebSocketTransport", "build_transport"]


def build_transport(kind: str = "ws", **kwargs) -> BaseTransport:
    """Фабрика по строковому имени: ``ws`` или ``tcp``."""
    kind = kind.lower()
    if kind in ("ws", "websocket", "web"):
        return WebSocketTransport(**kwargs)
    if kind in ("tcp", "tls", "mobile", "app"):
        return TcpTransport(**kwargs)
    raise ValueError(f"Неизвестный транспорт: {kind}")
