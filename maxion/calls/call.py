"""Высокоуровневый звонок: сигнализация + медиа в одном объекте.

Замыкает всю цепочку, разобранную с живого звонка:

    NOTIF_CALL_START -> vcp -> OkRtcChannel (/ws2) -> CallSession (WebRTC)

:class:`Call` соединяет канал сигнализации OK (:mod:`maxion.calls.okrtc`) с
медиа-сессией aiortc (:mod:`maxion.calls.session`): SDP и ICE, полученные из
канала, скармливаются в WebRTC, а встречные — уходят обратно командой
``transmit-data``. Требует extra ``maxion[calls]``.

Пример приёма входящего звонка::

    @app.raw.router.on("call")
    async def on_call(update):
        call = Call.incoming(update)          # из NOTIF_CALL_START
        await call.answer(audio="mic.wav")    # поднять и говорить
        await call.wait_hangup()

Сценарий проверяется на живом звонке; здесь — рабочий каркас на готовых,
сверенных с дампом форматах.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .okrtc import Commands, OkRtcChannel, OkRtcMessage
from .session import CallSession
from .signaling import CallConfig

log = logging.getLogger(__name__)


class Call:
    """Один звонок: канал сигнализации + медиа-сессия WebRTC."""

    def __init__(
        self,
        config: CallConfig,
        *,
        conversation_id: str,
        peer_id: int,
        video: bool = False,
    ):
        self.config = config
        self.conversation_id = conversation_id
        self.peer_id = peer_id
        self.video = video

        self.channel: OkRtcChannel | None = None
        self.session: CallSession | None = None
        self._pump: asyncio.Task | None = None
        self._hangup = asyncio.Event()
        #: id участника, которому шлём SDP/ICE (узнаётся из первого сообщения).
        self._remote_participant: int | None = None
        self._remote_type: str = "USER"

    # --- конструкторы ------------------------------------------------------

    @classmethod
    def incoming(cls, call_start) -> "Call":
        """Собирает звонок из события NOTIF_CALL_START.

        ``call_start`` — объект :class:`~maxion.raw.events.CallStart`.
        """
        config = call_start.config()
        if config is None:
            raise ValueError("в NOTIF_CALL_START нет vcp — нечего разбирать")
        return cls(
            config,
            conversation_id=call_start.conversation_id,
            peer_id=call_start.caller_id or 0,
            video=call_start.is_video,
        )

    # --- поднятие звонка ---------------------------------------------------

    async def answer(
        self,
        *,
        audio: Any = None,
        microphone: bool = False,
        camera: bool = False,
        media_file: str | None = None,
    ) -> None:
        """Отвечает на звонок и начинает медиа-обмен.

        :param audio: файл или aiortc-трек как источник звука; ``None`` —
            без исходящего звука (только слушать).
        :param microphone: взять звук с микрофона.
        :param camera: добавить видео с камеры (видео-звонок). Протокол тот же,
            сервер согласует VP8/H264.
        :param media_file: взять аудио и видео из одного файла (ролик).
        """
        self.session = CallSession(
            ice_servers=self.config.ice_servers(),
            on_signal=self._on_local_signal,
        )
        if media_file:
            await self.session.add_media_file(media_file)
            self.video = True
        else:
            if microphone:
                await self.session.add_microphone()
            elif audio is not None:
                self._add_audio_source(audio)
            if camera:
                await self.session.add_camera()
                self.video = True

        self.channel = await OkRtcChannel.connect(
            self.config,
            conversation_id=self.conversation_id,
            peer_id=self.peer_id,
            tgt="accept",
        )
        # принять звонок и объявить медиа-настройки
        await self.channel.send(self.channel.commands.accept_call())
        from .okrtc import media_settings

        await self.channel.send(
            self.channel.commands.change_media_settings(
                media_settings(audio=True, video=self.video)
            )
        )
        self._pump = asyncio.create_task(self._recv_loop(), name="maxion-call")

    # --- обмен сигнализацией ----------------------------------------------

    async def _recv_loop(self) -> None:
        assert self.channel and self.session
        try:
            async for msg in self.channel:
                await self._handle(msg)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("ошибка в цикле сигнализации звонка")
        finally:
            self._hangup.set()

    async def _handle(self, msg: OkRtcMessage) -> None:
        assert self.session
        if msg.peer_id and self._remote_participant is None:
            self._remote_participant = msg.peer_id
            if msg.peer_type:
                self._remote_type = msg.peer_type

        if msg.sdp:
            # сервер прислал offer/answer -> в WebRTC; на offer вернём answer
            answer = await self.session.feed_signal(
                {"type": "SDP", "sdp": msg.sdp["sdp"], "sdpType": msg.sdp["type"]}
            )
            if answer is not None:
                await self._send_sdp(answer.sdp)
        elif msg.candidate:
            await self.session.feed_signal(
                {"type": "CANDIDATE", "candidate": msg.candidate}
            )

    def _on_local_signal(self, message: dict[str, Any]) -> Any:
        """CallSession отдаёт наружу свои SDP/ICE — заворачиваем в transmit-data."""
        if self.channel is None or self._remote_participant is None:
            return None
        kind = message.get("type")
        if kind == "SDP":
            return self._send_sdp(message["sdp"])
        if kind == "CANDIDATE":
            return self._send_candidate(message["candidate"])
        return None

    async def _send_sdp(self, sdp: str) -> None:
        assert self.channel and self._remote_participant is not None
        await self.channel.send(
            self.channel.commands.transmit_sdp(
                self._remote_participant, sdp, participant_type=self._remote_type
            )
        )

    async def _send_candidate(self, candidate: str) -> None:
        assert self.channel and self._remote_participant is not None
        await self.channel.send(
            self.channel.commands.transmit_candidate(
                self._remote_participant, candidate, participant_type=self._remote_type
            )
        )

    # --- жизненный цикл ----------------------------------------------------

    async def wait_hangup(self) -> None:
        """Ждёт завершения звонка."""
        await self._hangup.wait()

    async def hangup(self) -> None:
        """Завершает звонок и освобождает ресурсы."""
        self._hangup.set()
        if self._pump:
            self._pump.cancel()
        if self.session:
            await self.session.close()
        if self.channel:
            await self.channel.close()

    async def __aenter__(self) -> "Call":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.hangup()

    # --- внутреннее --------------------------------------------------------

    def _add_audio_source(self, audio: Any) -> None:
        assert self.session
        if isinstance(audio, str):
            from aiortc.contrib.media import MediaPlayer

            player = MediaPlayer(audio)
            if player.audio:
                self.session.add_track(player.audio)
        else:
            self.session.add_track(audio)


__all__ = ["Call"]
