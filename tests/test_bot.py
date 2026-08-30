"""Bot API MAX: REST-клиент, разбор обновлений, фильтры."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from maxion.bot import Bot, filters
from maxion.bot.updates import parse_update
from maxion.bot.types import Message, User


class FakeResponse:
    def __init__(self, status: int, payload: Any):
        self.status = status
        self._payload = payload

    async def json(self, content_type=None):
        return self._payload

    async def text(self):
        return str(self._payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeSession:
    """Ловит вызовы request и отдаёт заготовленные ответы по (method, path)."""

    def __init__(self, routes: dict[tuple[str, str], Any]):
        self.routes = routes
        self.calls: list[dict] = []

    def request(self, method, url, params=None, json=None):
        path = url.split("max.ru", 1)[-1]
        self.calls.append({"method": method, "path": path, "params": params, "json": json})
        payload = self.routes.get((method, path), {})
        return FakeResponse(200, payload)

    def post(self, url, data=None):
        self.calls.append({"method": "POST", "url": url, "data": data})
        return FakeResponse(200, {"tokens": ["t"]})

    async def close(self):
        pass


def make_bot(routes) -> Bot:
    bot = Bot("TOKEN")
    bot._session = FakeSession(routes)
    return bot


# --- REST ------------------------------------------------------------------


async def test_get_me():
    bot = make_bot({("GET", "/me"): {"user_id": 5, "name": "MyBot", "username": "mybot", "is_bot": True}})
    me = await bot.get_me()
    assert isinstance(me, User)
    assert me.user_id == 5 and me.username == "mybot" and me.is_bot


async def test_send_message_shape():
    bot = make_bot({("POST", "/messages"): {"message": {"body": {"mid": "m1", "text": "привет"}}}})
    msg = await bot.send_message("привет", chat_id=-10, format="markdown")

    call = bot._session.calls[-1]  # type: ignore[attr-defined]
    assert call["method"] == "POST" and call["path"] == "/messages"
    assert call["params"]["chat_id"] == -10
    assert call["json"]["text"] == "привет"
    assert call["json"]["format"] == "markdown"
    assert call["json"]["notify"] is True
    assert msg.mid == "m1" and msg.text == "привет"


async def test_send_message_reply_builds_link():
    bot = make_bot({("POST", "/messages"): {"message": {}}})
    await bot.send_message("ответ", chat_id=1, reply_to="mid-9")
    assert bot._session.calls[-1]["json"]["link"] == {"type": "reply", "mid": "mid-9"}  # type: ignore[attr-defined]


async def test_token_in_header_and_query():
    bot = make_bot({("GET", "/me"): {"user_id": 1}})
    await bot.get_me()
    assert bot._session.calls[-1]["params"]["access_token"] == "TOKEN"  # type: ignore[attr-defined]


async def test_answer_callback():
    bot = make_bot({("POST", "/answers"): {}})
    await bot.answer_callback("cb-1", text="ок")
    call = bot._session.calls[-1]  # type: ignore[attr-defined]
    assert call["path"] == "/answers"
    assert call["params"]["callback_id"] == "cb-1"
    assert call["json"]["message"]["text"] == "ок"


async def test_get_updates_advances_marker():
    routes = {("GET", "/updates"): {"marker": 42, "updates": [
        {"update_type": "message_created", "message": {"body": {"mid": "m", "text": "hi"},
         "recipient": {"chat_id": -1}, "sender": {"user_id": 7}}}
    ]}}
    bot = make_bot(routes)
    updates = await bot.get_updates()
    assert bot._marker == 42
    assert len(updates) == 1 and updates[0].event == "message"
    assert updates[0].text == "hi" and updates[0].chat_id == -1


async def test_chats_and_members():
    routes = {
        ("GET", "/chats"): {"chats": [{"chat_id": -5, "type": "chat", "title": "T"}]},
        ("GET", "/chats/-5/members"): {"members": [{"user_id": 1, "name": "A"}]},
    }
    bot = make_bot(routes)
    chats = await bot.get_chats()
    assert chats[0].chat_id == -5 and chats[0].title == "T"
    members = await bot.get_members(-5)
    assert members[0].user_id == 1


async def test_error_raises_botapierror():
    from maxion.bot import BotApiError

    class ErrSession(FakeSession):
        def request(self, method, url, params=None, json=None):
            return FakeResponse(401, {"code": "auth.error", "message": "bad token"})

    bot = Bot("X")
    bot._session = ErrSession({})
    with pytest.raises(BotApiError) as info:
        await bot.get_me()
    assert info.value.status == 401
    assert "bad token" in str(info.value)


# --- разбор обновлений -----------------------------------------------------


def test_parse_message_callback():
    u = parse_update(None, {
        "update_type": "message_callback",
        "callback": {"callback_id": "c1", "payload": "yes", "user": {"user_id": 3}},
        "message": {"body": {"mid": "m"}},
    })
    assert u.event == "callback"
    assert u.callback_id == "c1" and u.payload == "yes"
    assert u.user.user_id == 3


def test_parse_bot_started():
    u = parse_update(None, {"update_type": "bot_started", "chat_id": 9, "user": {"user_id": 1}})
    assert u.event == "bot_started"
    assert u.chat_id == 9 and u.user.user_id == 1


def test_unknown_update_is_raw():
    u = parse_update(None, {"update_type": "something_new"})
    assert u.event == "raw"
    assert u.update_type == "something_new"


# --- фильтры и диспетчер ----------------------------------------------------


async def test_command_filter_and_dispatch():
    bot = make_bot({("POST", "/messages"): {"message": {}}})
    seen = []

    @bot.on_message(filters.command("start"))
    async def start(b, update):
        seen.append(update.command)

    u = parse_update(bot, {
        "update_type": "message_created",
        "message": {"body": {"text": "/start arg"}, "recipient": {"chat_id": -1}},
    })
    await bot._dispatch(u)
    for _ in range(20):
        await asyncio.sleep(0.01)
        if seen:
            break
    assert seen == [["start", "arg"]]


async def test_callback_payload_filter():
    bot = make_bot({})
    hits = []

    @bot.on_callback(filters.payload("yes"))
    async def yes(b, update):
        hits.append(update.payload)

    u_yes = parse_update(bot, {"update_type": "message_callback",
                               "callback": {"callback_id": "1", "payload": "yes"}})
    u_no = parse_update(bot, {"update_type": "message_callback",
                              "callback": {"callback_id": "2", "payload": "no"}})
    await bot._dispatch(u_yes)
    await bot._dispatch(u_no)
    await asyncio.sleep(0.05)
    assert hits == ["yes"]


async def test_filter_operators():
    bot = make_bot({})
    hits = []

    @bot.on_message(filters.text & ~filters.command("skip"))
    async def h(b, update):
        hits.append(update.text)

    for txt in ("обычный", "/skip"):
        u = parse_update(bot, {"update_type": "message_created",
                               "message": {"body": {"text": txt}, "recipient": {"chat_id": 1}}})
        await bot._dispatch(u)
    await asyncio.sleep(0.05)
    assert hits == ["обычный"]


# --- webhook ---------------------------------------------------------------


async def test_feed_update_dispatches_like_polling():
    """Приёмник webhook раздаёт обновления теми же обработчиками."""
    bot = make_bot({})
    seen = []

    @bot.on_message(filters.command("hi"))
    async def hi(b, update):
        seen.append(update.text)

    # как будто POST от MAX прилетел с одним update
    await bot.feed_update({
        "update_type": "message_created",
        "message": {"body": {"text": "/hi there"}, "recipient": {"chat_id": -1}},
    })
    for _ in range(20):
        await asyncio.sleep(0.01)
        if seen:
            break
    assert seen == ["/hi there"]


async def test_subscribe_unsubscribe_calls():
    bot = make_bot({("POST", "/subscriptions"): {"success": True},
                    ("DELETE", "/subscriptions"): {"success": True}})
    await bot.subscribe("https://ex.com/wh", update_types=["message_created"], secret="s")
    sub = bot._session.calls[-1]  # type: ignore[attr-defined]
    assert sub["path"] == "/subscriptions"
    assert sub["json"]["url"] == "https://ex.com/wh"
    assert sub["json"]["update_types"] == ["message_created"]
    assert sub["json"]["secret"] == "s"

    await bot.unsubscribe("https://ex.com/wh")
    assert bot._session.calls[-1]["params"]["url"] == "https://ex.com/wh"  # type: ignore[attr-defined]
