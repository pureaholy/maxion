"""Реакции на сообщения."""

from __future__ import annotations

from typing import Any

from ..enums import ReactionType
from ..opcodes import Opcode
from ..types import ReactionInfo
from ..utils import clean
from .base import MethodsBase


class ReactionMethods(MethodsBase):
    """Опкоды 178-181."""

    async def set_reaction(
        self,
        chat_id: int,
        message_id: str,
        reaction: str = "❤️",
        *,
        reaction_type: ReactionType | str = ReactionType.EMOJI,
        post_id: int | None = None,
    ) -> ReactionInfo | None:
        """MSG_REACTION (178). Ставит реакцию.

        Для стикер-реакции: ``reaction_type=ReactionType.STICKER``,
        ``reaction`` — id стикера строкой.
        """
        payload = await self.invoke(
            Opcode.MSG_REACTION,
            clean(
                {
                    "chatId": chat_id,
                    "messageId": str(message_id),
                    "postId": post_id,
                    "reaction": {
                        "reactionType": str(reaction_type),
                        "id": str(reaction),
                    },
                }
            ),
        )
        return ReactionInfo.parse(payload.get("reactionInfo"), self)  # type: ignore[arg-type]

    async def remove_reaction(
        self, chat_id: int, message_id: str, *, post_id: int | None = None
    ) -> ReactionInfo | None:
        """MSG_CANCEL_REACTION (179)."""
        payload = await self.invoke(
            Opcode.MSG_CANCEL_REACTION,
            clean({"chatId": chat_id, "messageId": str(message_id), "postId": post_id}),
        )
        return ReactionInfo.parse(payload.get("reactionInfo"), self)  # type: ignore[arg-type]

    async def get_reactions(
        self,
        chat_id: int,
        message_ids: list[str] | str,
        *,
        post_id: int | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """MSG_GET_REACTIONS (180). Сводка реакций."""
        if isinstance(message_ids, str):
            message_ids = [message_ids]
        return await self.invoke(
            Opcode.MSG_GET_REACTIONS,
            clean(
                {
                    "chatId": chat_id,
                    "messageIds": [str(m) for m in message_ids],
                    "postId": post_id,
                    **extra,
                }
            ),
        )

    async def get_detailed_reactions(
        self, chat_id: int, message_id: str, *, count: int = 50, **extra: Any
    ) -> dict[str, Any]:
        """MSG_GET_DETAILED_REACTIONS (181). Кто именно поставил реакцию."""
        return await self.invoke(
            Opcode.MSG_GET_DETAILED_REACTIONS,
            clean(
                {
                    "chatId": chat_id,
                    "messageId": str(message_id),
                    "count": count,
                    **extra,
                }
            ),
        )
