"""Простейший юзербот: отвечает на команды в своих чатах.

    python examples/echo_bot.py +79991234567
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maxion.raw import MaxClient, Router, Text, filters

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

router = Router("echo")


@router.on_message(filters.command("ping"))
async def ping(update):
    await update.reply("pong")


@router.on_message(filters.command("id"))
async def chat_id(update):
    await update.reply(
        Text("chat_id: ").code(str(update.chat_id)).newline()
        .text("message_id: ").code(str(update.message.id))
    )


@router.on_message(filters.command("echo"))
async def echo(update):
    body = update.text.split(maxsplit=1)
    await update.reply(body[1] if len(body) > 1 else "нечего повторять")


@router.on_message(filters.contains("спасибо") & filters.incoming)
async def thanks(update):
    await update.message.react("❤️")


async def main() -> None:
    phone = sys.argv[1] if len(sys.argv) > 1 else None
    client = MaxClient("echo.session")
    client.include_router(router)

    await client.start(phone=phone)
    me = client.me
    print(f"Вошли как {me.name} (id={me.id})")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
