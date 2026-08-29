"""Служебные опкоды и «сырой» доступ к любому методу."""

from __future__ import annotations

from typing import Any

from ..opcodes import Opcode
from ..utils import clean
from .base import MethodsBase


class MiscMethods(MethodsBase):
    """Опкоды 1-5, 158 и универсальный вызов."""

    async def ping(self, interactive: bool = False) -> dict[str, Any]:
        """PING (1). Держит соединение живым."""
        return await self.invoke(Opcode.PING, {"interactive": interactive})

    async def debug(self, cmd: str, args: list[str] | None = None) -> dict[str, Any]:
        """DEBUG (2). Отладочная команда клиента."""
        return await self.invoke(Opcode.DEBUG, clean({"cmd": cmd, "args": args or []}))

    async def send_log(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        """LOG (5). Клиентская телеметрия."""
        return await self.invoke(Opcode.LOG, {"events": events})

    async def get_ok_token(self, **payload: Any) -> dict[str, Any]:
        """OK_TOKEN (158). Токен для сервисов Одноклассников.

        Схема запроса неизвестна: поля передавайте как есть. Точные имена
        видны в дампе трафика собственного клиента.
        """
        return await self.invoke(Opcode.OK_TOKEN, clean(payload))

    # --- сырой доступ ------------------------------------------------------

    async def call(
        self,
        opcode: Opcode | int | str,
        payload: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Вызывает произвольный опкод — по числу, имени или :class:`Opcode`.

        Полезно, когда метод нашёлся в приложении раньше, чем появился здесь::

            await client.call("CHAT_SUGGEST", {"count": 10})
            await client.call(300, {"count": 10})
        """
        if isinstance(opcode, str):
            opcode = Opcode[opcode.upper()]
        merged = dict(payload or {})
        merged.update(kwargs)
        return await self.invoke(int(opcode), merged)
