"""Звонки, видеочаты и опросы.

Имена полей сверены с APK ``ru.oneme.app`` 26.29.1.
"""

from __future__ import annotations

from typing import Any

from ..opcodes import Opcode
from ..types import Call
from ..utils import clean
from .base import MethodsBase


class CallMethods(MethodsBase):
    """Опкоды 76, 78, 79, 84, 103, 163-167, 195."""

    async def start_video_chat(
        self, chat_id: int, *, video: bool = True, **extra: Any
    ) -> Call | None:
        """VIDEO_CHAT_START (76)."""
        payload = await self.invoke(
            Opcode.VIDEO_CHAT_START,
            clean({"chatId": chat_id, "isVideo": video, **extra}),
        )
        return Call.parse(payload.get("call") or payload, self)  # type: ignore[arg-type]

    async def get_active_video_chat(
        self,
        chat_id: int | None = None,
        *,
        conversation_id: str | None = None,
        callee_ids: list[int] | None = None,
        video: bool = True,
        internal_params: dict[str, Any] | str | None = None,
    ) -> Call | None:
        """VIDEO_CHAT_START_ACTIVE (78). Начинает звонок людям или в чате.

        Схема сверена с живым звонком ``ru.oneme.app`` 26.29.1::

            conversationId  UUID новой сессии
            calleeIds       кому звоним, список id
            isVideo         аудио или видео
            internalParams  JSON-СТРОКА: {protocolVersion, platform, deviceId,
                            sdkVersion, clientAppKey, capabilities}

        ``internal_params`` можно передать словарём — он сам сериализуется в
        строку, как это делает клиент.
        """
        if isinstance(internal_params, dict):
            import json as _json

            internal_params = _json.dumps(internal_params, separators=(",", ":"))
        payload = await self.invoke(
            Opcode.VIDEO_CHAT_START_ACTIVE,
            clean(
                {
                    "chatId": chat_id,
                    "conversationId": conversation_id,
                    "calleeIds": callee_ids,
                    "isVideo": video,
                    "internalParams": internal_params,
                }
            ),
        )
        return Call.parse(payload.get("call") or payload, self)  # type: ignore[arg-type]

    async def join_video_chat(
        self,
        join_link: str,
        *,
        video: bool = True,
        internal_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """VIDEO_CHAT_JOIN (166). Вход в звонок по ссылке."""
        return await self.invoke(
            Opcode.VIDEO_CHAT_JOIN,
            clean(
                {
                    "joinLink": join_link,
                    "isVideo": video,
                    "internalParams": internal_params,
                }
            ),
        )

    async def hangup_video_chat(
        self,
        conversation_id: str,
        *,
        reason: str | None = None,
        peer_id: int | None = None,
        internal_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """VIDEO_CHAT_HANGUP (167). Завершение звонка."""
        return await self.invoke(
            Opcode.VIDEO_CHAT_HANGUP,
            clean(
                {
                    "conversationId": conversation_id,
                    "reason": reason,
                    "peerId": peer_id,
                    "internalParams": internal_params,
                }
            ),
        )

    async def get_video_chat_members(self, chat_id: int, **extra: Any) -> dict[str, Any]:
        """VIDEO_CHAT_MEMBERS (195)."""
        return await self.invoke(
            Opcode.VIDEO_CHAT_MEMBERS, clean({"chatId": chat_id, **extra})
        )

    async def get_video_chat_history(self, chat_id: int, **extra: Any) -> dict[str, Any]:
        """VIDEO_CHAT_HISTORY (79)."""
        return await self.invoke(
            Opcode.VIDEO_CHAT_HISTORY, clean({"chatId": chat_id, **extra})
        )

    async def create_video_chat_link(self, chat_id: int, **extra: Any) -> dict[str, Any]:
        """VIDEO_CHAT_CREATE_JOIN_LINK (84)."""
        return await self.invoke(
            Opcode.VIDEO_CHAT_CREATE_JOIN_LINK, clean({"chatId": chat_id, **extra})
        )

    async def get_inbound_calls(self, **payload: Any) -> dict[str, Any]:
        """GET_INBOUND_CALLS (103). Входящие звонки.

        Схема запроса неизвестна: поля передавайте как есть. Точные имена
        видны в дампе трафика собственного клиента.
        """
        return await self.invoke(Opcode.GET_INBOUND_CALLS, clean(payload))

    async def get_call_history(self, *, sync: int = 0, **extra: Any) -> list[Call]:
        """CALL_HISTORY (163). Синхронизация журнала звонков.

        ``sync`` — маркер с прошлого раза; 0 запрашивает всё.
        """
        payload = await self.invoke(
            Opcode.CALL_HISTORY, clean({"callHistorySync": sync, **extra})
        )
        return Call.parse_list(payload.get("calls"), self)  # type: ignore[arg-type]

    async def clear_call_history(
        self, history_ids: list[str] | str | None = None, **extra: Any
    ) -> dict[str, Any]:
        """CALL_HISTORY_CLEAR (164). Без аргументов чистит журнал целиком."""
        if isinstance(history_ids, str):
            history_ids = [history_ids]
        return await self.invoke(
            Opcode.CALL_HISTORY_CLEAR, clean({"historyIds": history_ids, **extra})
        )


class PollMethods(MethodsBase):
    """Опросы: опкоды 304-306."""

    async def vote(
        self,
        chat_id: int,
        message_id: str,
        answer_ids: list[int] | int,
        *,
        poll_id: int | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """SEND_VOTE (304).

        Поле ответов на проводе называется ``answersIds`` — именно так,
        с ``s`` в середине; проверено по APK.
        """
        if isinstance(answer_ids, int):
            answer_ids = [answer_ids]
        return await self.invoke(
            Opcode.SEND_VOTE,
            clean(
                {
                    "chatId": chat_id,
                    "messageId": str(message_id),
                    "pollId": poll_id,
                    "answersIds": list(answer_ids),
                    **extra,
                }
            ),
        )

    async def get_voters(
        self,
        chat_id: int,
        message_id: str,
        answer_id: int,
        *,
        poll_id: int | None = None,
        marker: int | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """VOTERS_LIST_BY_ANSWER (305). Кто как проголосовал."""
        return await self.invoke(
            Opcode.VOTERS_LIST_BY_ANSWER,
            clean(
                {
                    "chatId": chat_id,
                    "messageId": str(message_id),
                    "answerId": answer_id,
                    "pollId": poll_id,
                    "marker": marker,
                    **extra,
                }
            ),
        )

    async def get_poll_updates(
        self,
        chat_id: int,
        message_id: str,
        *,
        poll_id: int | None = None,
        polls: list[dict[str, Any]] | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """GET_POLL_UPDATES (306). Свежие результаты опроса."""
        return await self.invoke(
            Opcode.GET_POLL_UPDATES,
            clean(
                {
                    "chatId": chat_id,
                    "messageId": str(message_id),
                    "pollId": poll_id,
                    "polls": polls,
                    **extra,
                }
            ),
        )
