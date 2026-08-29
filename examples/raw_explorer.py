"""Интерактивная консоль для опкодов: щупаем API руками.

    python examples/raw_explorer.py +79991234567

    > 53 {"marker": 0, "count": 5}
    > CHATS_LIST {"count": 5}
    > watch            печатать все входящие кадры
    > quit

Всё, что приходит от сервера, попутно пишется в raw_dump.jsonl -- этот файл
можно скормить tools/infer_schema.py.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maxion.raw import MaxClient, Opcode, opcode_name
from maxion.raw.errors import MaxError

DUMP = Path("raw_dump.jsonl")


async def main() -> None:
    phone = sys.argv[1] if len(sys.argv) > 1 else None
    client = MaxClient("explorer.session")
    watching = False

    @client.on_raw()
    async def sink(update):
        with DUMP.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "opcode": update.opcode,
                        "name": update.name,
                        "direction": "in",
                        "payload": update.payload,
                    },
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )
        if watching:
            print(f"\n<- {update.name}({update.opcode}) {update.payload}\n> ", end="")

    await client.start(phone=phone)
    print(f"Вошли как {client.me.name}. Опкодов доступно: {len(list(Opcode))}")
    print("Формат: <опкод или имя> <json>. help -- список опкодов, quit -- выход.")

    while True:
        line = (await asyncio.to_thread(input, "> ")).strip()
        if not line:
            continue
        if line in ("quit", "exit"):
            break
        if line == "watch":
            watching = not watching
            print("слежение:", "вкл" if watching else "выкл")
            continue
        if line == "help":
            for op in sorted(Opcode, key=int):
                print(f"  {int(op):>4}  {op.name}")
            continue

        head, _, tail = line.partition(" ")
        try:
            opcode = int(head) if head.isdigit() else int(Opcode[head.upper()])
        except (KeyError, ValueError):
            print(f"не знаю опкод {head!r}")
            continue
        try:
            payload = json.loads(tail) if tail.strip() else {}
        except json.JSONDecodeError as exc:
            print(f"плохой json: {exc}")
            continue

        try:
            result = await client.invoke(opcode, payload)
        except MaxError as exc:
            print(f"! {exc}")
            continue
        print(f"<- {opcode_name(opcode)}")
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str)[:4000])

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
