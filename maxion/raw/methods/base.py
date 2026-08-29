"""Базовый класс для миксинов с методами API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from ..opcodes import Opcode

if TYPE_CHECKING:  # pragma: no cover
    from ..session import Session


class MethodsBase(Protocol):
    """То, что миксины ожидают от клиента.

    Реализуется в :class:`maxion.raw.client.MaxClient`; вынесено отдельно,
    чтобы миксины оставались независимыми и проверялись типами.
    """

    session: "Session"

    async def invoke(
        self,
        opcode: Opcode | int,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Отправляет запрос и возвращает payload ответа."""
        ...

    async def notify(
        self, opcode: Opcode | int, payload: dict[str, Any] | None = None
    ) -> None:
        """Отправляет запрос, не дожидаясь ответа."""
        ...

    @property
    def user_id(self) -> int | None: ...
