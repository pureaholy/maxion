"""Протокол сигнализации звонков OK externcalls.

Снят с живого звонка ``ru.oneme.app`` 26.29.1: клиент подключается к
``wss://videowebrtc.okcdn.ru/ws2`` (адрес и токен — в поле ``vcp`` из
NOTIF_CALL_START, см. :func:`maxion.calls.parse_vcp`), соединение сжато
расширением ``permessage-deflate``, сообщения — JSON.

Клиент шлёт команды с растущим ``sequence``::

    accept-call            {mediaSettings}
    change-media-settings  {mediaSettings: {isAudioEnabled, isVideoEnabled, …}}
    update-media-modifiers {mediaModifiers: {denoise, denoiseAnn}}
    transmit-data          {participantId, participantType, data: {sdp|candidate}}
    custom-data            {data: {sdk: {rtt, loss}}}

Сервер отвечает ``response``/``notification`` со ``stamp``::

    {stamp, peerId: {id, type}, data: {sdp: {type, sdp}}}
    {stamp, peerId, data: {candidate: {candidate: "candidate:…"}}}

SDP и ICE ходят внутри ``data`` — и у клиента (в ``transmit-data``), и у
сервера. Этот модуль строит и разбирает такие сообщения; сетевой канал с
``permessage-deflate`` — :class:`OkRtcChannel`.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from typing import Any


# --- медиа-настройки -------------------------------------------------------

def media_settings(
    *,
    audio: bool = True,
    video: bool = False,
    screen: bool = False,
    fast_screen: bool = False,
    audio_sharing: bool = False,
) -> dict[str, bool]:
    """Объект ``mediaSettings`` в именах клиента."""
    return {
        "isAudioEnabled": audio,
        "isVideoEnabled": video,
        "isScreenSharingEnabled": screen,
        "isFastScreenSharingEnabled": fast_screen,
        "isAudioSharingEnabled": audio_sharing,
    }


# --- исходящие команды -----------------------------------------------------

class Commands:
    """Строит команды клиента. ``sequence`` растёт сам."""

    def __init__(self) -> None:
        self._seq = itertools.count(1)

    def _cmd(self, command: str, **fields: Any) -> dict[str, Any]:
        return {"command": command, "sequence": next(self._seq), **fields}

    def accept_call(self, settings: dict[str, bool] | None = None) -> dict[str, Any]:
        return self._cmd("accept-call", mediaSettings=settings or media_settings())

    def change_media_settings(self, settings: dict[str, bool]) -> dict[str, Any]:
        return self._cmd("change-media-settings", mediaSettings=settings)

    def update_media_modifiers(
        self, *, denoise: bool = False, denoise_ann: bool = False
    ) -> dict[str, Any]:
        return self._cmd(
            "update-media-modifiers",
            mediaModifiers={"denoise": denoise, "denoiseAnn": denoise_ann},
        )

    def change_participant_state(self, state: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._cmd("change-participant-state", participantState={"state": state or {}})

    def transmit_sdp(
        self,
        participant_id: int,
        sdp: str,
        *,
        participant_type: str = "USER",
        p2p_relay: bool = True,
    ) -> dict[str, Any]:
        """SDP (offer/answer) собеседнику через ``transmit-data``."""
        return self._cmd(
            "transmit-data",
            participantId=participant_id,
            participantType=participant_type,
            data={"sdp": {"p2pRelay": p2p_relay, "sdp": sdp}},
        )

    def transmit_candidate(
        self,
        participant_id: int,
        candidate: str,
        *,
        participant_type: str = "USER",
    ) -> dict[str, Any]:
        """ICE-кандидат собеседнику."""
        return self._cmd(
            "transmit-data",
            participantId=participant_id,
            participantType=participant_type,
            data={"candidate": {"candidate": candidate}},
        )

    def custom_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Служебные данные (например статистика ``{sdk: {rtt, loss}}``)."""
        return self._cmd("custom-data", data=data)


