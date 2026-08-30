"""Звонки MAX: медиа-слой на aiortc.

Опциональный модуль — ставится через extra::

    pip install "maxion[calls]"

Что уже есть и что нет:

* **есть** — сборка и разбор сигнальных сообщений (SDP, ICE) в форматах,
  снятых с клиента ``ru.oneme.app`` 26.29.1, и медиа-сессия
  :class:`CallSession` поверх WebRTC (aiortc): offer/answer, обмен
  ICE-кандидатами, аудио- и видеотреки;
* **нет** — самого сигнального канала: адрес и обёртка приходят с сервера
  в рантайме и статически из APK не извлекаются. Поэтому :class:`CallSession`
  канал не открывает — исходящие сигналы отдаёт в колбэк, входящие принимает
  методом, а доставку соединяет с сокетом тот код, который снимет канал
  с живого дампа (см. ``docs/calls.md``).

Сигнальные опкоды звонков (начать, войти, положить трубку, журнал) — в
:mod:`maxion.raw.methods.calls`, отдельно от медиа.
"""

from __future__ import annotations

from .okrtc import Commands, OkRtcChannel, OkRtcMessage, media_settings, parse_message
from .signaling import (
    CallConfig,
    IceSignal,
    SdpSignal,
    SignalType,
    ice_servers_from,
    parse_signal,
    parse_vcp,
)

__all__ = [
    "SignalType",
    "SdpSignal",
    "IceSignal",
    "parse_signal",
    "ice_servers_from",
    "CallConfig",
    "parse_vcp",
    "Commands",
    "OkRtcMessage",
    "parse_message",
    "media_settings",
    "OkRtcChannel",
    "CallSession",
    "Call",
]


def __getattr__(name: str):
    # CallSession/Call тянут aiortc — импортируем лениво, чтобы signaling
    # работал и без установленного extra.
    if name == "CallSession":
        from .session import CallSession

        return CallSession
    if name == "Call":
        from .call import Call

        return Call
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
