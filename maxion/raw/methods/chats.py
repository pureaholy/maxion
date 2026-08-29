"""Чаты, каналы, участники, папки."""

from __future__ import annotations

from typing import Any, AsyncIterator

from ..enums import AccessType, ChatType, ItemType, MarkType, MemberType, TypingType
from ..opcodes import Opcode
from ..types import Chat, Folder, LinkInfo, Member, Message
from ..utils import clean
from .base import MethodsBase


class ChatMethods(MethodsBase):
    """Опкоды 48-63, 68, 75, 77, 86, 117, 144-145, 196, 198, 257-258, 272-277, 300, 307."""

    # --- получение чатов ---------------------------------------------------

    async def get_chats(
        self, *, count: int = 40, marker: int = 0
    ) -> tuple[list[Chat], int | None]:
        """CHATS_LIST (53). Возвращает страницу чатов и маркер следующей."""
        payload = await self.invoke(
            Opcode.CHATS_LIST, {"marker": marker, "count": count}
        )
        chats = Chat.parse_list(payload.get("chats"), self)  # type: ignore[arg-type]
        self._cache_chats(chats)
        next_marker = payload.get("marker")
        return chats, int(next_marker) if next_marker else None

    async def iter_chats(self, *, chunk: int = 40, limit: int | None = None) -> AsyncIterator[Chat]:
        """Обходит все чаты постранично."""
        marker, seen = 0, 0
        while True:
            chats, marker = await self.get_chats(count=chunk, marker=marker)
            if not chats:
                return
            for chat in chats:
                yield chat
                seen += 1
                if limit is not None and seen >= limit:
                    return
            if not marker:
                return

    async def get_all_chats(self, *, limit: int | None = None) -> list[Chat]:
        """Собирает все чаты в список."""
        return [chat async for chat in self.iter_chats(limit=limit)]

    async def get_chats_info(self, chat_ids: list[int] | int) -> list[Chat]:
        """CHAT_INFO (48)."""
        if isinstance(chat_ids, int):
            chat_ids = [chat_ids]
        payload = await self.invoke(Opcode.CHAT_INFO, {"chatIds": list(chat_ids)})
        raw = payload.get("chats")
        if not raw and payload.get("chat"):
            raw = [payload["chat"]]
        chats = Chat.parse_list(raw, self)  # type: ignore[arg-type]
        self._cache_chats(chats)
        return chats

    async def get_chat(self, chat_id: int) -> Chat | None:
        """Одиночная обёртка над CHAT_INFO."""
        chats = await self.get_chats_info([chat_id])
        return chats[0] if chats else None

    # --- история -----------------------------------------------------------

    async def get_history(
        self,
        chat_id: int,
        *,
        limit: int = 50,
        from_time: int | None = None,
        forward: int = 0,
        backward: int | None = None,
        forward_time: int | None = None,
        backward_time: int | None = None,
        post_id: int | None = None,
        item_type: ItemType | str | None = None,
        get_chat: bool = False,
        interactive: bool | None = None,
        access_token: str | None = None,
    ) -> list[Message]:
        """CHAT_HISTORY (49). По умолчанию тянет ``limit`` сообщений назад."""
        payload = await self.invoke(
            Opcode.CHAT_HISTORY,
            clean(
                {
                    "chatId": chat_id,
                    "from": from_time if from_time is not None else _now_ms(),
                    "forward": forward,
                    "backward": limit if backward is None else backward,
                    "forwardTime": forward_time,
                    "backwardTime": backward_time,
                    "getMessages": True,
                    "getChat": get_chat or None,
                    "interactive": interactive,
                    "postId": post_id,
                    "itemType": str(item_type) if item_type else None,
                    "chatAccessToken": access_token,
                }
            ),
        )
        return Message.parse_list(payload.get("messages"), self)  # type: ignore[arg-type]

    async def iter_history(
        self, chat_id: int, *, chunk: int = 100, limit: int | None = None
    ) -> AsyncIterator[Message]:
        """Обходит историю чата от новых к старым."""
        cursor = _now_ms()
        produced = 0
        while True:
            batch = await self.get_history(chat_id, limit=chunk, from_time=cursor)
            if not batch:
                return
            for message in batch:
                yield message
                produced += 1
                if limit is not None and produced >= limit:
                    return
            oldest = min((m.get("time") or 0) for m in batch)
            if not oldest or oldest >= cursor:
                return
            cursor = oldest

    async def get_chat_media(
        self,
        chat_id: int,
        *,
        attach_types: list[str] | None = None,
        message_id: str | None = None,
        forward: int = 0,
        backward: int = 50,
    ) -> list[Message]:
        """CHAT_MEDIA (51). Медиа-галерея чата."""
        payload = await self.invoke(
            Opcode.CHAT_MEDIA,
            clean(
                {
                    "chatId": chat_id,
                    "messageId": message_id,
                    "attachTypes": attach_types or ["PHOTO", "VIDEO"],
                    "forward": forward,
                    "backward": backward,
                }
            ),
        )
        return Message.parse_list(payload.get("messages"), self)  # type: ignore[arg-type]

    # --- отметки прочтения -------------------------------------------------

    async def mark_chat(
        self,
        chat_id: int,
        *,
        mark_type: MarkType | str = MarkType.READ_MESSAGE,
        message_id: str | None = None,
        mark: int | None = None,
    ) -> dict[str, Any]:
        """CHAT_MARK (50)."""
        return await self.invoke(
            Opcode.CHAT_MARK,
            clean(
                {
                    "chatId": chat_id,
                    "type": str(mark_type),
                    "messageId": message_id,
                    "mark": mark if mark is not None else _now_ms(),
                }
            ),
        )

    async def read_message(self, chat_id: int, message_id: str) -> dict[str, Any]:
        """Отмечает сообщение прочитанным."""
        return await self.mark_chat(
            chat_id, mark_type=MarkType.READ_MESSAGE, message_id=str(message_id)
        )

    async def mark_unread(self, chat_id: int) -> dict[str, Any]:
        """Возвращает чату статус непрочитанного."""
        return await self.mark_chat(chat_id, mark_type=MarkType.SET_AS_UNREAD)

    # --- изменение чата ----------------------------------------------------

    async def update_chat(
        self,
        chat_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
        access: AccessType | str | None = None,
        link: str | None = None,
        remove_link: bool | None = None,
        revoke_private_link: bool | None = None,
        theme: str | None = None,
        photo_token: str | None = None,
        crop: dict[str, Any] | None = None,
        pin_message_id: str | None = None,
        notify_pin: bool | None = None,
        change_owner_id: int | None = None,
        options: dict[str, bool] | None = None,
    ) -> Chat | None:
        """CHAT_UPDATE (55). Универсальное изменение чата или канала."""
        payload = await self.invoke(
            Opcode.CHAT_UPDATE,
            clean(
                {
                    "chatId": chat_id,
                    "theme": theme if theme is not None else title,
                    "description": description,
                    "access": str(access) if access else None,
                    "link": link,
                    "removeLink": remove_link,
                    "revokePrivateLink": revoke_private_link,
                    "photoToken": photo_token,
                    "crop": crop,
                    "pinMessageId": pin_message_id,
                    "notifyPin": notify_pin,
                    "changeOwnerId": change_owner_id,
                    "options": options,
                }
            ),
        )
        return Chat.parse(payload.get("chat"), self)  # type: ignore[arg-type]

    async def set_chat_title(self, chat_id: int, title: str) -> Chat | None:
        """Меняет название чата (поле ``theme``)."""
        return await self.update_chat(chat_id, theme=title)

    async def set_chat_description(self, chat_id: int, description: str) -> Chat | None:
        return await self.update_chat(chat_id, description=description)

    async def set_chat_photo(self, chat_id: int, photo_token: str, crop: dict | None = None) -> Chat | None:
        return await self.update_chat(chat_id, photo_token=photo_token, crop=crop)

    async def pin_message(self, chat_id: int, message_id: str, *, notify: bool = True) -> Chat | None:
        """Закрепляет сообщение."""
        return await self.update_chat(
            chat_id, pin_message_id=str(message_id), notify_pin=notify
        )

    async def unpin_message(self, chat_id: int) -> Chat | None:
        """Снимает закреп."""
        return await self.update_chat(chat_id, pin_message_id="0")

    async def set_pin_visibility(self, chat_id: int, visible: bool) -> dict[str, Any]:
        """CHAT_PIN_SET_VISIBILITY (86). Прячет закреп лично у себя."""
        return await self.invoke(
            Opcode.CHAT_PIN_SET_VISIBILITY, {"chatId": chat_id, "visible": visible}
        )

    async def transfer_ownership(self, chat_id: int, user_id: int) -> Chat | None:
        return await self.update_chat(chat_id, change_owner_id=user_id)

    async def set_chat_options(self, chat_id: int, options: dict[str, bool]) -> Chat | None:
        """Переключатели чата: ``ONLY_OWNER_CAN_CHANGE_ICON_TITLE``, ``SIGN_ADMIN`` и т.п."""
        return await self.update_chat(chat_id, options=options)

    async def set_personal_config(
        self, chat_id: int, *, hide_non_contact_bar: bool | None = None
    ) -> Chat | None:
        """CHAT_PERSONAL_CONFIG (61). Личные настройки чата."""
        payload = await self.invoke(
            Opcode.CHAT_PERSONAL_CONFIG,
            clean({"chatId": chat_id, "hideNonContactBar": hide_non_contact_bar}),
        )
        return Chat.parse(payload.get("chat"), self)  # type: ignore[arg-type]

    # --- создание, вход, выход ---------------------------------------------

    async def create_chat(
        self,
        user_ids: list[int] | None = None,
        *,
        title: str | None = None,
        chat_type: ChatType | str = ChatType.CHAT,
        message: dict[str, Any] | None = None,
        **extra: Any,
    ) -> Chat | None:
        """CHAT_CREATE (63). Создаёт группу или канал."""
        payload = await self.invoke(
            Opcode.CHAT_CREATE,
            clean(
                {
                    "userIds": user_ids,
                    "title": title,
                    "type": str(chat_type),
                    "message": message,
                    **extra,
                }
            ),
        )
        return Chat.parse(payload.get("chat") or payload, self)  # type: ignore[arg-type]

    async def check_link(self, link: str, *, link_type: str | None = None) -> LinkInfo:
        """CHAT_CHECK_LINK (56). Что скрывается за ссылкой-приглашением."""
        payload = await self.invoke(
            Opcode.CHAT_CHECK_LINK, clean({"link": link, "linkType": link_type})
        )
        return LinkInfo(payload, self)  # type: ignore[arg-type]

    async def join_chat(self, link: str) -> Chat | None:
        """CHAT_JOIN (57). Вход по ссылке или @имени."""
        payload = await self.invoke(Opcode.CHAT_JOIN, {"link": link})
        return Chat.parse(payload.get("chat") or payload, self)  # type: ignore[arg-type]

    async def leave_chat(self, chat_id: int) -> dict[str, Any]:
        """CHAT_LEAVE (58)."""
        return await self.invoke(Opcode.CHAT_LEAVE, {"chatId": chat_id})

    async def subscribe_chat(self, chat_id: int, subscribe: bool = True) -> dict[str, Any]:
        """CHAT_SUBSCRIBE (75). Подписка/отписка от канала."""
        return await self.invoke(
            Opcode.CHAT_SUBSCRIBE, {"chatId": chat_id, "subscribe": subscribe}
        )

    async def unsubscribe_chat(self, chat_id: int) -> dict[str, Any]:
        return await self.subscribe_chat(chat_id, False)

    async def delete_chat(self, chat_id: int, **extra: Any) -> dict[str, Any]:
        """CHAT_DELETE (52)."""
        return await self.invoke(Opcode.CHAT_DELETE, clean({"chatId": chat_id, **extra}))

    async def clear_chat(self, chat_id: int, **extra: Any) -> dict[str, Any]:
        """CHAT_CLEAR (54). Очищает историю."""
        return await self.invoke(Opcode.CHAT_CLEAR, clean({"chatId": chat_id, **extra}))

    async def hide_chat(self, chat_id: int, hide: bool = True) -> dict[str, Any]:
        """CHAT_HIDE (196). Убирает чат из списка, не удаляя."""
        return await self.invoke(Opcode.CHAT_HIDE, {"chatId": chat_id, "hide": hide})

    # --- участники ---------------------------------------------------------

    async def get_members(
        self,
        chat_id: int,
        *,
        member_type: MemberType | str | None = None,
        marker: int = 0,
        count: int = 100,
        query: str | None = None,
    ) -> list[Member]:
        """CHAT_MEMBERS (59)."""
        payload = await self.invoke(
            Opcode.CHAT_MEMBERS,
            clean(
                {
                    "chatId": chat_id,
                    "type": str(member_type) if member_type else None,
                    "marker": marker,
                    "count": count,
                    "query": query,
                }
            ),
        )
        return Member.parse_list(payload.get("members"), self)  # type: ignore[arg-type]

    async def iter_members(
        self, chat_id: int, *, chunk: int = 100, member_type: MemberType | str | None = None
    ) -> AsyncIterator[Member]:
        """Обходит всех участников чата."""
        marker = 0
        while True:
            payload = await self.invoke(
                Opcode.CHAT_MEMBERS,
                clean(
                    {
                        "chatId": chat_id,
                        "type": str(member_type) if member_type else None,
                        "marker": marker,
                        "count": chunk,
                    }
                ),
            )
            members = Member.parse_list(payload.get("members"), self)  # type: ignore[arg-type]
            if not members:
                return
            for member in members:
                yield member
            marker = payload.get("marker") or 0
            if not marker:
                return

    async def update_members(
        self,
        chat_id: int,
        user_ids: list[int] | int,
        operation: str,
        *,
        show_history: bool = True,
        **extra: Any,
    ) -> dict[str, Any]:
        """CHAT_MEMBERS_UPDATE (77). ``operation``: add/remove/block/admin."""
        if isinstance(user_ids, int):
            user_ids = [user_ids]
        return await self.invoke(
            Opcode.CHAT_MEMBERS_UPDATE,
            clean(
                {
                    "chatId": chat_id,
                    "userIds": list(user_ids),
                    "operation": operation,
                    "showHistory": show_history,
                    **extra,
                }
            ),
        )

    async def add_members(
        self, chat_id: int, user_ids: list[int] | int, *, show_history: bool = True
    ) -> dict[str, Any]:
        return await self.update_members(chat_id, user_ids, "add", show_history=show_history)

    async def remove_members(self, chat_id: int, user_ids: list[int] | int) -> dict[str, Any]:
        return await self.update_members(chat_id, user_ids, "remove")

    async def block_members(self, chat_id: int, user_ids: list[int] | int) -> dict[str, Any]:
        return await self.update_members(chat_id, user_ids, "block")

    async def promote_members(
        self, chat_id: int, user_ids: list[int] | int, permissions: list[str] | None = None
    ) -> dict[str, Any]:
        """Выдаёт админку."""
        return await self.update_members(
            chat_id, user_ids, "admin", permissions=permissions
        )

    async def demote_members(self, chat_id: int, user_ids: list[int] | int) -> dict[str, Any]:
        """Снимает админку."""
        return await self.update_members(chat_id, user_ids, "revokeAdmin")

    async def get_common_participants(self, chat_id: int, query: str | None = None) -> list[Member]:
        """CHAT_SEARCH_COMMON_PARTICIPANTS (198)."""
        payload = await self.invoke(
            Opcode.CHAT_SEARCH_COMMON_PARTICIPANTS,
            clean({"chatId": chat_id, "query": query}),
        )
        return Member.parse_list(payload.get("members") or payload.get("contacts"), self)  # type: ignore[arg-type]

    # --- поиск -------------------------------------------------------------

    async def search_chats(self, query: str, *, count: int = 30, **extra: Any) -> list[Chat]:
        """CHAT_SEARCH (68). Поиск по своим чатам."""
        payload = await self.invoke(
            Opcode.CHAT_SEARCH, clean({"query": query, "count": count, **extra})
        )
        return Chat.parse_list(payload.get("chats"), self)  # type: ignore[arg-type]

    async def search_public(self, query: str, *, count: int = 30, **extra: Any) -> dict[str, Any]:
        """PUBLIC_SEARCH (60). Глобальный поиск каналов, чатов и людей."""
        return await self.invoke(
            Opcode.PUBLIC_SEARCH, clean({"query": query, "count": count, **extra})
        )

    async def get_chat_suggestions(
        self,
        *,
        chat_ids: list[int] | None = None,
        folder_id: int | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """CHAT_SUGGEST (300). Рекомендованные чаты."""
        return await self.invoke(
            Opcode.CHAT_SUGGEST,
            clean({"userChatIds": chat_ids, "folderId": folder_id, **extra}),
        )

    # --- уведомления и режим «не беспокоить» -------------------------------

    async def mute_chat(self, chat_id: int, until: int = -1) -> dict[str, Any]:
        """Заглушает чат: ``-1`` — навсегда, иначе timestamp в мс."""
        return await self.invoke(
            Opcode.CONFIG,
            {"settings": {"chats": {str(chat_id): {"dontDisturbUntil": until}}}},
        )

    async def unmute_chat(self, chat_id: int) -> dict[str, Any]:
        return await self.mute_chat(chat_id, 0)

    async def send_typing(
        self, chat_id: int, kind: TypingType | str = TypingType.TEXT
    ) -> None:
        """MSG_TYPING (65). Индикатор набора текста."""
        await self.notify(Opcode.MSG_TYPING, {"chatId": chat_id, "type": str(kind)})

    # --- жалобы ------------------------------------------------------------

    async def complain_chat(self, chat_id: int, reason: str, **extra: Any) -> dict[str, Any]:
        """CHAT_COMPLAIN (117)."""
        return await self.invoke(
            Opcode.CHAT_COMPLAIN, clean({"chatId": chat_id, "reason": reason, **extra})
        )

    async def complain(
        self,
        *,
        type_id: int | str | None = None,
        parent_id: int | None = None,
        ids: list[int] | list[str] | None = None,
        reason_id: int | str | None = None,
        post_id: int | None = None,
        details: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """COMPLAIN (161). Универсальная жалоба.

        ``type_id`` — на что жалуемся, ``parent_id`` — чат или канал,
        ``ids`` — конкретные объекты, ``reason_id`` — причина из
        :meth:`get_complain_reasons`.
        """
        return await self.invoke(
            Opcode.COMPLAIN,
            clean(
                {
                    "typeId": type_id,
                    "parentId": parent_id,
                    "ids": ids,
                    "reasonId": reason_id,
                    "postId": post_id,
                    "details": details,
                    **extra,
                }
            ),
        )

    async def get_complain_reasons(self, *, sync: int = 0, **extra: Any) -> dict[str, Any]:
        """COMPLAIN_REASONS_GET (162). Справочник причин жалоб.

        ``sync`` — маркер с прошлого раза, 0 запрашивает всё.
        """
        return await self.invoke(
            Opcode.COMPLAIN_REASONS_GET, clean({"complainSync": sync, **extra})
        )

    # --- боты в чате -------------------------------------------------------

    async def get_bot_commands(self, chat_id: int) -> dict[str, Any]:
        """CHAT_BOT_COMMANDS (144)."""
        return await self.invoke(Opcode.CHAT_BOT_COMMANDS, {"chatId": chat_id})

    async def get_bot_info(
        self, bot_id: int, *, chat_id: int | None = None, type_: str | None = None
    ) -> dict[str, Any]:
        """BOT_INFO (145)."""
        return await self.invoke(
            Opcode.BOT_INFO,
            clean({"botId": bot_id, "chatId": chat_id, "type": type_}),
        )

    async def suspend_bot(self, bot_id: int, chat_id: int | None = None, suspend: bool = True) -> dict[str, Any]:
        """SUSPEND_BOT (119)."""
        return await self.invoke(
            Opcode.SUSPEND_BOT,
            clean({"botId": bot_id, "chatId": chat_id, "suspend": suspend}),
        )

    # --- настройки реакций -------------------------------------------------

    async def get_reactions_settings(self, chat_ids: list[int] | int) -> dict[str, Any]:
        """REACTIONS_SETTINGS_GET_BY_CHAT_ID (258). Поле множественное: ``chatIds``."""
        if isinstance(chat_ids, int):
            chat_ids = [chat_ids]
        return await self.invoke(
            Opcode.REACTIONS_SETTINGS_GET_BY_CHAT_ID, {"chatIds": list(chat_ids)}
        )

    async def set_reactions_settings(
        self,
        chat_id: int,
        *,
        reaction_ids: list[str] | None = None,
        included: bool | None = None,
        value: Any = None,
        count: int | None = None,
        reset: bool | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """CHAT_REACTIONS_SETTINGS_SET (257). Какие реакции разрешены в чате."""
        return await self.invoke(
            Opcode.CHAT_REACTIONS_SETTINGS_SET,
            clean(
                {
                    "chatId": chat_id,
                    "reactionIds": reaction_ids,
                    "included": included,
                    "value": value,
                    "count": count,
                    "reset": reset,
                    **extra,
                }
            ),
        )

    # --- прочее ------------------------------------------------------------

    async def get_livestream_info(self, chat_ids: list[int] | int) -> dict[str, Any]:
        """CHAT_LIVESTREAM_INFO (62)."""
        if isinstance(chat_ids, int):
            chat_ids = [chat_ids]
        return await self.invoke(Opcode.CHAT_LIVESTREAM_INFO, {"chatIds": list(chat_ids)})

    async def check_esia(self, chat_id: int, **extra: Any) -> dict[str, Any]:
        """CHAT_CHECK_ESIA (307). Проверка подтверждения через Госуслуги."""
        return await self.invoke(
            Opcode.CHAT_CHECK_ESIA, clean({"chatId": chat_id, **extra})
        )

    async def get_organizations(self, organization_ids: list[int] | int) -> dict[str, Any]:
        """ORG_INFO (256)."""
        if isinstance(organization_ids, int):
            organization_ids = [organization_ids]
        return await self.invoke(
            Opcode.ORG_INFO, {"organizationIds": list(organization_ids)}
        )

    # --- папки -------------------------------------------------------------

    async def get_folders(self, *, sync: int = 0) -> list[Folder]:
        """FOLDERS_GET (272). ``sync`` — маркер с прошлого раза."""
        payload = await self.invoke(
            Opcode.FOLDERS_GET, clean({"folderSync": sync})
        )
        return Folder.parse_list(payload.get("folders"), self)  # type: ignore[arg-type]

    async def get_folder(self, folder_id: int) -> Folder | None:
        """FOLDERS_GET_BY_ID (273)."""
        payload = await self.invoke(Opcode.FOLDERS_GET_BY_ID, {"folderIds": [folder_id]})
        folders = Folder.parse_list(payload.get("folders"), self)  # type: ignore[arg-type]
        return folders[0] if folders else None

    async def update_folder(
        self,
        *,
        folder_id: int | None = None,
        title: str | None = None,
        include: list[int] | None = None,
        filters: dict[str, Any] | list[Any] | None = None,
        options: dict[str, Any] | list[Any] | None = None,
        favorites: list[int] | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """FOLDERS_UPDATE (274). Создаёт или изменяет папку.

        Поля плоские, без обёртки ``folder`` — проверено по APK 26.29.1.
        ``folder_id=None`` создаёт новую папку.
        """
        return await self.invoke(
            Opcode.FOLDERS_UPDATE,
            clean(
                {
                    "id": folder_id,
                    "title": title,
                    "include": include,
                    "filters": filters,
                    "options": options,
                    "favorites": favorites,
                    **extra,
                }
            ),
        )

    async def reorder_folders(self, folder_ids: list[int]) -> dict[str, Any]:
        """FOLDERS_REORDER (275). Поле называется ``foldersOrder``."""
        return await self.invoke(
            Opcode.FOLDERS_REORDER, {"foldersOrder": list(folder_ids)}
        )

    async def delete_folders(self, folder_ids: list[int] | int) -> dict[str, Any]:
        """FOLDERS_DELETE (276)."""
        if isinstance(folder_ids, int):
            folder_ids = [folder_ids]
        return await self.invoke(Opcode.FOLDERS_DELETE, {"folderIds": list(folder_ids)})

    # --- служебное ---------------------------------------------------------

    def _cache_chats(self, chats: list[Chat]) -> None:
        cache = getattr(self, "chats_cache", None)
        if cache is None:
            return
        for chat in chats:
            if chat.id is not None:
                cache[chat.id] = chat


def _now_ms() -> int:
    from ..utils import now_ms

    return now_ms()
