"""Константы протокола MAX (внутренний клиентский API, api/ws-api.oneme.ru)."""

from __future__ import annotations

# --- Точки входа -----------------------------------------------------------

WS_URL = "wss://ws-api.oneme.ru/websocket"
"""WebSocket-эндпоинт, который использует web.max.ru (JSON-кадры)."""

TCP_HOST = "api.oneme.ru"
TCP_PORT = 443
"""TLS-эндпоинт мобильных/десктопных клиентов (бинарные кадры MsgPack+LZ4)."""

WEB_ORIGIN = "https://web.max.ru"

# --- Версии ----------------------------------------------------------------

RPC_VERSION_WS = 11
"""`ver` для web-протокола."""

RPC_VERSION_TCP = 10
"""`ver` для мобильного бинарного протокола."""

APP_VERSION_WEB = "26.2.2"
APP_VERSION_ANDROID = "26.28.0"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)

# --- Кадрирование ----------------------------------------------------------

HEADER_SIZE = 10
"""ver(1) + cmd(2) + seq(2) + opcode(2) + cof(1) + length(3)."""

COMPRESS_THRESHOLD = 32
"""Payload короче этого размера не сжимается (правило клиента)."""

# --- Тайминги --------------------------------------------------------------

PING_INTERVAL = 30.0
REQUEST_TIMEOUT = 30.0
RECONNECT_DELAYS = (1.0, 2.0, 5.0, 10.0, 15.0, 30.0)

# --- Загрузка файлов -------------------------------------------------------

UPLOAD_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Origin": WEB_ORIGIN,
    "Referer": WEB_ORIGIN + "/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "cross-site",
    "User-Agent": DEFAULT_USER_AGENT,
}

DEFAULT_USER_AGENT_OBJECT = {
    "deviceType": "WEB",
    "locale": "ru",
    "deviceLocale": "ru",
    "osVersion": "Linux",
    "deviceName": "Chrome",
    "headerUserAgent": DEFAULT_USER_AGENT,
    "appVersion": APP_VERSION_WEB,
    "screen": "1080x1920 1.0x",
    "timezone": "Europe/Moscow",
}
"""Профиль по умолчанию. Готовые профили устройств -- в maxion.raw.device.Device."""
