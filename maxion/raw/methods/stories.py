"""Истории (stories).

Имена полей сверены с приложением ``ru.oneme.app`` 26.29.1.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from ..enums import ReactionType
from ..opcodes import Opcode
from ..types import Story
from ..utils import clean, next_cid
from .base import MethodsBase


class StoryMethods(MethodsBase):
    """Опкоды 208-220."""

    # --- лента -------------------------------------------------------------

    async def get_stories_feed(
        self, *, cursor: str | None = None, count: int = 30
    ) -> dict[str, Any]:
        """STORIES_LIST (208). Лента превью историй."""
        return await self.invoke(
            Opcode.STORIES_LIST, clean({"cursor": cursor, "count": count})
        )

    async def iter_stories_feed(
        self, *, chunk: int = 30, limit: int | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Постранично обходит ленту историй по курсору."""
        cursor: str | None = None
        produced = 0
        while True:
            payload = await self.get_stories_feed(cursor=cursor, count=chunk)
            previews = payload.get("storiesPreviews") or []
            if not previews:
                return
            for preview in previews:
                yield preview
                produced += 1
                if limit is not None and produced >= limit:
                    return
            cursor = payload.get("cursor")
            if not cursor:
                return

    async def get_stories_previews(
        self, owner_ids: list[int] | int, **extra: Any
    ) -> dict[str, Any]:
        """STORIES_LIST_BY_OWNER_ID (209). Превью историй нескольких авторов."""
        if isinstance(owner_ids, int):
            owner_ids = [owner_ids]
        return await self.invoke(
            Opcode.STORIES_LIST_BY_OWNER_ID,
            clean({"owners": list(owner_ids), **extra}),
        )

    # --- чтение ------------------------------------------------------------

    async def get_stories_by_owner(
        self, owner_ids: list[int] | int, **extra: Any
    ) -> list[Story]:
        """STORIES_GET_BY_OWNER_ID (210). Истории автора целиком."""
        if isinstance(owner_ids, int):
            owner_ids = [owner_ids]
        payload = await self.invoke(
            Opcode.STORIES_GET_BY_OWNER_ID,
            clean({"owners": list(owner_ids), **extra}),
        )
        return Story.parse_list(payload.get("stories"), self)  # type: ignore[arg-type]

    async def get_stories(
        self, story_ids: list[int] | int, owner_id: int | None = None, **extra: Any
    ) -> list[Story]:
        """STORIES_GET_BY_STORY_ID (220). Истории по их id."""
        if isinstance(story_ids, int):
            story_ids = [story_ids]
        payload = await self.invoke(
            Opcode.STORIES_GET_BY_STORY_ID,
            clean({"storyIds": list(story_ids), "owner": owner_id, **extra}),
        )
        return Story.parse_list(payload.get("stories"), self)  # type: ignore[arg-type]

    async def get_story(self, story_id: int, owner_id: int | None = None) -> Story | None:
        """Одиночная обёртка над STORIES_GET_BY_STORY_ID."""
        stories = await self.get_stories([story_id], owner_id)
        return stories[0] if stories else None

    # --- публикация --------------------------------------------------------

    async def send_story(
        self,
        media: list[dict[str, Any]] | dict[str, Any] | None = None,
        *,
        stories: list[dict[str, Any]] | None = None,
        layers: list[dict[str, Any]] | None = None,
        settings: dict[str, Any] | None = None,
        expiration: int | None = None,
        clickable_link: dict[str, Any] | None = None,
        url: str | None = None,
        cid: int | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """STORIES_SEND (215). Публикация истории из загруженного медиа.

        ``media`` — вложение из :meth:`upload_photo` или :meth:`upload_video`.
        ``stories`` — если публикуется сразу несколько историй, каждая своим
        объектом. ``layers`` — наклейки и текст поверх медиа; у слоя свои
        ``type``, ``coordinates``, ``rotation``.
        """
        if isinstance(media, dict):
            media = [media]
        return await self.invoke(
            Opcode.STORIES_SEND,
            clean(
                {
                    "media": list(media) if media else None,
                    "stories": stories,
                    "layers": layers,
                    "settings": settings,
                    "expiration": expiration,
                    "clickableLink": clickable_link,
                    "url": url,
                    "cid": cid if cid is not None else next_cid(),
                    **extra,
                }
            ),
        )

    async def edit_story(
        self, story_id: int, *, settings: dict[str, Any] | None = None, **extra: Any
    ) -> dict[str, Any]:
        """STORIES_EDIT (217). Меняет настройки опубликованной истории."""
        return await self.invoke(
            Opcode.STORIES_EDIT,
            clean({"storyId": story_id, "settings": settings, **extra}),
        )

    async def delete_stories(self, story_ids: list[int] | int) -> dict[str, Any]:
        """STORIES_DELETE (218)."""
        if isinstance(story_ids, int):
            story_ids = [story_ids]
        return await self.invoke(
            Opcode.STORIES_DELETE, {"storyIds": list(story_ids)}
        )

    async def delete_story(self, story_id: int) -> dict[str, Any]:
        """Одиночная обёртка над STORIES_DELETE."""
        return await self.delete_stories([story_id])

    # --- взаимодействие ----------------------------------------------------

    async def react_story(
        self,
        story_id: int,
        reaction: str = "❤️",
        *,
        owner_id: int | None = None,
        reaction_type: ReactionType | str = ReactionType.EMOJI,
        **extra: Any,
    ) -> dict[str, Any]:
        """STORIES_REACT (213). Реакция на историю."""
        return await self.invoke(
            Opcode.STORIES_REACT,
            clean(
                {
                    "storyId": story_id,
                    "owner": owner_id,
                    "reaction": {
                        "reactionType": str(reaction_type),
                        "id": str(reaction),
                    },
                    **extra,
                }
            ),
        )

    async def mark_story(
        self, story_id: int, owner_id: int | None = None, **extra: Any
    ) -> dict[str, Any]:
        """STORIES_MARK (214). Отмечает историю просмотренной."""
        return await self.invoke(
            Opcode.STORIES_MARK,
            clean({"storyId": story_id, "owner": owner_id, **extra}),
        )

    # --- статистика --------------------------------------------------------

    async def get_story_stats(self, story_ids: list[int] | int) -> dict[str, Any]:
        """STORIES_GET_STATS (211). Короткая статистика по историям."""
        if isinstance(story_ids, int):
            story_ids = [story_ids]
        return await self.invoke(
            Opcode.STORIES_GET_STATS, {"storyIds": list(story_ids)}
        )

    async def get_story_detailed_stats(
        self,
        story_id: int,
        *,
        marker: int | None = None,
        filter_: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """STORIES_GET_DETAILED_STATS (212). Кто именно смотрел и реагировал."""
        return await self.invoke(
            Opcode.STORIES_GET_DETAILED_STATS,
            clean(
                {"storyId": story_id, "marker": marker, "filter": filter_, **extra}
            ),
        )
