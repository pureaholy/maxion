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


# --- vcp: параметры звонка, снятые с живого звонка -------------------------

# Реальный vcp из NOTIF_CALL_START (ru.oneme.app 26.29.1), токены обрезаны.
REAL_VCP = None
try:
    import base64, lz4.block, json as _json
    _cfg = {
        "tkn": "TESTTOKEN=", "wse": "wss://videowebrtc.okcdn.ru/ws2",
        "wsip": ["155.212.204.11"], "wte": "https://videowebrtc.okcdn.ru:23456/wt",
        "vcae": "https://calls.okcdn.ru", "srcp": "one_me", "et": 1788046797,
        "stne": "stun:155.212.199.159:19302",
        "trne": "turn:155.212.199.159:19302,turn:155.212.205.82:19302",
        "trnu": "1788075417:1125900224277751", "trnp": "BOTa/4/dak8=", "iv": False,
    }
    _body = _json.dumps(_cfg).encode()
    _packed = base64.b64encode(lz4.block.compress(_body, store_size=False)).decode()
    REAL_VCP = f"{len(_body)}:{_packed}"
except ImportError:
    pass


@pytest.mark.skipif(REAL_VCP is None, reason="нужен lz4")
def test_parse_vcp_recovers_call_infrastructure():
    from maxion.calls import parse_vcp

    cfg = parse_vcp(REAL_VCP)

    assert cfg.signaling_url == "wss://videowebrtc.okcdn.ru/ws2"
    assert cfg.token == "TESTTOKEN="
    assert cfg.stun == "stun:155.212.199.159:19302"
    assert cfg.turn.startswith("turn:")
    assert cfg.turn_username == "1788075417:1125900224277751"
    assert cfg.api_url == "https://calls.okcdn.ru"
    assert cfg.is_video is False


@pytest.mark.skipif(REAL_VCP is None, reason="нужен lz4")
def test_vcp_produces_aiortc_ice_servers():
    from maxion.calls import parse_vcp

    servers = parse_vcp(REAL_VCP).ice_servers()

    assert {"urls": ["stun:155.212.199.159:19302"]} in servers
    turn = next(s for s in servers if s["urls"][0].startswith("turn:"))
    assert len(turn["urls"]) == 2
    assert turn["username"] == "1788075417:1125900224277751"
    assert turn["credential"] == "BOTa/4/dak8="


# --- протокол сигнализации OK externcalls (снято с живого звонка) ----------


def test_ok_commands_build_client_messages():
    from maxion.calls import Commands, media_settings

    c = Commands()
    accept = c.accept_call()
    assert accept["command"] == "accept-call"
    assert accept["sequence"] == 1
    assert set(accept["mediaSettings"]) == {
        "isAudioEnabled", "isVideoEnabled", "isScreenSharingEnabled",
        "isFastScreenSharingEnabled", "isAudioSharingEnabled",
    }

    # sequence растёт
    assert c.change_media_settings(media_settings(video=True))["sequence"] == 2
    assert c.update_media_modifiers(denoise=True)["sequence"] == 3


def test_ok_transmit_sdp_and_candidate():
    from maxion.calls import Commands

    c = Commands()
    sdp = c.transmit_sdp(1125899939828522, "v=0\r\n", participant_type="USER")
    assert sdp["command"] == "transmit-data"
    assert sdp["participantId"] == 1125899939828522
    assert sdp["data"]["sdp"]["sdp"] == "v=0\r\n"
    assert sdp["data"]["sdp"]["p2pRelay"] is True

    ice = c.transmit_candidate(42, "candidate:1 1 udp ...")
    assert ice["data"]["candidate"]["candidate"].startswith("candidate:")


def test_ok_parse_incoming_sdp():
    from maxion.calls import parse_message

    # форма из реального дампа
    msg = parse_message({
        "stamp": 1788047236751000001,
        "peerId": {"id": 41827132202, "type": "WEB_TRANSPORT"},
        "data": {"sdp": {"type": "offer", "sdp": "v=0\r\no=- 1 2 IN IP4 127.0.0.1\r\n"}},
    })
    assert msg.peer_id == 41827132202
    assert msg.peer_type == "WEB_TRANSPORT"
    assert msg.sdp["type"] == "offer"
    assert msg.sdp["sdp"].startswith("v=0")
    assert msg.candidate is None


