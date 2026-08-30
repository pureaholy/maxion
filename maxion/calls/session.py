"""Медиа-сессия звонка поверх aiortc.

Обёртка над ``RTCPeerConnection``, которая говорит на сигнальных форматах
MAX (см. :mod:`maxion.calls.signaling`), но **не знает канала**: исходящие
сигналы уходят в колбэк ``on_signal``, входящие подаются методом
:meth:`feed_signal`. Канал (когда он будет снят с трафика) просто соединяет
эти две точки с сокетом.

Требует установки extra ``maxion[calls]`` (aiortc + PyAV с кодеками).

Пример каркаса::

    async def send(msg):        # доставка сигнала в реальный канал
        await channel.send(msg)

    call = CallSession(ice_servers=ice_servers_from(turn_server), on_signal=send)
    await call.add_microphone()
    offer = await call.create_offer()   # уйдёт и в on_signal, и вернётся
    ...                                 # получить answer из канала:
    await call.feed_signal(answer_msg)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from .signaling import IceSignal, SdpSignal, SignalType, parse_signal

log = logging.getLogger(__name__)

SignalSender = Callable[[dict[str, Any]], Awaitable[None] | None]


def _require_aiortc():
    try:
        import aiortc  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Для звонков нужен extra maxion[calls]: pip install 'maxion[calls]'"
        ) from exc
    from aiortc import (
        RTCConfiguration,
        RTCIceServer,
        RTCPeerConnection,
        RTCSessionDescription,
    )
    from aiortc.sdp import candidate_from_sdp, candidate_to_sdp

    return (
        RTCConfiguration,
        RTCIceServer,
        RTCPeerConnection,
        RTCSessionDescription,
        candidate_from_sdp,
        candidate_to_sdp,
    )


class CallSession:
    """Одна медиа-сессия WebRTC.

    :param ice_servers: список ICE-серверов (см.
        :func:`~maxion.calls.signaling.ice_servers_from`).
    :param on_signal: куда отдавать исходящие сигнальные сообщения. Может быть
        как обычной, так и async-функцией.
    """

    def __init__(
        self,
        *,
        ice_servers: list[dict[str, Any]] | None = None,
        on_signal: SignalSender | None = None,
    ):
        (
            RTCConfiguration,
            RTCIceServer,
            RTCPeerConnection,
            RTCSessionDescription,
            candidate_from_sdp,
            candidate_to_sdp,
        ) = _require_aiortc()

        self._RTCSessionDescription = RTCSessionDescription
        self._candidate_from_sdp = candidate_from_sdp
        self._candidate_to_sdp = candidate_to_sdp

        servers = [
            RTCIceServer(
                urls=s["urls"],
                username=s.get("username"),
                credential=s.get("credential"),
            )
            for s in (ice_servers or [])
            if s.get("urls")
        ]
        self.pc = RTCPeerConnection(RTCConfiguration(iceServers=servers))
        self.on_signal = on_signal

        self._closed = asyncio.Event()
        self._track_handlers: list[Callable[[Any], Any]] = []

        @self.pc.on("connectionstatechange")
        async def _state():  # pragma: no cover - зависит от сети
            log.info("состояние звонка: %s", self.pc.connectionState)
            if self.pc.connectionState in ("failed", "closed"):
                self._closed.set()

        @self.pc.on("track")
        def _track(track):  # pragma: no cover - зависит от сети
            log.info("входящий трек: %s", track.kind)
            for handler in self._track_handlers:
                handler(track)

    # --- медиа-треки -------------------------------------------------------

    async def add_microphone(self, device: str | None = None) -> None:
        """Добавляет аудио с микрофона (кодек Opus)."""
        player = self._open_player(device or self._default_mic(), {})
        if player.audio:
            self.pc.addTrack(player.audio)

    async def add_camera(
        self, device: str | None = None, *, size: str | None = None, fps: int | None = None
    ) -> None:
        """Добавляет видео с камеры (кодек VP8/H264 — что согласует aiortc).

        Видео-звонок в MAX идёт по тому же каналу; сервер предлагает VP8 и
        H264 (проверено по SDP из дампа). ``size`` — например ``"1280x720"``,
        ``fps`` — частота кадров.
        """
        opts: dict[str, str] = {}
        if size:
            opts["video_size"] = size
        if fps:
            opts["framerate"] = str(fps)
        player = self._open_player(device or self._default_camera(), opts, video=True)
        if player.video:
            self.pc.addTrack(player.video)

    async def add_media_file(self, path: str) -> None:
        """Добавляет аудио и видео из файла (для видео-звонка из ролика)."""
        from aiortc.contrib.media import MediaPlayer

        player = MediaPlayer(path)
        if player.audio:
            self.pc.addTrack(player.audio)
        if player.video:
            self.pc.addTrack(player.video)

    def add_track(self, track: Any) -> None:
        """Добавляет произвольный aiortc-трек (например из ``MediaPlayer``)."""
        self.pc.addTrack(track)

    def on_track(self, handler: Callable[[Any], Any]) -> Callable[[Any], Any]:
        """Регистрирует обработчик входящих треков (аудио/видео собеседника)."""
        self._track_handlers.append(handler)
        return handler

    # --- сигнализация: исходящее ------------------------------------------

    async def create_offer(self) -> SdpSignal:
        """Создаёт offer, применяет локально и отдаёт наружу."""
        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)
        signal = SdpSignal(sdp=self.pc.localDescription.sdp, sdp_type="offer")
        await self._emit(signal.to_json())
        return signal

    async def create_answer(self) -> SdpSignal:
        """Создаёт answer на уже принятый offer."""
        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)
        signal = SdpSignal(sdp=self.pc.localDescription.sdp, sdp_type="answer")
        await self._emit(signal.to_json())
        return signal

    # --- сигнализация: входящее -------------------------------------------

    async def feed_signal(self, message: dict[str, Any]) -> SdpSignal | None:
        """Обрабатывает входящее сигнальное сообщение из канала.

        На offer автоматически формирует answer и возвращает его; на answer и
        ICE-кандидата возвращает ``None``.
        """
        signal = parse_signal(message)
        if isinstance(signal, SdpSignal):
            return await self._apply_sdp(signal)
        if isinstance(signal, IceSignal):
            await self._apply_ice(signal)
            return None
        log.debug("неизвестное сигнальное сообщение: %s", message)
        return None

    async def _apply_sdp(self, signal: SdpSignal) -> SdpSignal | None:
        description = self._RTCSessionDescription(sdp=signal.sdp, type=signal.sdp_type)
        await self.pc.setRemoteDescription(description)
        if signal.sdp_type == "offer":
            return await self.create_answer()
        return None

    async def _apply_ice(self, signal: IceSignal) -> None:
        if not signal.candidate:
            return
        candidate = self._candidate_from_sdp(signal.candidate.replace("candidate:", "", 1))
        # OK externcalls шлёт кандидата без sdpMid/sdpMLineIndex, а aiortc
        # требует хотя бы один. При BUNDLE (один транспорт на все медиа)
        # первая m-line годится: sdpMid="0", sdpMLineIndex=0.
        candidate.sdpMid = signal.sdp_mid if signal.sdp_mid is not None else "0"
        candidate.sdpMLineIndex = (
            signal.sdp_mline_index if signal.sdp_mline_index is not None else 0
        )
        await self.pc.addIceCandidate(candidate)

    # --- жизненный цикл ----------------------------------------------------

    async def wait_closed(self) -> None:
        await self._closed.wait()

    async def close(self) -> None:
        await self.pc.close()
        self._closed.set()

    async def __aenter__(self) -> "CallSession":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()

    # --- внутреннее --------------------------------------------------------

    async def _emit(self, message: dict[str, Any]) -> None:
        if self.on_signal is None:
            return
        result = self.on_signal(message)
        if asyncio.iscoroutine(result):
            await result

    @staticmethod
    def _default_mic() -> str:
        import sys

        return {
            "win32": "audio=Microphone",
            "darwin": ":0",
        }.get(sys.platform, "default")

    @staticmethod
    def _default_camera() -> str:
        import sys

        return {
            "win32": "video=Integrated Camera",
            "darwin": "default:none",
            "linux": "/dev/video0",
        }.get(sys.platform, "/dev/video0")

    def _open_player(self, source: str, opts: dict[str, str], *, video: bool = False):
        from aiortc.contrib.media import MediaPlayer

        import sys

        if video:
            fmt = {"win32": "dshow", "darwin": "avfoundation", "linux": "v4l2"}.get(
                sys.platform
            )
        else:
            fmt = {"win32": "dshow", "darwin": "avfoundation", "linux": "pulse"}.get(
                sys.platform
            )
        return MediaPlayer(source, format=fmt, options=opts)


__all__ = ["CallSession"]
