"""Форматы сигнальных сообщений звонка.

Сняты из клиента ``ru.oneme.app`` 26.29.1: сигнализация звонков идёт JSON'ом
(``org.json.JSONObject``), а не MsgPack, и не через опкоды протокола. Типы
сообщений лежат в enum: ``NONE``, ``SDP``, ``CANDIDATE``, ``SIGNALING``.

Формы полей восстановлены из строковых констант классов сборки/разбора::

    SDP     {type: "SDP",       sdp, label, capabilities, p2pRelay, data}
    ICE     {type: "CANDIDATE", candidate, sdpMid, sdpMLineIndex, data}

Канал, по которому эти сообщения ходят, из APK статически не извлекается —
эндпоинт приходит с сервера в рантайме. Поэтому модуль канал не открывает:
он лишь строит и разбирает сообщения, а доставку отдаёт наружу.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SignalType(str, Enum):
    """Тип сигнального сообщения (enum ``Luzj;`` из клиента)."""

    NONE = "NONE"
    SDP = "SDP"
    CANDIDATE = "CANDIDATE"
    SIGNALING = "SIGNALING"


@dataclass
class SdpSignal:
    """SDP-предложение или ответ."""

    sdp: str
    #: ``offer`` или ``answer`` — из ``RTCSessionDescription.type``.
    sdp_type: str
    label: str | None = None
    capabilities: int | None = None
    p2p_relay: bool | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "type": SignalType.SDP.value,
            "sdp": self.sdp,
            "sdpType": self.sdp_type,
        }
        if self.label is not None:
            data["label"] = self.label
        if self.capabilities is not None:
            data["capabilities"] = self.capabilities
        if self.p2p_relay is not None:
            data["p2pRelay"] = self.p2p_relay
        data.update(self.extra)
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "SdpSignal":
        known = {"type", "sdp", "sdpType", "label", "capabilities", "p2pRelay"}
        return cls(
            sdp=str(data.get("sdp", "")),
            sdp_type=str(data.get("sdpType") or data.get("type_", "offer")),
            label=data.get("label"),
            capabilities=data.get("capabilities"),
            p2p_relay=data.get("p2pRelay"),
            extra={k: v for k, v in data.items() if k not in known},
        )


@dataclass
class IceSignal:
    """ICE-кандидат.

    Поля названы как в клиенте: ``candidate``, ``sdpMid``, ``sdpMLineIndex``.
    """

    candidate: str
    sdp_mid: str | None = None
    sdp_mline_index: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "type": SignalType.CANDIDATE.value,
            "candidate": self.candidate,
        }
        if self.sdp_mid is not None:
            data["sdpMid"] = self.sdp_mid
        if self.sdp_mline_index is not None:
            data["sdpMLineIndex"] = self.sdp_mline_index
        data.update(self.extra)
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "IceSignal":
        known = {"type", "candidate", "sdpMid", "sdpMLineIndex"}
        return cls(
            candidate=str(data.get("candidate", "")),
            sdp_mid=data.get("sdpMid"),
            sdp_mline_index=data.get("sdpMLineIndex"),
            extra={k: v for k, v in data.items() if k not in known},
        )


def parse_signal(data: dict[str, Any]) -> SdpSignal | IceSignal | dict[str, Any]:
    """Разбирает входящее сообщение по полю ``type``.

    Неизвестный тип возвращается как есть — чтобы канал мог обработать его сам.
    """
    kind = str(data.get("type", "")).upper()
    if kind == SignalType.SDP.value or "sdp" in data:
        return SdpSignal.from_json(data)
    if kind == SignalType.CANDIDATE.value or "candidate" in data:
        return IceSignal.from_json(data)
    return data


def ice_servers_from(turn_server: Any) -> list[dict[str, Any]]:
    """Приводит присланный сервером ``turnServer`` к списку ICE-серверов.

    Формат ``turnServer`` в ответе на звонок из APK не извлекается (приходит
    в рантайме), поэтому поддерживаем несколько вероятных форм: строку-URL,
    объект с ``urls``/``username``/``credential`` или список таких объектов.
    """
    if not turn_server:
        return []
    if isinstance(turn_server, str):
        return [{"urls": [turn_server]}]
    if isinstance(turn_server, dict):
        urls = turn_server.get("urls") or turn_server.get("url")
        if isinstance(urls, str):
            urls = [urls]
        server: dict[str, Any] = {"urls": urls or []}
        for src, dst in (
            ("username", "username"),
            ("credential", "credential"),
            ("password", "credential"),
        ):
            if turn_server.get(src) is not None:
                server[dst] = turn_server[src]
        return [server]
    if isinstance(turn_server, list):
        result: list[dict[str, Any]] = []
        for item in turn_server:
            result.extend(ice_servers_from(item))
        return result
    return []


__all__ = [
    "SignalType",
    "SdpSignal",
    "IceSignal",
    "parse_signal",
    "ice_servers_from",
]
