"""Высокоуровневый слой библиотеки."""

from __future__ import annotations

import asyncio

import pytest

from maxion import Client, ContinuePropagation, StopPropagation, enums, filters
from maxion.parser import parse_html
from maxion.raw.opcodes import Opcode
from maxion.raw.protocol import Packet
from maxion.types import Chat, Message, User
from tests.test_client import FakeTransport

RESPONSES = {
    Opcode.SESSION_INIT: {"isVpn": False},
    Opcode.MSG_SEND: {
        "message": {"id": "42", "chatId": -1, "text": "привет", "sender": 7}
    },
    Opcode.CHATS_LIST: {
        "marker": 0,
        "chats": [{"id": -1, "type": "CHAT", "title": "Тест", "newMessages": 3}],
    },
    Opcode.CHAT_INFO: {"chats": [{"id": -1, "type": "CHAT", "title": "Тест"}]},
    Opcode.CONTACT_INFO: {
        "contacts": [{"id": 7, "names": [{"name": "Артур"}], "link": "artur"}]
    },
}


@pytest.fixture
async def app(tmp_path):
    transport = FakeTransport(dict(RESPONSES))
    client = Client(
        "test",
        workdir=tmp_path,
        transport=transport,
        ping_interval=0,
        auto_reconnect=False,
    )
    await client.raw.connect()
    client._started = True
    try:
        yield client
    finally:
        await client.stop()


def push(app: Client, text: str, *, chat_id: int = -1, sender: int = 7) -> None:
    app.raw.transport.push(  # type: ignore[attr-defined]
        Packet(
            opcode=Opcode.NOTIF_MESSAGE,
            cmd=1,
            seq=0,
            payload={
                "chatId": chat_id,
                "message": {"id": "1", "chatId": chat_id, "text": text, "sender": sender},
            },
        )
    )


async def settle(condition, tries: int = 30) -> None:
    for _ in range(tries):
        await asyncio.sleep(0.01)
        if condition():
            return


# --- типы -------------------------------------------------------------------


async def test_send_message_returns_rich_message(app):
    message = await app.send_message(-1, "привет")

    assert isinstance(message, Message)
    assert message.id == "42"
    assert message.text == "привет"
    assert isinstance(message.chat, Chat)
    assert message.chat.id == -1
    assert isinstance(message.from_user, User)
    assert message.from_user.id == 7


async def test_chat_type_maps_to_high_level_enum(app):
    chat = await app.get_chat(-1)

    assert chat.type is enums.ChatType.GROUP
    assert chat.title == "Тест"


async def test_get_users_single_and_list(app):
    one = await app.get_users(7)
    many = await app.get_users([7])

    assert isinstance(one, User) and one.full_name == "Артур"
    assert one.username == "artur"
    assert isinstance(many, list) and len(many) == 1


async def test_get_dialogs_yields_dialog_objects(app):
    dialogs = [d async for d in app.get_dialogs(limit=5)]

    assert len(dialogs) == 1
    assert dialogs[0].chat.title == "Тест"
    assert dialogs[0].unread_messages_count == 3


# --- разметка ---------------------------------------------------------------


async def test_markdown_is_the_default_parse_mode(app):
    await app.send_message(-1, "это **важно**")

    sent = app.raw.transport.sent[-1].payload["message"]  # type: ignore[attr-defined]
    assert sent["text"] == "это важно"
    assert sent["elements"] == [{"type": "STRONG", "from": 4, "length": 5}]


async def test_parse_mode_disabled_keeps_text_as_is(app):
    await app.send_message(-1, "это **важно**", parse_mode=enums.ParseMode.DISABLED)

    sent = app.raw.transport.sent[-1].payload["message"]  # type: ignore[attr-defined]
    assert sent["text"] == "это **важно**"
    assert sent["elements"] == []


async def test_parse_mode_html(app):
    await app.send_message(
        -1, 'жирный <b>раз</b> и <a href="https://max.ru">ссылка</a>',
        parse_mode=enums.ParseMode.HTML,
    )

    sent = app.raw.transport.sent[-1].payload["message"]  # type: ignore[attr-defined]
    assert sent["text"] == "жирный раз и ссылка"
    assert sent["elements"] == [
        {"type": "STRONG", "from": 7, "length": 3},
        {"type": "LINK", "from": 13, "length": 6, "url": "https://max.ru"},
    ]


