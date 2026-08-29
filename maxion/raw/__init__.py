"""maxion.raw — низкоуровневый слой: протокол MAX без обёрток.

Здесь всё, что снято с приложения: кадры, 176 опкодов, транспорты и
методы один-в-один с протоколом. Удобный слой поверх — в :mod:`maxion`.

    import asyncio
    from maxion.raw import MaxClient, filters

    client = MaxClient("my.session")

    @client.on_message(filters.command("ping"))
    async def ping(update):
        await update.reply("pong")

    async def main():
        await client.start(phone="+79991234567")
        await client.run_until_disconnected()

    asyncio.run(main())
"""

from . import enums, errors, filters
from .client import MaxClient
from .const import TCP_HOST, WS_URL
from .device import Device
from .enums import (
    AccessType,
    AttachType,
    AuthType,
    ChatType,
    ContactUpdateAction,
    ElementType,
    MarkType,
    MemberType,
    PushDeviceType,
    ReactionType,
)
from .errors import (
    AuthError,
    MaxError,
    NotAuthorizedError,
    NotConnectedError,
    ProtocolError,
    RpcError,
    SessionExpiredError,
    TransportError,
    TwoFactorRequired,
)
from .events import Update, parse_update
from .opcodes import Opcode, opcode_name
from .protocol import Packet
from .router import Router
from .session import Session
from .transport import BaseTransport, TcpTransport, WebSocketTransport
from .types import (
    Attach,
    Chat,
    Folder,
    Member,
    Message,
    Presence,
    Profile,
    Reaction,
    Sticker,
    Story,
    User,
)
from .utils import Text, parse_markdown

__version__ = "0.1.0"

__all__ = [
    "MaxClient",
    "Session",
    "Device",
    "Router",
    "Opcode",
    "opcode_name",
    "Packet",
    "Update",
    "parse_update",
    "Text",
    "parse_markdown",
    "filters",
    "enums",
    "errors",
    "WS_URL",
    "TCP_HOST",
    "BaseTransport",
    "WebSocketTransport",
    "TcpTransport",
    # типы
    "User",
    "Profile",
    "Chat",
    "Member",
    "Folder",
    "Message",
    "Attach",
    "Reaction",
    "Presence",
    "Sticker",
    "Story",
    # перечисления
    "AttachType",
    "ChatType",
    "MemberType",
    "MarkType",
    "AccessType",
    "AuthType",
    "ElementType",
    "ReactionType",
    "PushDeviceType",
    "ContactUpdateAction",
    # ошибки
    "MaxError",
    "RpcError",
    "AuthError",
    "NotAuthorizedError",
    "NotConnectedError",
    "SessionExpiredError",
    "TwoFactorRequired",
    "TransportError",
    "ProtocolError",
]
