"""Медиа-слой звонков: сигнальные форматы и сессия на aiortc."""

from __future__ import annotations

import asyncio

import pytest

from maxion.calls import IceSignal, SdpSignal, ice_servers_from, parse_signal
from maxion.calls.signaling import SignalType

try:
    import aiortc  # noqa: F401
    HAS_AIORTC = True
except ImportError:
    HAS_AIORTC = False

requires_aiortc = pytest.mark.skipif(
    not HAS_AIORTC, reason='нужен extra maxion[calls] (aiortc)'
)


# --- форматы сигналов (снято с APK 26.29.1) --------------------------------


def test_sdp_signal_uses_client_field_names():
    signal = SdpSignal(sdp="v=0\r\n", sdp_type="offer", label="cam", p2p_relay=True)
    data = signal.to_json()

    assert data["type"] == "SDP"
    assert data["sdp"] == "v=0\r\n"
    assert data["sdpType"] == "offer"
    assert data["label"] == "cam"
    assert data["p2pRelay"] is True


def test_sdp_signal_roundtrip_keeps_unknown_fields():
    data = {"type": "SDP", "sdp": "x", "sdpType": "answer", "capabilities": 3, "vcp": 1}
    signal = SdpSignal.from_json(data)

    assert signal.sdp_type == "answer"
    assert signal.capabilities == 3
    assert signal.extra == {"vcp": 1}
    assert signal.to_json()["vcp"] == 1


def test_ice_signal_uses_client_field_names():
    signal = IceSignal(candidate="candidate:1 1 udp ...", sdp_mid="0", sdp_mline_index=0)
    data = signal.to_json()

    assert data["type"] == "CANDIDATE"
    assert data["candidate"].startswith("candidate:")
    assert data["sdpMid"] == "0"
    assert data["sdpMLineIndex"] == 0


def test_parse_signal_dispatches_by_type():
    assert isinstance(parse_signal({"type": "SDP", "sdp": "x"}), SdpSignal)
    assert isinstance(parse_signal({"type": "CANDIDATE", "candidate": "c"}), IceSignal)
    # по наличию поля, даже если type не проставлен
    assert isinstance(parse_signal({"sdp": "x"}), SdpSignal)
    assert isinstance(parse_signal({"candidate": "c"}), IceSignal)
    # неизвестное — как есть
    unknown = {"type": "SIGNALING", "data": {"cmd": "mute"}}
    assert parse_signal(unknown) == unknown


def test_signal_type_enum_matches_client():
    assert {t.value for t in SignalType} == {"NONE", "SDP", "CANDIDATE", "SIGNALING"}


# --- turnServer -> ICE-серверы ---------------------------------------------


def test_ice_servers_from_various_shapes():
    assert ice_servers_from(None) == []
    assert ice_servers_from("turn:host:3478") == [{"urls": ["turn:host:3478"]}]

    obj = ice_servers_from(
        {"urls": ["turn:a", "turn:b"], "username": "u", "credential": "p"}
    )
    assert obj == [{"urls": ["turn:a", "turn:b"], "username": "u", "credential": "p"}]

    # password маппится в credential
    assert ice_servers_from({"url": "turn:a", "password": "p"}) == [
        {"urls": ["turn:a"], "credential": "p"}
    ]

    # список объектов разворачивается
    two = ice_servers_from([{"urls": "turn:a"}, {"urls": "turn:b"}])
    assert [s["urls"] for s in two] == [["turn:a"], ["turn:b"]]


# --- CallSession на настоящем aiortc ---------------------------------------



@requires_aiortc
async def test_offer_answer_handshake_between_two_sessions():
    """Две сессии обмениваются SDP и ICE через колбэки — как через канал.

    Сервер MAX не участвует: проверяется, что наши сигнальные форматы
    достаточны для реального установления соединения WebRTC.
    """
    from maxion.calls import CallSession

    a_out: list[dict] = []
    b_out: list[dict] = []

    caller = CallSession(on_signal=lambda m: a_out.append(m))
    callee = CallSession(on_signal=lambda m: b_out.append(m))

    # у offer-инициатора должен быть хотя бы один трек
    from aiortc.mediastreams import AudioStreamTrack

    caller.add_track(AudioStreamTrack())
    callee.add_track(AudioStreamTrack())

    try:
        offer = await caller.create_offer()
        assert offer.sdp_type == "offer"
        assert a_out and a_out[0]["type"] == "SDP"

        # передаём offer собеседнику — он сам вернёт answer
        answer = await callee.feed_signal(offer.to_json())
        assert answer is not None and answer.sdp_type == "answer"

        # answer обратно инициатору
        assert await caller.feed_signal(answer.to_json()) is None

        # дожидаемся сбора ICE и соединения
        for _ in range(100):
            await asyncio.sleep(0.05)
            if caller.pc.connectionState == "connected":
                break
        assert caller.pc.connectionState in ("connecting", "connected")
        assert caller.pc.localDescription.type == "offer"
        assert callee.pc.remoteDescription.type == "offer"
    finally:
        await caller.close()
        await callee.close()


@requires_aiortc
async def test_feed_ice_candidate_does_not_raise():
    from maxion.calls import CallSession

    session = CallSession()
    try:
        # кандидат до remote description — aiortc его буферизует
        result = await session.feed_signal(
            {
                "type": "CANDIDATE",
                "candidate": "candidate:1 1 udp 2130706431 192.0.2.1 12345 typ host",
                "sdpMid": "0",
                "sdpMLineIndex": 0,
            }
        )
        assert result is None
    finally:
        await session.close()


@requires_aiortc
async def test_empty_candidate_is_ignored():
    from maxion.calls import CallSession

    session = CallSession()
    try:
        assert await session.feed_signal({"type": "CANDIDATE", "candidate": ""}) is None
    finally:
        await session.close()
