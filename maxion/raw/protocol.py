"""Кадрирование протокола MAX.

Два представления одного и того же RPC:

* **JSON** — web-клиент (``wss://ws-api.oneme.ru/websocket``);
* **binary** — мобильные и десктопные клиенты (TLS на ``api.oneme.ru:443``):

  ``[ver:1][cmd:1][seq:2][opcode:2][cof:1][len:3][payload:len]``

  payload кодируется MsgPack, а при длине больше
  :data:`~maxion.raw.const.COMPRESS_THRESHOLD` сжимается LZ4 (raw block).
  Байт ``cof`` — коэффициент сжатия ``floor(raw / packed) + 1``; 0 означает,
  что сжатия нет. При распаковке важен лишь факт ``cof != 0``, само значение
  используется как подсказка о размере выходного буфера.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from typing import Any

from .const import COMPRESS_THRESHOLD, HEADER_SIZE
from .enums import Cmd
from .errors import ProtocolError
from .opcodes import opcode_name

_HEADER = struct.Struct(">BBHHB")  # ver, cmd, seq, opcode, cof (7 байт) + len(3)


@dataclass(slots=True)
class Packet:
    """Один кадр протокола."""

    opcode: int
    payload: dict[str, Any] = field(default_factory=dict)
    seq: int = 0
    cmd: int = int(Cmd.REQUEST)
    ver: int = 11

    # --- свойства ----------------------------------------------------------

    @property
    def name(self) -> str:
        return opcode_name(self.opcode)

    @property
    def is_error(self) -> bool:
        return self.cmd == int(Cmd.ERROR) or (
            isinstance(self.payload, dict) and "error" in self.payload
        )

    @property
    def is_response(self) -> bool:
        return self.cmd == int(Cmd.RESPONSE)

    def __repr__(self) -> str:  # pragma: no cover - отладка
        return (
            f"<Packet {self.name} seq={self.seq} cmd={self.cmd} "
            f"payload={self.payload!r}>"
        )

    # --- JSON --------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "ver": self.ver,
            "cmd": self.cmd,
            "seq": self.seq,
            "opcode": self.opcode,
            "payload": self.payload,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Packet":
        if not isinstance(data, dict):
            raise ProtocolError(f"Ожидался объект, получено {type(data).__name__}")
        try:
            return cls(
                ver=int(data.get("ver", 11)),
                cmd=int(data.get("cmd", 1)),
                seq=int(data.get("seq", 0)),
                opcode=int(data["opcode"]),
                payload=data.get("payload") or {},
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProtocolError(f"Неверный кадр: {data!r}") from exc

    @classmethod
    def from_json(cls, raw: str | bytes) -> "Packet":
        try:
            return cls.from_dict(json.loads(raw))
        except json.JSONDecodeError as exc:
            raise ProtocolError("Кадр не является валидным JSON") from exc

    # --- binary ------------------------------------------------------------

    def to_bytes(self, *, compress: bool = True) -> bytes:
        """Сериализует кадр в бинарный формат мобильного клиента."""
        raw = _msgpack().packb(self.payload, use_bin_type=True)
        cof, body = 0, raw
        if compress and len(raw) > COMPRESS_THRESHOLD:
            packed = _lz4().compress(raw, store_size=False)
            if len(packed) < len(raw):
                body = packed
                cof = min(255, len(raw) // max(1, len(packed)) + 1)
        if len(body) > 0xFFFFFF:
            raise ProtocolError("Payload превышает 16 МиБ")
        header = _HEADER.pack(
            self.ver & 0xFF,
            self.cmd & 0xFF,
            self.seq & 0xFFFF,
            self.opcode & 0xFFFF,
            cof,
        )
        return header + len(body).to_bytes(3, "big") + body

    @classmethod
    def from_bytes(cls, data: bytes) -> "Packet":
        """Разбирает бинарный кадр целиком (без остатка)."""
        packet, consumed = cls.parse_stream(data)
        if packet is None:
            raise ProtocolError("Кадр неполный")
        if consumed != len(data):
            raise ProtocolError("В буфере остались лишние байты")
        return packet

    @classmethod
    def parse_stream(cls, buffer: bytes) -> tuple["Packet | None", int]:
        """Пытается вынуть один кадр из потока.

        :returns: ``(пакет | None, сколько байт израсходовано)``.
        """
        if len(buffer) < HEADER_SIZE:
            return None, 0
        ver, cmd, seq, opcode, cof = _HEADER.unpack_from(buffer, 0)
        length = int.from_bytes(buffer[7:HEADER_SIZE], "big")
        total = HEADER_SIZE + length
        if len(buffer) < total:
            return None, 0
        body = bytes(buffer[HEADER_SIZE:total])
        if not body:
            # Пустое тело — законный ответ, а не обрыв: так сервер отвечает,
            # например, на PING. Снято с живого api.oneme.ru, кадр целиком:
            # 0a 01 0002 0001 00 000000.
            return cls(ver=ver, cmd=cmd, seq=seq, opcode=opcode, payload={}), total
        if cof:
            body = _lz4_decompress(body, cof)
        try:
            payload = _msgpack().unpackb(body, raw=False, strict_map_key=False)
        except Exception as exc:  # msgpack бросает разные типы
            raise ProtocolError(f"Не удалось распаковать payload: {exc}") from exc
        if not isinstance(payload, dict):
            payload = {"_": payload}
        return cls(ver=ver, cmd=cmd, seq=seq, opcode=opcode, payload=payload), total


def _lz4_decompress(body: bytes, cof: int) -> bytes:
    """LZ4 raw-block без сохранённого размера: подбираем размер буфера."""
    lz4 = _lz4()
    guess = max(len(body) * max(cof, 2), 1024)
    last: Exception | None = None
    while guess <= 64 * 1024 * 1024:
        try:
            return lz4.decompress(body, uncompressed_size=guess)
        except Exception as exc:  # LZ4BlockError
            last = exc
            guess *= 2
    raise ProtocolError(f"LZ4: не удалось распаковать payload ({last})")


# --- ленивые зависимости ---------------------------------------------------

def _msgpack():
    try:
        import msgpack  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ProtocolError(
            "Для бинарного протокола нужен пакет msgpack: pip install msgpack"
        ) from exc
    return msgpack


def _lz4():
    try:
        import lz4.block as block  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ProtocolError(
            "Для бинарного протокола нужен пакет lz4: pip install lz4"
        ) from exc
    return block
