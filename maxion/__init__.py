"""maxion — библиотека-клиент мессенджера MAX.

Работа от лица обычного аккаунта (юзербот), а не через Bot API::

    from maxion import Client, filters

    app = Client("my_account", phone_number="+79991234567")

    @app.on_message(filters.command("start") & filters.private)
    async def start(client, message):
        await message.reply("привет")

    app.run()

Слоя два:

* удобный — :class:`Client`, :mod:`maxion.filters`, :mod:`maxion.types`:
  обработчики с фильтрами, модели с связанными методами, разметка текста;
* низкий — :mod:`maxion.raw`: все 153 опкода внутреннего протокола, кадры и
  транспорты, сверенные с APK ``ru.oneme.app`` 26.29.1. Доступен как
  ``app.raw``, произвольный опкод — через ``app.invoke()``.
"""

from . import bot, enums, errors, filters, handlers, raw, types
from .client import Client, ContinuePropagation, StopPropagation, compose, idle
from .enums import (
    ChatAction,
    ChatMemberStatus,
    ChatType,
    MessageEntityType,
    ParseMode,
    UserStatus,
)
from .errors import FloodWait, RPCError, SessionPasswordNeeded, Unauthorized
from .handlers import (
    DeletedMessagesHandler,
    EditedMessageHandler,
    MessageHandler,
    RawUpdateHandler,
)
from .types import Chat, ChatMember, Dialog, Message, MessageEntity, User

__version__ = "0.1.0"

__all__ = [
    "Client",
    "idle",
    "compose",
    "StopPropagation",
    "ContinuePropagation",
    # модули
    "filters",
    "types",
    "enums",
    "errors",
    "handlers",
    "raw",
    "bot",
    # типы
    "User",
    "Chat",
    "Message",
    "MessageEntity",
    "ChatMember",
    "Dialog",
    # перечисления
    "ChatType",
    "ParseMode",
    "ChatAction",
    "MessageEntityType",
    "UserStatus",
    "ChatMemberStatus",
    # ошибки
    "RPCError",
    "FloodWait",
    "Unauthorized",
    "SessionPasswordNeeded",
    # обработчики
    "MessageHandler",
    "EditedMessageHandler",
    "DeletedMessagesHandler",
    "RawUpdateHandler",
]
