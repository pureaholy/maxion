"""Выгружает содержимое аккаунта: чаты, контакты, сессии, историю.

    python examples/dump_account.py +79991234567
    python examples/dump_account.py +79991234567 --history -68093732121255
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maxion.raw import MaxClient


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phone", nargs="?")
    parser.add_argument("--history", type=int, help="выгрузить историю чата")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--out", type=Path, default=Path("dump"))
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    async with MaxClient("dump.session") as client:
        await client.start(phone=args.phone)
        print(f"Вошли как {client.me.name}")

        chats = await client.get_all_chats()
        _save(args.out / "chats.json", [c.to_dict() for c in chats])
        print(f"Чатов: {len(chats)}")
        for chat in chats[:20]:
            unread = f" ({chat.new_messages} непроч.)" if chat.new_messages else ""
            print(f"  {chat.id:>18}  {chat.type:<8} {chat.title or '—'}{unread}")

        contacts = [u async for u in client.iter_contacts()]
        _save(args.out / "contacts.json", [u.to_dict() for u in contacts])
        print(f"Контактов: {len(contacts)}")

        sessions = await client.get_sessions()
        _save(args.out / "sessions.json", [s.to_dict() for s in sessions])
        print("Активные сессии:")
        for session in sessions:
            mark = " <- текущая" if session.is_current else ""
            print(f"  {session.device_name} {session.app_version} {session.ip}{mark}")

        if args.history:
            messages = [
                m.to_dict()
                async for m in client.iter_history(args.history, limit=args.limit)
            ]
            path = args.out / f"history_{args.history}.json"
            _save(path, messages)
            print(f"Сообщений выгружено: {len(messages)} -> {path}")


def _save(path: Path, data) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


if __name__ == "__main__":
    asyncio.run(main())
