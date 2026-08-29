"""Тесты кадрирования и разметки."""

from __future__ import annotations

import json

import pytest

from maxion.raw.opcodes import Opcode, opcode_name
from maxion.raw.protocol import Packet
from maxion.raw.utils import Text, next_cid, normalize_phone, parse_markdown

# Реальный кадр START_AUTH из дампа мобильного клиента.
REAL_FRAME = bytes.fromhex(
    "0a00000700110000003083a570686f6e65ac2b3739393939393939393939"
    "a474797065aa53544152545f41555448a86c616e6775616765a27275"
)


def test_parse_real_frame():
    packet = Packet.from_bytes(REAL_FRAME)
    assert packet.ver == 10
    assert packet.cmd == 0
    assert packet.seq == 7
    assert packet.opcode == Opcode.AUTH_REQUEST
    assert packet.payload == {
        "phone": "+79999999999",
        "type": "START_AUTH",
        "language": "ru",
    }


def test_binary_roundtrip_is_byte_exact():
    packet = Packet.from_bytes(REAL_FRAME)
    rebuilt = Packet(
        opcode=packet.opcode, payload=packet.payload, seq=7, cmd=0, ver=10
    ).to_bytes(compress=False)
    assert rebuilt == REAL_FRAME


def test_compression_roundtrip():
    payload = {"text": "я" * 500, "ids": list(range(200))}
    raw = Packet(opcode=Opcode.MSG_SEND, payload=payload, seq=1, ver=10).to_bytes()
    assert raw[6] != 0, "большой payload должен сжаться"
    assert len(raw) < 500
    assert Packet.from_bytes(raw).payload == payload


def test_parse_stream_handles_partial_and_multiple():
    first = Packet(opcode=1, payload={"a": 1}, seq=1, ver=10).to_bytes()
    second = Packet(opcode=2, payload={"b": 2}, seq=2, ver=10).to_bytes()
    stream = first + second

    packet, consumed = Packet.parse_stream(stream[: len(first) - 1])
    assert packet is None and consumed == 0

    packet, consumed = Packet.parse_stream(stream)
    assert packet.opcode == 1 and consumed == len(first)
    packet, consumed = Packet.parse_stream(stream[consumed:])
    assert packet.opcode == 2 and consumed == len(second)


def test_json_frame():
    packet = Packet(opcode=64, payload={"chatId": 5}, seq=3, cmd=0, ver=11)
    assert json.loads(packet.to_json()) == {
        "ver": 11,
        "cmd": 0,
        "seq": 3,
        "opcode": 64,
        "payload": {"chatId": 5},
    }
    assert Packet.from_json(packet.to_json()) == packet


def test_error_detection():
    assert Packet(opcode=64, payload={}, cmd=3).is_error
    assert Packet(opcode=64, payload={"error": "flood"}, cmd=1).is_error
    assert not Packet(opcode=64, payload={"ok": 1}, cmd=1).is_error


def test_opcode_name_for_unknown():
    assert opcode_name(64) == "MSG_SEND"
    assert opcode_name(9999) == "UNKNOWN_9999"


def test_normalize_phone():
    assert normalize_phone("8 (999) 123-45-67") == "+79991234567"
    assert normalize_phone("+7 999 123 45 67") == "+79991234567"
    with pytest.raises(ValueError):
        normalize_phone("не номер")


def test_cid_is_monotonic():
    values = [next_cid() for _ in range(5)]
    assert values == sorted(values)
    assert len(set(values)) == len(values)


def test_text_builder():
    text = Text("Привет, ").bold("мир").text("! ").link("док", "https://max.ru")
    assert text.value == "Привет, мир! док"
    assert text.elements == [
        {"type": "STRONG", "from": 8, "length": 3},
        {"type": "LINK", "from": 13, "length": 3, "url": "https://max.ru"},
    ]


def test_parse_markdown():
    body, elements = parse_markdown("это **жирно** и `код`")
    assert body == "это жирно и код"
    kinds = {e["type"] for e in elements}
    assert kinds == {"STRONG", "MONOSPACED"}
    strong = next(e for e in elements if e["type"] == "STRONG")
    assert body[strong["from"] : strong["from"] + strong["length"]] == "жирно"
    mono = next(e for e in elements if e["type"] == "MONOSPACED")
    assert body[mono["from"] : mono["from"] + mono["length"]] == "код"


def test_parse_markdown_link():
    body, elements = parse_markdown("см. [доки](https://max.ru) тут")
    assert body == "см. доки тут"
    link = elements[0]
    assert link["url"] == "https://max.ru"
    assert body[link["from"] : link["from"] + link["length"]] == "доки"
