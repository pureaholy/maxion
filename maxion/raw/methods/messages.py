"""Отправка, редактирование, удаление и поиск сообщений."""

from __future__ import annotations

from typing import Any, AsyncIterator, Sequence

from ..enums import ItemType
from ..errors import RpcError
from ..opcodes import Opcode
from ..types import Message
from ..utils import Text, clean, next_cid, now_ms, parse_markdown
from .base import MethodsBase


class MessageMethods(MethodsBase):
    """Опкоды 64, 66, 67, 70-74, 92, 94, 118, 127, 176-177, 303."""

    # --- отправка ----------------------------------------------------------

    async def send_message(
        self,
        chat_id: int,
        text: str | Text = "",
        *,
        attaches: Sequence[dict[str, Any]] | None = None,
        elements: Sequence[dict[str, Any]] | None = None,
        reply_to: str | int | None = None,
        forward_from: tuple[int, str] | None = None,
        notify: bool = True,
        markdown: bool = False,
        user_id: int | None = None,
        post_id: int | None = None,
        cid: int | None = None,
        **extra: Any,
    ) -> Message:
        """MSG_SEND (64). Отправляет сообщение в чат.

        :param text: строка либо :class:`~maxion.raw.utils.Text` с разметкой.
        :param markdown: разобрать markdown в ``elements``.
        :param reply_to: id сообщения, на которое отвечаем.
        :param forward_from: ``(chat_id, message_id)`` для пересылки.
        """
        if isinstance(text, Text):
            body, auto_elements = text.value, text.elements
        elif markdown:
            body, auto_elements = parse_markdown(str(text))
        else:
            body, auto_elements = str(text), []

        message: dict[str, Any] = {
            "text": body,
            "cid": cid if cid is not None else next_cid(),
            "elements": list(elements) if elements is not None else auto_elements,
            "attaches": list(attaches or []),
        }
        if reply_to is not None:
            message["link"] = {"type": "REPLY", "messageId": str(reply_to)}
        elif forward_from is not None:
            src_chat, src_message = forward_from
            message["link"] = {
                "type": "FORWARD",
                "chatId": int(src_chat),
                "messageId": str(src_message),
            }
        message.update(extra)

        payload = await self.invoke(
            Opcode.MSG_SEND,
            clean(
                {
                    "chatId": chat_id,
                    "userId": user_id,
                    "postId": post_id,
                    "message": message,
                    "notify": notify,
                }
            ),
        )
        return Message(payload.get("message") or {}, self)  # type: ignore[arg-type]

    async def reply_message(
        self, chat_id: int, message_id: str, text: str | Text = "", **kwargs
    ) -> Message:
        """Ответ на сообщение."""
        return await self.send_message(chat_id, text, reply_to=message_id, **kwargs)

    async def forward_message(
        self,
        chat_id: int,
        from_chat_id: int,
        message_id: str,
        *,
        text: str | Text = "",
        **kwargs,
    ) -> Message:
        """Пересылка одного сообщения."""
        return await self.send_message(
            chat_id, text, forward_from=(from_chat_id, str(message_id)), **kwargs
        )

    async def forward_messages(
        self, chat_id: int, from_chat_id: int, message_ids: Sequence[str]
    ) -> list[Message]:
        """Пересылает несколько сообщений по очереди."""
        result = []
        for message_id in message_ids:
            result.append(await self.forward_message(chat_id, from_chat_id, message_id))
        return result

    async def send_sticker(self, chat_id: int, sticker_id: int, **kwargs) -> Message:
        """Отправляет стикер."""
        return await self.send_message(
            chat_id, "", attaches=[{"_type": "STICKER", "stickerId": sticker_id}], **kwargs
        )

    async def send_location(
        self, chat_id: int, latitude: float, longitude: float, *, live: bool = False, **kwargs
    ) -> Message:
        """Отправляет геопозицию (обычную или live)."""
        if live:
            return await self.share_live_location(chat_id, latitude, longitude, **kwargs)
        return await self.send_message(
            chat_id,
            "",
            attaches=[
                {"_type": "LOCATION", "latitude": latitude, "longitude": longitude}
            ],
            **kwargs,
        )

    async def send_contact(self, chat_id: int, user_id: int, **kwargs) -> Message:
        """Делится контактом."""
        return await self.send_message(
            chat_id, "", attaches=[{"_type": "CONTACT", "contactId": user_id}], **kwargs
        )

    # --- редактирование и удаление ----------------------------------------

    async def edit_message(
        self,
        chat_id: int,
        message_id: str,
        text: str | Text = "",
        *,
        elements: Sequence[dict[str, Any]] | None = None,
        attachments: Sequence[dict[str, Any]] | None = None,
        markdown: bool = False,
        post_id: int | None = None,
        delayed_attributes: dict[str, Any] | None = None,
    ) -> Message:
        """MSG_EDIT (67). ``delayed_attributes`` — параметры отложенного поста."""
        if isinstance(text, Text):
            body, auto_elements = text.value, text.elements
        elif markdown:
            body, auto_elements = parse_markdown(str(text))
        else:
            body, auto_elements = str(text), []
        payload = await self.invoke(
            Opcode.MSG_EDIT,
            clean(
                {
                    "chatId": chat_id,
                    "messageId": str(message_id),
                    "postId": post_id,
                    "text": body,
                    "elements": list(elements) if elements is not None else auto_elements,
                    "attachments": list(attachments or []),
                    "delayedAttributes": delayed_attributes,
                }
            ),
        )
        return Message(payload.get("message") or {}, self)  # type: ignore[arg-type]

    async def delete_messages(
        self,
        chat_id: int,
        message_ids: Sequence[str] | str,
        *,
        for_me: bool = False,
        post_id: int | None = None,
        item_type: ItemType | str | None = None,
        complaint: str | None = None,
    ) -> dict[str, Any]:
        """MSG_DELETE (66). ``complaint`` — удалить с жалобой."""
        if isinstance(message_ids, str):
            message_ids = [message_ids]
        return await self.invoke(
            Opcode.MSG_DELETE,
            clean(
                {
                    "chatId": chat_id,
                    "messageIds": [str(m) for m in message_ids],
                    "forMe": for_me,
                    "postId": post_id,
                    "itemType": str(item_type) if item_type else None,
                    "complaint": complaint,
                }
            ),
        )

    async def delete_message_range(
        self,
        chat_id: int,
        start_time: int,
        end_time: int,
        *,
        item_type: ItemType | str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """MSG_DELETE_RANGE (92). Удаляет сообщения в интервале времени.

        Поля называются ``startTime``/``endTime`` — проверено по APK 26.29.1.
        """
        return await self.invoke(
            Opcode.MSG_DELETE_RANGE,
            clean(
                {
                    "chatId": chat_id,
                    "startTime": start_time,
                    "endTime": end_time,
                    "itemType": str(item_type) if item_type else None,
                    **extra,
                }
            ),
        )

    async def delete_user_messages(
        self,
        chat_id: int,
        user_id: int,
        *,
        message_id: str | None = None,
        post_id: int | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """MSG_DELETE_USER (94). Удаляет сообщения участника."""
        return await self.invoke(
            Opcode.MSG_DELETE_USER,
            clean(
                {
                    "chatId": chat_id,
                    "userId": user_id,
                    "messageId": str(message_id) if message_id else None,
                    "postId": post_id,
                    **extra,
                }
            ),
        )

    # --- чтение ------------------------------------------------------------

    async def get_messages(
        self, chat_id: int, message_ids: Sequence[str] | str
    ) -> list[Message]:
        """MSG_GET (71)."""
        if isinstance(message_ids, str):
            message_ids = [message_ids]
        payload = await self.invoke(
            Opcode.MSG_GET,
            {"chatId": chat_id, "messageIds": [str(m) for m in message_ids]},
        )
        return Message.parse_list(payload.get("messages"), self)  # type: ignore[arg-type]

    async def get_message(self, chat_id: int, message_id: str) -> Message | None:
        messages = await self.get_messages(chat_id, [message_id])
        return messages[0] if messages else None

    async def search_messages(
        self,
        query: str,
        *,
        chat_id: int | None = None,
        count: int = 30,
        marker: int | None = None,
    ) -> dict[str, Any]:
        """MSG_SEARCH (73). Поиск по сообщениям."""
        return await self.invoke(
            Opcode.MSG_SEARCH,
            clean({"chatId": chat_id, "query": query, "count": count, "marker": marker}),
        )

    async def iter_search_messages(
        self, query: str, *, chat_id: int | None = None, chunk: int = 30
    ) -> AsyncIterator[dict[str, Any]]:
        """Постранично обходит результаты поиска."""
        marker: int | None = None
        while True:
            payload = await self.search_messages(
                query, chat_id=chat_id, count=chunk, marker=marker
            )
            results = payload.get("result") or []
            if not results:
                return
            for item in results:
                yield item
            marker = payload.get("marker")
            if not marker:
                return

    async def touch_search(self, **payload: Any) -> dict[str, Any]:
        """MSG_SEARCH_TOUCH (72). Помечает поисковый запрос как использованный.

        Схема запроса неизвестна: поля передавайте как есть. Точные имена
        видны в дампе трафика собственного клиента.
        """
        return await self.invoke(Opcode.MSG_SEARCH_TOUCH, clean(payload))

    async def get_message_stats(
        self, chat_id: int, message_ids: Sequence[str] | str
    ) -> dict[str, Any]:
        """MSG_GET_STAT (74). Просмотры и пересылки постов."""
        if isinstance(message_ids, str):
            message_ids = [message_ids]
        return await self.invoke(
            Opcode.MSG_GET_STAT,
            {"chatId": chat_id, "messageIds": [str(m) for m in message_ids]},
        )

    async def get_link_preview(self, text: str) -> dict[str, Any]:
        """MSG_SHARE_PREVIEW (70). Готовит превью ссылки из текста."""
        return await self.invoke(Opcode.MSG_SHARE_PREVIEW, {"text": text})

    async def get_last_mentions(self, **payload: Any) -> dict[str, Any]:
        """GET_LAST_MENTIONS (127). Последние упоминания.

        Схема запроса неизвестна: поля передавайте как есть. Точные имена
        видны в дампе трафика собственного клиента.
        """
        return await self.invoke(Opcode.GET_LAST_MENTIONS, clean(payload))

    async def confirm_delivery(self, delivery_token: str, **extra: Any) -> None:
        """MSG_DELIVERY (303). Подтверждает доставку пуша.

        Приложение шлёт сюда ``deliveryToken`` из уведомления, а не список
        сообщений — проверено по APK 26.29.1.
        """
        await self.notify(
            Opcode.MSG_DELIVERY, clean({"deliveryToken": delivery_token, **extra})
        )

    # --- кнопки ботов ------------------------------------------------------

    async def press_button(
        self,
        chat_id: int,
        message_id: str,
        payload_value: str,
        **extra: Any,
    ) -> dict[str, Any]:
        """MSG_SEND_CALLBACK (118). Нажимает inline-кнопку бота."""
        return await self.invoke(
            Opcode.MSG_SEND_CALLBACK,
            clean(
                {
                    "chatId": chat_id,
                    "messageId": str(message_id),
                    "payload": payload_value,
                    **extra,
                }
            ),
        )

    async def external_callback(self, **payload: Any) -> dict[str, Any]:
        """EXTERNAL_CALLBACK (105). Внешний колбэк мини-приложения.

        Схема запроса неизвестна: поля передавайте как есть. Точные имена
        видны в дампе трафика собственного клиента.
        """
        return await self.invoke(Opcode.EXTERNAL_CALLBACK, clean(payload))

    async def get_webapp_init_data(
        self,
        bot_id: int,
        *,
        chat_id: int | None = None,
        start_param: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """WEB_APP_INIT_DATA (160). initData для мини-приложения бота."""
        return await self.invoke(
            Opcode.WEB_APP_INIT_DATA,
            clean(
                {
                    "botId": bot_id,
                    "chatId": chat_id,
                    "startParam": start_param,
                    **extra,
                }
            ),
        )

    # --- комментарии -------------------------------------------------------

    async def get_comments_updates(
        self, chat_id: int, post_ids: Sequence[int] | int, **extra: Any
    ) -> dict[str, Any]:
        """GET_COMMENTS_UPDATES (91). Счётчики комментариев к постам."""
        if isinstance(post_ids, int):
            post_ids = [post_ids]
        return await self.invoke(
            Opcode.GET_COMMENTS_UPDATES,
            clean({"chatId": chat_id, "postIds": list(post_ids), **extra}),
        )

    async def send_comment(
        self, chat_id: int, post_id: int, text: str | Text = "", **kwargs
    ) -> Message:
        """Комментарий к посту канала (MSG_SEND с ``postId``)."""
        return await self.send_message(chat_id, text, post_id=post_id, **kwargs)

    # --- черновики ---------------------------------------------------------

    async def save_draft(
        self, chat_id: int, text: str = "", **extra: Any
    ) -> dict[str, Any]:
        """DRAFT_SAVE (176)."""
        return await self.invoke(
            Opcode.DRAFT_SAVE,
            clean({"chatId": chat_id, "text": text, "time": now_ms(), **extra}),
        )

    async def discard_draft(self, chat_id: int) -> dict[str, Any]:
        """DRAFT_DISCARD (177)."""
        return await self.invoke(Opcode.DRAFT_DISCARD, {"chatId": chat_id})

    # --- геолокация --------------------------------------------------------

    async def share_live_location(
        self,
        chat_id: int,
        latitude: float,
        longitude: float,
        *,
        duration: int | None = None,
        **extra: Any,
    ) -> Any:
        """LOCATION_SEND (125). Трансляция геопозиции."""
        return await self.invoke(
            Opcode.LOCATION_SEND,
            clean(
                {
                    "chatId": chat_id,
                    "latitude": latitude,
                    "longitude": longitude,
                    "duration": duration,
                    **extra,
                }
            ),
        )

    async def stop_live_location(self, chat_id: int, **extra: Any) -> dict[str, Any]:
        """LOCATION_STOP (124)."""
        return await self.invoke(
            Opcode.LOCATION_STOP, clean({"chatId": chat_id, **extra})
        )

    async def request_location(self, chat_id: int, **extra: Any) -> dict[str, Any]:
        """LOCATION_REQUEST (126). Просит собеседника прислать геопозицию."""
        return await self.invoke(
            Opcode.LOCATION_REQUEST, clean({"chatId": chat_id, **extra})
        )

    # --- удобные обёртки ---------------------------------------------------

    async def try_delete(self, chat_id: int, message_ids: Sequence[str] | str) -> bool:
        """Удаляет сообщения, проглатывая ошибку прав."""
        try:
            await self.delete_messages(chat_id, message_ids)
            return True
        except RpcError:
            return False