def test_parse_html_handles_nesting():
    text, elements = parse_html("<b>жир <i>и курсив</i></b>")

    assert text == "жир и курсив"
    kinds = {e["type"] for e in elements}
    assert kinds == {"STRONG", "EMPHASIZED"}


# --- фильтры ----------------------------------------------------------------


async def test_command_filter_fills_message_command(app):
    seen: list[list[str]] = []

    @app.on_message(filters.command("start"))
    async def handler(_client, message):
        seen.append(message.command)

    push(app, "/start arg1 arg2")
    await settle(lambda: seen)

    assert seen == [["start", "arg1", "arg2"]]


async def test_filters_combine_with_operators(app):
    hits: list[str] = []

    @app.on_message(filters.text & ~filters.command("skip"))
    async def handler(_client, message):
        hits.append(message.text)

    push(app, "обычный текст")
    push(app, "/skip")
    await settle(lambda: hits)

    assert hits == ["обычный текст"]


async def test_regex_filter_exposes_matches(app):
    found: list[str] = []

    @app.on_message(filters.regex(r"код (\d+)"))
    async def handler(_client, message):
        found.append(message.matches[0].group(1))

    push(app, "мой код 4242")
    await settle(lambda: found)

    assert found == ["4242"]


# --- обработчики и группы ---------------------------------------------------


async def test_first_matching_handler_in_group_wins(app):
    order: list[str] = []

    @app.on_message(filters.text)
    async def first(_client, _message):
        order.append("first")

    @app.on_message(filters.text)
    async def second(_client, _message):
        order.append("second")

    push(app, "привет")
    await settle(lambda: order)

    assert order == ["first"]


async def test_continue_propagation_passes_to_next_handler(app):
    order: list[str] = []

    @app.on_message(filters.text)
    async def first(_client, _message):
        order.append("first")
        raise ContinuePropagation

    @app.on_message(filters.text)
    async def second(_client, _message):
        order.append("second")

    push(app, "привет")
    await settle(lambda: len(order) == 2)

    assert order == ["first", "second"]


async def test_groups_run_in_order_and_stop_propagation(app):
    order: list[str] = []

    @app.on_message(filters.text, group=1)
    async def later(_client, _message):
        order.append("group1")

    @app.on_message(filters.text, group=0)
    async def earlier(_client, _message):
        order.append("group0")
        raise StopPropagation

    push(app, "привет")
    await settle(lambda: order)
    await asyncio.sleep(0.05)

    assert order == ["group0"]


async def test_raw_handler_sees_every_frame(app):
    names: list[str] = []

    @app.on_raw_update()
    async def handler(_client, update):
        names.append(update.name)

    push(app, "привет")
    await settle(lambda: names)

    assert "NOTIF_MESSAGE" in names


# --- связанные методы --------------------------------------------------------


async def test_message_reply_quotes_by_default(app):
    replies: list[Message] = []

    @app.on_message(filters.text)
    async def handler(_client, message):
        replies.append(await message.reply("ответ"))

    push(app, "вопрос")
    await settle(lambda: replies)

    link = app.raw.transport.sent[-1].payload["message"]["link"]  # type: ignore[attr-defined]
    assert link == {"type": "REPLY", "messageId": "1"}
    assert replies[0].text == "привет"  # то, что вернул фейковый сервер


async def test_message_reply_without_quote(app):
    message = await app.send_message(-1, "первое")
    await message.reply("второе", quote=False)

    sent = app.raw.transport.sent[-1].payload["message"]  # type: ignore[attr-defined]
    assert "link" not in sent


async def test_client_exposes_raw_layer(app):
    """Низкоуровневый слой должен оставаться доступным."""
    assert app.raw.transport is not None
    assert hasattr(app.raw, "send_message")
    assert hasattr(app.raw, "stories_feed") is False  # опечатки не проходят
    assert callable(app.raw.get_stories_feed)
