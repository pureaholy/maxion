"""Эхо-бот на официальном Bot API MAX.

    python examples/bot_echo.py <TOKEN>

Токен бота берётся у @MasterBot в MAX. В отличие от userbot-примеров, здесь
не нужен номер телефона — бот работает по своему токену через botapi.max.ru.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maxion.bot import Bot, filters

token = sys.argv[1] if len(sys.argv) > 1 else "PUT_TOKEN_HERE"
bot = Bot(token)


@bot.on_bot_started()
async def started(bot, update):
    await update.answer("Привет! Напиши /help или что угодно — отвечу эхом.")


@bot.on_message(filters.command("help"))
async def help_cmd(bot, update):
    await update.reply(
        "Я эхо-бот на **maxion**.\n"
        "Команды: /help. Любое сообщение вернётся обратно.",
        format="markdown",
    )


@bot.on_message(filters.command("id"))
async def chat_id(bot, update):
    await update.reply(f"chat_id: `{update.chat_id}`", format="markdown")


@bot.on_message(filters.text & ~filters.command("help", "id"))
async def echo(bot, update):
    await update.reply(update.text)


@bot.on_callback()
async def on_button(bot, update):
    await update.answer(f"Нажато: {update.payload}")


if __name__ == "__main__":
    print("Бот запущен (Ctrl+C — выход).")
    bot.run()
