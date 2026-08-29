"""Профиль и настройки аккаунта."""

from __future__ import annotations

from typing import Any

from ..opcodes import Opcode
from ..types import Profile
from ..utils import clean
from .base import MethodsBase


class ProfileMethods(MethodsBase):
    """Опкоды 16, 21, 22, 25, 39, 43, 203."""

    async def update_profile(
        self,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
        description: str | None = None,
        link: str | None = None,
        photo_token: str | None = None,
        photo_id: int | None = None,
        crop: dict[str, Any] | None = None,
        avatar_type: str | None = None,
    ) -> Profile:
        """PROFILE (16). Меняет имя, описание, @ссылку или аватар."""
        payload = await self.invoke(
            Opcode.PROFILE,
            clean(
                {
                    "firstName": first_name,
                    "lastName": last_name,
                    "description": description,
                    "link": link,
                    "photoToken": photo_token,
                    "photoId": photo_id,
                    "crop": crop,
                    "avatarType": avatar_type,
                }
            ),
        )
        return Profile(payload.get("profile") or payload, self)  # type: ignore[arg-type]

    async def get_config(
        self, *, push_token: str | None = None, config_hash: str | None = None
    ) -> dict[str, Any]:
        """CONFIG (22) без изменений — просто читает настройки."""
        return await self.invoke(
            Opcode.CONFIG, clean({"pushToken": push_token, "hash": config_hash})
        )

    async def update_settings(
        self, settings: dict[str, Any], *, reset: bool = False
    ) -> dict[str, Any]:
        """CONFIG (22). Универсальный апдейт настроек.

        Примеры::

            await client.update_settings({"user": {"HIDDEN": True}})
            await client.update_settings({"chats": {"-680937": {"dontDisturbUntil": -1}}})
        """
        return await self.invoke(
            Opcode.CONFIG, clean({"settings": settings, "reset": reset or None})
        )

    async def set_user_setting(self, key: str, value: Any) -> dict[str, Any]:
        """Меняет одну настройку профиля, например ``HIDDEN``."""
        return await self.update_settings({"user": {key: value}})

    async def set_hidden(self, hidden: bool = True) -> dict[str, Any]:
        """Скрывает время последнего визита."""
        return await self.set_user_setting("HIDDEN", hidden)

    async def register_push_token(
        self, push_token: str, *, options: int | None = None
    ) -> dict[str, Any]:
        """CONFIG (22) с pushToken."""
        return await self.invoke(
            Opcode.CONFIG, clean({"pushToken": push_token, "pushOptions": options})
        )

    async def sync_contacts(self, contact_list: dict[str, Any]) -> dict[str, Any]:
        """SYNC (21). Загружает телефонную книгу и получает совпадения.

        ``contact_list`` — словарь ``{телефон: {"names": [...]}}``.
        """
        return await self.invoke(Opcode.SYNC, {"contactList": contact_list})

    async def get_preset_avatars(self) -> list[dict[str, Any]]:
        """PRESET_AVATARS (25)."""
        payload = await self.invoke(Opcode.PRESET_AVATARS, {})
        return list(payload.get("presetAvatars") or [])

    async def get_profile_photos(
        self, user_id: int | None = None, *, count: int = 50, offset: int = 0
    ) -> dict[str, Any]:
        """CONTACT_PHOTOS (39). История аватаров."""
        return await self.invoke(
            Opcode.CONTACT_PHOTOS,
            {"contactId": user_id or self.user_id, "count": count, "from": offset},
        )

    async def remove_profile_photo(self, photo_id: int) -> Profile:
        """REMOVE_CONTACT_PHOTO (43)."""
        payload = await self.invoke(Opcode.REMOVE_CONTACT_PHOTO, {"photoId": photo_id})
        return Profile(payload.get("profile") or payload, self)  # type: ignore[arg-type]

    async def refresh_photo_url(
        self,
        photo_ids: list[int] | int,
        *,
        chat_id: int | None = None,
        message_id: str | None = None,
        media: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """PHOTO_URL_REFRESH (203). Обновляет протухшие ссылки на фото."""
        if isinstance(photo_ids, int):
            photo_ids = [photo_ids]
        return await self.invoke(
            Opcode.PHOTO_URL_REFRESH,
            clean(
                {
                    "photoIds": list(photo_ids),
                    "chatId": chat_id,
                    "messageId": str(message_id) if message_id else None,
                    "media": media,
                }
            ),
        )
