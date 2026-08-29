"""Просмотр историй из ленты.

    python examples/stories_feed.py                      # лента: кто что выложил
    python examples/stories_feed.py --owner 123456       # истории одного автора
    python examples/stories_feed.py --view               # пометить просмотренными
    python examples/stories_feed.py --react 42           # лайкнуть историю
    python examples/stories_feed.py --dump stories.jsonl # сохранить сырые ответы

Из всей группы STORIES_* схемой из клиента подтверждён только STORIES_LIST
(``cursor``/``count`` -> ``cursor``/``storiesPreviews``). Поэтому пример не
полагается на точные имена полей: он вытаскивает их по нескольким вариантам,
а с ``--dump`` складывает сырые payload в JSONL для tools/infer_schema.py.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maxion.raw import MaxClient
from maxion.raw.errors import MaxError

# Ключи, под которыми в превью может лежать одно и то же.
OWNER_KEYS = ("ownerId", "owner", "userId", "authorId", "chatId")
STORY_LIST_KEYS = ("stories", "storyIds", "items", "previews")
STORY_ID_KEYS = ("id", "storyId")


def _first(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if data.get(key) is not None:
            return data[key]
    return None


def _owner_id(preview: dict[str, Any]) -> int | None:
    value = _first(preview, OWNER_KEYS)
    if isinstance(value, dict):
        value = _first(value, ("id", "userId"))
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _story_ids(preview: dict[str, Any]) -> list[int]:
    raw = _first(preview, STORY_LIST_KEYS) or []
    ids: list[int] = []
    for item in raw if isinstance(raw, list) else []:
        value = _first(item, STORY_ID_KEYS) if isinstance(item, dict) else item
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            continue
    return ids


class Dump:
    """Складывает сырые payload, чтобы потом скормить infer_schema."""

    def __init__(self, path: Path | None):
        self.path = path
        self.count = 0

    def add(self, opcode: int, payload: dict[str, Any]) -> None:
        if self.path is None:
            return
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {"opcode": opcode, "direction": "in", "payload": payload},
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )
        self.count += 1


async def show_feed(client: MaxClient, args, dump: Dump) -> None:
    """Проходит ленту и печатает, у кого что есть."""
    previews: list[dict[str, Any]] = []
    async for preview in client.iter_stories_feed(limit=args.limit):
        previews.append(preview)
        dump.add(208, preview)

    if not previews:
        print("Лента историй пуста")
        return

    owner_ids = [oid for p in previews if (oid := _owner_id(p)) is not None]
    names: dict[int, str] = {}
    if owner_ids:
        try:
            for user in await client.get_contacts(owner_ids):
                if user.id is not None:
                    names[user.id] = user.name
        except MaxError as exc:
            print(f"! имена авторов не подтянулись: {exc}")

    print(f"В ленте авторов: {len(previews)}\n")
    for preview in previews:
        owner = _owner_id(preview)
        ids = _story_ids(preview)
        title = names.get(owner, f"id{owner}") if owner else "?"
        unseen = "" if preview.get("viewed") else "  • новое"
        print(f"{title:<28} историй: {len(ids) or '?':<4}{unseen}")
        if args.verbose:
            print(f"    {json.dumps(preview, ensure_ascii=False, default=str)[:300]}")
        if owner is not None and (args.details or args.view):
            await show_owner(client, owner, args, dump, indent="    ")
    print()


async def show_owner(
    client: MaxClient, owner_id: int, args, dump: Dump, indent: str = ""
) -> None:
    """Печатает истории одного автора и, если попросили, отмечает просмотр."""
    try:
        stories = await client.get_stories_by_owner(owner_id, count=args.limit)
    except MaxError as exc:
        print(f"{indent}! истории автора {owner_id} не открылись: {exc}")
        return

    if not stories:
        print(f"{indent}(историй нет)")
        return

    for story in stories:
        dump.add(210, story.to_dict())
        created = story.created_at.strftime("%d.%m %H:%M") if story.created_at else "?"
        views = f"просмотров {story.views}" if story.views is not None else ""
        seen = "просмотрено" if story.is_viewed else "не просмотрено"
        print(f"{indent}#{story.id}  {created}  {seen}  {views}")

        if args.view and story.id is not None and not story.is_viewed:
            try:
                await client.mark_story(story.id)
                print(f"{indent}  -> отмечено просмотренным")
            except MaxError as exc:
                print(f"{indent}  ! отметить не вышло: {exc}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--phone")
    parser.add_argument("--owner", type=int, help="истории конкретного автора")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--details", action="store_true", help="раскрыть каждого автора")
    parser.add_argument("--view", action="store_true", help="отмечать просмотренными")
    parser.add_argument("--react", type=int, metavar="STORY_ID", help="лайкнуть историю")
    parser.add_argument("--verbose", action="store_true", help="печатать сырые превью")
    parser.add_argument("--dump", type=Path, help="сохранить сырые payload в JSONL")
    args = parser.parse_args()

    dump = Dump(args.dump)

    async with MaxClient("stories.session", device="android") as client:
        await client.start(phone=args.phone)
        print(f"Вошли как {client.me.name}\n")

        if args.react is not None:
            result = await client.react_story(args.react)
            print(f"Реакция отправлена: {result}")
        elif args.owner is not None:
            await show_owner(client, args.owner, args, dump)
        else:
            await show_feed(client, args, dump)

    if dump.path:
        print(f"Сохранено записей: {dump.count} -> {dump.path}")
        print(f"Схемы: python -m tools.infer_schema {dump.path} --markdown docs/stories.md")


if __name__ == "__main__":
    asyncio.run(main())