def test_ok_parse_incoming_candidate():
    from maxion.calls import parse_message

    msg = parse_message({
        "stamp": 1788047236751000002,
        "peerId": {"id": 41827132202, "type": "WEB_TRANSPORT"},
        "data": {"candidate": {"candidate": "candidate:468136283 1 udp 658217562 1.2.3.4 43210 typ host"}},
    })
    assert msg.candidate.startswith("candidate:468136283")
    assert msg.sdp is None


def test_ok_custom_data_carries_stats():
    from maxion.calls import Commands

    msg = Commands().custom_data({"sdk": {"rtt": 0.0, "loss": 0.0}})
    assert msg["command"] == "custom-data"
    assert msg["data"]["sdk"]["rtt"] == 0.0


# --- Call: замыкание сигнализации на медиа ---------------------------------

@requires_aiortc
async def test_call_routes_server_sdp_into_media_and_answers_back():
    """Входящий offer из канала -> WebRTC -> answer уходит через transmit-data.

    Канал и медиа настоящие (aiortc), но сокета нет: подменяем OkRtcChannel
    накопителем отправленных команд и вручную подаём сообщения сервера.
    """
    from maxion.calls import CallConfig
    from maxion.calls.call import Call
    from maxion.calls.okrtc import Commands, parse_message
    from aiortc import RTCPeerConnection
    from aiortc.mediastreams import AudioStreamTrack

    class FakeChannel:
        def __init__(self):
            self.commands = Commands()
            self.sent = []
        async def send(self, m): self.sent.append(m)
        async def close(self): pass

    cfg = CallConfig(token="t", signaling_url="wss://x/ws2")
    call = Call(cfg, conversation_id="c1", peer_id=7)

    # готовим сессию и подменённый канал вручную (минуя сеть)
    from maxion.calls.session import CallSession
    call.session = CallSession(on_signal=call._on_local_signal)
    call.session.add_track(AudioStreamTrack())
    call.channel = FakeChannel()

    # генерим настоящий offer другой сессией и подаём его как серверный
    offerer = RTCPeerConnection()
    offerer.addTrack(AudioStreamTrack())
    offer = await offerer.createOffer()
    await offerer.setLocalDescription(offer)

    server_msg = parse_message({
        "peerId": {"id": 41827132202, "type": "WEB_TRANSPORT"},
        "data": {"sdp": {"type": "offer", "sdp": offerer.localDescription.sdp}},
    })
    await call._handle(server_msg)

    # answer должен уйти в канал командой transmit-data с data.sdp
    sdp_out = [m for m in call.channel.sent if m.get("command") == "transmit-data"
               and "sdp" in m.get("data", {})]
    assert sdp_out, "answer не ушёл в канал"
    assert sdp_out[0]["participantId"] == 41827132202
    assert sdp_out[0]["participantType"] == "WEB_TRANSPORT"
    assert sdp_out[0]["data"]["sdp"]["sdp"].startswith("v=0")

    await offerer.close()
    await call.session.close()


@requires_aiortc
async def test_call_feeds_ice_candidate_from_channel():
    from maxion.calls import CallConfig
    from maxion.calls.call import Call
    from maxion.calls.okrtc import Commands, parse_message
    from maxion.calls.session import CallSession

    class FakeChannel:
        def __init__(self): self.commands = Commands(); self.sent = []
        async def send(self, m): self.sent.append(m)
        async def close(self): pass

    call = Call(CallConfig(token="t", signaling_url="wss://x/ws2"),
                conversation_id="c1", peer_id=7)
    call.session = CallSession(on_signal=call._on_local_signal)
    call.channel = FakeChannel()

    # ICE до SDP — aiortc буферизует, ошибки быть не должно
    msg = parse_message({
        "peerId": {"id": 42, "type": "USER"},
        "data": {"candidate": {"candidate":
            "candidate:1 1 udp 2130706431 192.0.2.1 12345 typ host"}},
    })
    await call._handle(msg)          # не должно бросить
    assert call._remote_participant == 42
    await call.session.close()


def test_incoming_call_builds_from_notif(monkeypatch):
    """Call.incoming собирает звонок из NOTIF_CALL_START с vcp."""
    from maxion.calls import CallConfig
    from maxion.calls.call import Call

    class FakeStart:
        conversation_id = "conv-1"
        caller_id = 199383792
        is_video = False
        def config(self):
            return CallConfig(token="tok", signaling_url="wss://videowebrtc.okcdn.ru/ws2",
                              stun="stun:1.2.3.4:19302")

    call = Call.incoming(FakeStart())
    assert call.conversation_id == "conv-1"
    assert call.peer_id == 199383792
    assert call.config.signaling_url.endswith("/ws2")