# --- входящие сообщения ----------------------------------------------------

@dataclass
class OkRtcMessage:
    """Разобранное сообщение от сервера сигнализации."""

    stamp: int | None
    peer_id: int | None
    peer_type: str | None
    #: ``response`` / ``notification`` (если сервер прислал ``type``).
    kind: str | None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def data(self) -> dict[str, Any]:
        value = self.raw.get("data")
        return value if isinstance(value, dict) else {}

    @property
    def sdp(self) -> dict[str, Any] | None:
        """``{type, sdp}`` если сервер прислал SDP, иначе None."""
        value = self.data.get("sdp")
        return value if isinstance(value, dict) else None

    @property
    def candidate(self) -> str | None:
        """Строка ICE-кандидата, если пришёл кандидат."""
        cand = self.data.get("candidate")
        if isinstance(cand, dict):
            return cand.get("candidate")
        return cand if isinstance(cand, str) else None

    @property
    def capabilities(self) -> Any:
        return self.data.get("capabilities")


def parse_message(data: dict[str, Any]) -> OkRtcMessage:
    """Разбирает входящее сообщение сигнализации OK."""
    peer = data.get("peerId")
    peer_id = peer.get("id") if isinstance(peer, dict) else peer
    peer_type = peer.get("type") if isinstance(peer, dict) else None
    return OkRtcMessage(
        stamp=data.get("stamp"),
        peer_id=peer_id,
        peer_type=peer_type,
        kind=data.get("type"),
        raw=data,
    )


# --- сетевой канал ---------------------------------------------------------

class OkRtcChannel:
    """WebSocket-канал сигнализации к ``videowebrtc.okcdn.ru`` с deflate.

    Требует extra ``maxion[calls]`` (websockets). URL и токен берутся из
    :class:`~maxion.calls.signaling.CallConfig`. Пример::

        cfg = parse_vcp(notif["vcp"])
        async with OkRtcChannel.connect(cfg) as ch:
            await ch.send(ch.commands.accept_call())
            async for msg in ch:
                if msg.sdp: ...
    """

    def __init__(self, ws) -> None:
        self._ws = ws
        self.commands = Commands()

    @classmethod
    async def connect(cls, config, *, conversation_id: str, peer_id: int, tgt: str = "accept"):
        """Открывает канал по параметрам из ``vcp``.

        Собирает URL так же, как клиент: ``/ws2`` с query-параметрами
        ``conversationId``, ``peerId``, ``token`` и ``tgt``.
        """
        try:
            import websockets
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "для звонков нужен extra maxion[calls]"
            ) from exc
        from urllib.parse import urlencode

        base = config.signaling_url
        query = urlencode(
            {
                "conversationId": conversation_id,
                "peerId": peer_id,
                "token": config.token,
                "tgt": tgt,
                "version": 5,
                "clientType": "one_me",
                "platform": "DESKTOP",
            }
        )
        url = f"{base}{'&' if '?' in base else '?'}{query}"
        ws = await websockets.connect(
            url, compression="deflate", max_size=8 * 1024 * 1024
        )
        return cls(ws)

    async def send(self, message: dict[str, Any]) -> None:
        await self._ws.send(json.dumps(message, ensure_ascii=False))

    async def recv(self) -> OkRtcMessage:
        raw = await self._ws.recv()
        if isinstance(raw, (bytes, bytearray)):
            raw = bytes(raw).decode("utf-8", "replace")
        return parse_message(json.loads(raw))

    async def __aenter__(self) -> "OkRtcChannel":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()

    def __aiter__(self):
        return self

    async def __anext__(self) -> OkRtcMessage:
        try:
            return await self.recv()
        except Exception as exc:  # закрытие соединения завершает итерацию
            raise StopAsyncIteration from exc

    async def close(self) -> None:
        await self._ws.close()


__all__ = [
    "media_settings",
    "Commands",
    "OkRtcMessage",
    "parse_message",
    "OkRtcChannel",
]
