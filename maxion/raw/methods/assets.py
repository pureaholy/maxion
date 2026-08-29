"""Стикеры, анимоджи, фоны — «ассеты»."""

from __future__ import annotations

from typing import Any

from ..enums import AssetType
from ..opcodes import Opcode
from ..types import Sticker, StickerSet
from ..utils import clean
from .base import MethodsBase


class AssetMethods(MethodsBase):
    """Опкоды 26-29, 193-194, 259-261."""

    async def get_assets(
        self,
        asset_type: AssetType | str = AssetType.STICKER,
        *,
        section_id: str | None = None,
        offset: int = 0,
        count: int = 50,
        query: str | None = None,
    ) -> dict[str, Any]:
        """ASSETS_GET (26). Каталог стикеров, фонов, анимоджи."""
        return await self.invoke(
            Opcode.ASSETS_GET,
            clean(
                {
                    "type": str(asset_type),
                    "sectionId": section_id,
                    "from": offset,
                    "count": count,
                    "query": query,
                }
            ),
        )

    async def search_stickers(self, query: str, *, count: int = 50) -> dict[str, Any]:
        """Поиск стикеров через ASSETS_GET."""
        return await self.get_assets(AssetType.STICKER, query=query, count=count)

    async def sync_assets(
        self,
        asset_type: AssetType | str = AssetType.STICKER,
        *,
        sync: int = 0,
        chat_id: int | None = None,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        """ASSETS_UPDATE (27). Инкрементальная синхронизация коллекции."""
        return await self.invoke(
            Opcode.ASSETS_UPDATE,
            clean(
                {
                    "type": str(asset_type),
                    "sync": sync,
                    "chatId": chat_id,
                    "userId": user_id,
                }
            ),
        )

    async def get_assets_by_ids(
        self, ids: list[int] | int, asset_type: AssetType | str = AssetType.STICKER
    ) -> dict[str, Any]:
        """ASSETS_GET_BY_IDS (28)."""
        if isinstance(ids, int):
            ids = [ids]
        return await self.invoke(
            Opcode.ASSETS_GET_BY_IDS, {"type": str(asset_type), "ids": list(ids)}
        )

    async def get_stickers(self, sticker_ids: list[int] | int) -> list[Sticker]:
        """Стикеры по id."""
        payload = await self.get_assets_by_ids(sticker_ids, AssetType.STICKER)
        return Sticker.parse_list(payload.get("stickers"), self)  # type: ignore[arg-type]

    async def get_sticker_sets(self, set_ids: list[int] | int) -> list[StickerSet]:
        """Наборы стикеров по id."""
        payload = await self.get_assets_by_ids(set_ids, AssetType.STICKER_SET)
        return StickerSet.parse_list(payload.get("stickerSets"), self)  # type: ignore[arg-type]

    async def add_asset(
        self, asset_id: int, asset_type: AssetType | str = AssetType.STICKER_SET
    ) -> dict[str, Any]:
        """ASSETS_ADD (29). Добавляет набор себе."""
        return await self.invoke(
            Opcode.ASSETS_ADD, {"type": str(asset_type), "id": asset_id}
        )

    async def remove_asset(
        self, asset_id: int, asset_type: AssetType | str = AssetType.STICKER_SET
    ) -> dict[str, Any]:
        """ASSETS_REMOVE (259)."""
        return await self.invoke(
            Opcode.ASSETS_REMOVE, {"type": str(asset_type), "id": asset_id}
        )

    async def move_asset(
        self,
        asset_id: int,
        position: int,
        asset_type: AssetType | str = AssetType.STICKER_SET,
    ) -> dict[str, Any]:
        """ASSETS_MOVE (260). Меняет порядок наборов."""
        return await self.invoke(
            Opcode.ASSETS_MOVE,
            {"type": str(asset_type), "id": asset_id, "position": position},
        )

    async def modify_assets_list(self, **payload: Any) -> dict[str, Any]:
        """ASSETS_LIST_MODIFY (261). Массовое изменение коллекции.

        Схема запроса неизвестна: поля передавайте как есть. Точные имена
        видны в дампе трафика собственного клиента.
        """
        return await self.invoke(Opcode.ASSETS_LIST_MODIFY, clean(payload))

    async def create_sticker(self, **payload: Any) -> dict[str, Any]:
        """STICKER_CREATE (193). Кастомный стикер из загруженного файла.

        Схема запроса неизвестна: поля передавайте как есть. Точные имена
        видны в дампе трафика собственного клиента.
        """
        return await self.invoke(Opcode.STICKER_CREATE, clean(payload))

    async def suggest_stickers(self, query: str, **extra: Any) -> dict[str, Any]:
        """STICKER_SUGGEST (194). Подсказки стикеров по слову."""
        return await self.invoke(
            Opcode.STICKER_SUGGEST, clean({"query": query, **extra})
        )

    async def get_banners(self, *, sync: int = 0, **extra: Any) -> dict[str, Any]:
        """BANNERS_GET (302). ``sync`` — маркер с прошлого раза."""
        return await self.invoke(
            Opcode.BANNERS_GET, clean({"bannersSync": sync, **extra})
        )
