"""Тесты клиента на поддельном транспорте."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from maxion.raw import MaxClient, Router, filters
from maxion.raw.errors import RpcError
from maxion.raw.opcodes import Opcode
from maxion.raw.protocol import Packet
from maxion.raw.transport.base import BaseTransport


class FakeTransport(BaseTransport):
    """Транспорт, который отвечает по заранее заданной таблице."""

    rpc_version = 11
    device_type = "WEB"

    def __init__(self, responses: dict[int, dict[str, Any]] | None = None):
        self.responses = responses or {}
        self.sent: list[Packet] = []
        self.incoming: asyncio.Queue[Packet] = asyncio.Queue()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def close(self) -> None:
        self._connected = False

    async def send(self, packet: Packet) -> None:
        self.sent.append(packet)
        payload = self.responses.get(packet.opcode, {})
        cmd = 3 if "error" in payload else 1
        await self.incoming.put(
            Packet(opcode=packet.opcode, payload=payload, seq=packet.seq, cmd=cmd)
        )

    async def recv(self) -> Packet:
        return await self.incoming.get()

    def push(self, packet: Packet) -> None:
        """Имитирует событие от сервера."""
        self.incoming.put_nowait(packet)


@pytest.fixture
async def client():
    transport = FakeTransport(
        {
            Opcode.SESSION_INIT: {"isVpn": False},
            Opcode.MSG_SEND: {
                "chatId": -1,
                "message": {"id": "42", "chatId": -1, "text": "привет", "sender": 7},
            },
            Opcode.CHATS_LIST: {
                "marker": 0,
                "chats": [{"id": -1, "type": "CHAT", "title": "Тест"}],
            },
            Opcode.CHAT_JOIN: {"error": "chat.not.found", "message": "нет такого чата"},
        }
    )
    client = MaxClient(transport=transport, ping_interval=0, auto_reconnect=False)
    await client.connect()
    try:
        yield client
    finally:
        await client.disconnect()


async def test_session_init_is_sent_on_connect(client):
    transport: FakeTransport = client.transport  # type: ignore[assignment]
    assert transport.sent[0].opcode == Opcode.SESSION_INIT
    assert transport.sent[0].payload["deviceId"] == client.session.device_id


async def test_send_message_builds_payload(client):
    message = await client.send_message(-1, "привет")
    assert message.id == "42"
    assert message.text == "привет"

    sent = client.transport.sent[-1]  # type: ignore[attr-defined]
    assert sent.opcode == Opcode.MSG_SEND
    assert sent.payload["chatId"] == -1
    assert sent.payload["message"]["text"] == "привет"
    assert isinstance(sent.payload["message"]["cid"], int)
    assert sent.payload["notify"] is True


async def test_reply_sets_link(client):
    await client.send_message(-1, "ответ", reply_to="99")
    link = client.transport.sent[-1].payload["message"]["link"]  # type: ignore[attr-defined]
    assert link == {"type": "REPLY", "messageId": "99"}


async def test_markdown_produces_elements(client):
    await client.send_message(-1, "это **важно**", markdown=True)
    message = client.transport.sent[-1].payload["message"]  # type: ignore[attr-defined]
    assert message["text"] == "это важно"
    assert message["elements"] == [{"type": "STRONG", "from": 4, "length": 5}]


async def test_get_chats_parses_and_caches(client):
    chats, marker = await client.get_chats()
    assert marker is None
    assert chats[0].title == "Тест"
    assert chats[0].is_group
    assert client.chats_cache[-1].title == "Тест"


async def test_rpc_error_raised(client):
    with pytest.raises(RpcError) as info:
        await client.join_chat("https://max.ru/nope")
    assert info.value.code == "chat.not.found"
    assert "нет такого чата" in str(info.value)


async def test_router_receives_message_event(client):
    seen: list[str] = []
    router = Router()

    @router.on_message(filters.contains("пинг"))
    async def handler(update):
        seen.append(update.text)

    client.include_router(router)
    client.transport.push(  # type: ignore[attr-defined]
        Packet(
            opcode=Opcode.NOTIF_MESSAGE,
            cmd=1,
            seq=0,
            payload={"chatId": -1, "message": {"id": "1", "text": "пинг!", "sender": 5}},
        )
    )
    for _ in range(20):
        await asyncio.sleep(0.01)
        if seen:
            break
    assert seen == ["пинг!"]


async def test_filter_skips_non_matching(client):
    seen: list[str] = []
    router = Router()

    @router.on_message(filters.command("start"))
    async def handler(update):
        seen.append(update.text)

    client.include_router(router)
    client.transport.push(  # type: ignore[attr-defined]
        Packet(
            opcode=Opcode.NOTIF_MESSAGE,
            cmd=1,
            seq=0,
            payload={"chatId": -1, "message": {"id": "2", "text": "просто текст"}},
        )
    )
    await asyncio.sleep(0.05)
    assert seen == []


async def test_call_by_opcode_name(client):
    await client.call("PING", {"interactive": False})
    assert client.transport.sent[-1].opcode == Opcode.PING  # type: ignore[attr-defined]


async def test_mute_chat_payload(client):
    client.transport.responses[Opcode.CONFIG] = {"hash": "x"}  # type: ignore[attr-defined]
    await client.mute_chat(-500, -1)
    payload = client.transport.sent[-1].payload  # type: ignore[attr-defined]
    assert payload == {"settings": {"chats": {"-500": {"dontDisturbUntil": -1}}}}
