"""Client — высокоуровневый клиент MAX."""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Sequence

from .enums import ChatAction, ChatMemberStatus, ParseMode
from .filters import Filter
from .handlers import (
    DeletedMessagesHandler,
    EditedMessageHandler,
    Handler,
    MessageHandler,
    RawUpdateHandler,
)
from .parser import parse
from .raw.client import MaxClient
from .raw.device import Device
from .types import Chat, ChatMember, Dialog, Message, User

log = logging.getLogger(__name__)


class StopPropagation(Exception):
    """Прекратить обработку события целиком."""


class ContinuePropagation(Exception):
    """Передать событие следующему обработчику в той же группе."""


class Client:
    """Высокоуровневый клиент MAX.

    ::

        app = Client("my_account", phone_number="+79991234567")

        @app.on_message(filters.command("start") & filters.private)
        async def start(client, message):
            await message.reply("привет")

        app.run()

    Низкоуровневый клиент со всеми 153 опкодами доступен как :attr:`raw`.
    """

    def __init__(
        self,
        name: str = "my_account",
        *,
        phone_number: str | None = None,
        password: str | None = None,
        workdir: str | os.PathLike[str] = ".",
        transport: str = "tcp",
        device_model: str | None = None,
        app_version: str | None = None,
        parse_mode: ParseMode = ParseMode.DEFAULT,
        device: Device | str | None = None,
        **kwargs: Any,
    ):
        self.name = name
        self.phone_number = phone_number
        self.password = password
        self.workdir = Path(workdir)
        self.parse_mode = parse_mode

        if device is None:
            device = Device.for_transport(
                "ANDROID" if transport in ("tcp", "tls", "mobile", "app") else "WEB"
            )
        elif isinstance(device, str):
            device = Device.for_transport(device.upper())
        if device_model:
            device.device_name = device_model
        if app_version:
            device.app_version = app_version

        self._raw = MaxClient(
            self.workdir / f"{name}.session",
            transport=transport,
            device=device,
            **kwargs,
        )
        self._groups: dict[int, list[Handler]] = defaultdict(list)
        self._started = False

        self._raw.router.on("raw")(self._feed)

    # --- доступ к слоям --------------------------------------------------

    @property
    def raw(self) -> MaxClient:
        """Низкоуровневый клиент: все опкоды, транспорт, сессия."""
        return self._raw

    @property
    def me(self) -> User | None:
        """Свой профиль, если уже вошли."""
        return User(self, self._raw.me) if self._raw.me else None

    @property
    def is_connected(self) -> bool:
        return self._raw.is_connected

    # --- жизненный цикл ---------------------------------------------------

    async def start(self) -> "Client":
        """Подключается и логинится; повторный вызов безвреден."""
        if self._started:
            return self
        await self._raw.connect()
        await self._raw.start(phone=self.phone_number, password=self.password)
        self._started = True
        log.info("Вошли как %s", self._raw.me.name if self._raw.me else "?")
        return self

    async def stop(self) -> "Client":
        await self._raw.disconnect()
        self._started = False
        return self

    async def __aenter__(self) -> "Client":
        return await self.start()

    async def __aexit__(self, *exc_info) -> None:
        await self.stop()

    def run(self, coroutine=None) -> Any:
        """Блокирующий запуск: поднимает клиент и держит его до остановки."""

        async def main():
            await self.start()
            try:
                if coroutine is not None:
                    return await coroutine
                await self._raw.run_until_disconnected()
            finally:
                if self._started:
                    await self.stop()

        return asyncio.run(main())

    async def idle(self) -> None:
        """Ждёт, пока соединение живо."""
        await self._raw.run_until_disconnected()

    # --- обработчики ------------------------------------------------------

    def add_handler(self, handler: Handler, group: int = 0) -> Handler:
        """Регистрирует обработчик в группе (меньше — раньше)."""
        self._groups[group].append(handler)
        return handler

    def remove_handler(self, handler: Handler, group: int = 0) -> None:
        if handler in self._groups.get(group, []):
            self._groups[group].remove(handler)

    def _decorator(self, handler_cls: type[Handler]):
        def outer(filters: Filter | None = None, group: int = 0):
            def decorator(func):
                self.add_handler(handler_cls(func, filters), group)
                return func

            return decorator

        return outer

    def on_message(self, filters: Filter | None = None, group: int = 0):
        return self._decorator(MessageHandler)(filters, group)

    def on_edited_message(self, filters: Filter | None = None, group: int = 0):
        return self._decorator(EditedMessageHandler)(filters, group)

    def on_deleted_messages(self, filters: Filter | None = None, group: int = 0):
        return self._decorator(DeletedMessagesHandler)(filters, group)

    def on_raw_update(self, filters: Filter | None = None, group: int = 0):
        return self._decorator(RawUpdateHandler)(filters, group)

    # --- диспетчер --------------------------------------------------------

    async def _feed(self, update) -> None:
        """Принимает событие низкоуровневого роутера и раздаёт обработчикам."""
        event = update.event
        payload: Any = update
        if event == "message":
            payload = Message(self, update.message)
            if getattr(update, "is_edit", False):
                event = "edited_message"

        for group in sorted(self._groups):
            for handler in self._groups[group]:
                if handler.event not in (event, "raw"):
                    continue
                target = update if handler.event == "raw" else payload
                try:
                    if not await handler.check(self, target):
                        continue
                except Exception:
                    log.exception("Ошибка в фильтре %s", handler)
                    continue
                try:
                    await handler.callback(self, target)
                except ContinuePropagation:
                    continue
                except StopPropagation:
                    return
                except Exception:
                    log.exception("Ошибка в обработчике %s", handler)
                break  # в группе срабатывает первый подошедший

    # --- сообщения --------------------------------------------------------

    def _parse(self, text: str, parse_mode: ParseMode | str | None):
        return parse(text, parse_mode if parse_mode is not None else self.parse_mode)

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        parse_mode: ParseMode | str | None = None,
        entities: Sequence[dict[str, Any]] | None = None,
        reply_to_message_id: str | None = None,
        disable_notification: bool = False,
        **kwargs: Any,
    ) -> Message:
        """Отправляет текстовое сообщение."""
        body, parsed = self._parse(text, parse_mode)
        raw = await self._raw.send_message(
            chat_id,
            body,
            elements=list(entities) if entities is not None else parsed,
            reply_to=reply_to_message_id,
            notify=not disable_notification,
            **kwargs,
        )
        return Message(self, raw)

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: str,
        text: str,
        *,
        parse_mode: ParseMode | str | None = None,
        **kwargs: Any,
    ) -> Message:
        body, parsed = self._parse(text, parse_mode)
        raw = await self._raw.edit_message(
            chat_id, message_id, body, elements=parsed, **kwargs
        )
        return Message(self, raw)

    async def delete_messages(
        self, chat_id: int, message_ids: Sequence[str] | str, *, revoke: bool = True
    ) -> None:
        """``revoke=True`` удаляет у всех, ``False`` — только у себя."""
        await self._raw.delete_messages(chat_id, message_ids, for_me=not revoke)

    async def forward_messages(
        self, chat_id: int, from_chat_id: int, message_ids: Sequence[str] | str
    ) -> list[Message]:
        if isinstance(message_ids, str):
            message_ids = [message_ids]
        raw = await self._raw.forward_messages(chat_id, from_chat_id, message_ids)
        return [Message(self, item) for item in raw]

    async def get_messages(
        self, chat_id: int, message_ids: Sequence[str] | str
    ) -> Message | list[Message]:
        single = isinstance(message_ids, str)
        raw = await self._raw.get_messages(chat_id, message_ids)
        messages = [Message(self, item) for item in raw]
        if single:
            return messages[0] if messages else None  # type: ignore[return-value]
        return messages

    async def get_chat_history(
        self, chat_id: int, *, limit: int = 100, offset_date: int | None = None
    ) -> AsyncIterator[Message]:
        """Асинхронный генератор сообщений — от новых к старым."""
        produced = 0
        async for raw in self._raw.iter_history(chat_id, limit=limit):
            if offset_date is not None and (raw.get("time") or 0) > offset_date:
                continue
            yield Message(self, raw)
            produced += 1
            if produced >= limit:
                return

    async def search_messages(
        self, query: str, *, chat_id: int | None = None, limit: int = 30
    ) -> dict[str, Any]:
        return await self._raw.search_messages(query, chat_id=chat_id, count=limit)

    async def read_chat_history(self, chat_id: int, message_id: str) -> None:
        await self._raw.read_message(chat_id, message_id)

    async def send_reaction(
        self, chat_id: int, message_id: str, emoji: str = "❤️"
    ) -> Any:
        return await self._raw.set_reaction(chat_id, message_id, emoji)

    async def send_chat_action(
        self, chat_id: int, action: ChatAction | str = ChatAction.TYPING
    ) -> None:
        raw = action.raw if isinstance(action, ChatAction) else str(action)
        await self._raw.send_typing(chat_id, raw)

    # --- медиа ------------------------------------------------------------

    async def send_photo(
        self, chat_id: int, photo, caption: str = "", **kwargs: Any
    ) -> Message:
        return Message(self, await self._raw.send_photo(chat_id, photo, caption, **kwargs))

    async def send_video(
        self, chat_id: int, video, caption: str = "", **kwargs: Any
    ) -> Message:
        return Message(self, await self._raw.send_video(chat_id, video, caption, **kwargs))

    async def send_document(
        self, chat_id: int, document, caption: str = "", **kwargs: Any
    ) -> Message:
        return Message(self, await self._raw.send_file(chat_id, document, caption, **kwargs))

    async def send_sticker(self, chat_id: int, sticker_id: int, **kwargs: Any) -> Message:
        return Message(self, await self._raw.send_sticker(chat_id, sticker_id, **kwargs))

    async def download_media(
        self, message: Message, *, file_name: str | os.PathLike[str] | None = None
    ) -> Path | None:
        """Скачивает первое вложение сообщения."""
        attach = None
        for candidate in message._raw.attaches:
            if candidate.type in ("PHOTO", "VIDEO", "FILE", "AUDIO"):
                attach = candidate
                break
        if attach is None:
            return None

        chat_id, message_id = message._raw.chat_id, message.id
        if attach.type == "FILE":
            url = await self._raw.get_file_url(chat_id, message_id, attach.file_id)
            default = attach.name or f"{attach.file_id}.bin"
        elif attach.type == "VIDEO":
            urls = await self._raw.get_video_url(chat_id, message_id, attach.video_id)
            url = next(iter(urls.values()), None)
            default = f"{attach.video_id}.mp4"
        elif attach.type == "AUDIO":
            data = await self._raw.get_audio_url(chat_id, message_id, attach.audio_id)
            url = data.get("url")
            default = f"{attach.audio_id}.ogg"
        else:
            url, default = attach.url, f"{attach.photo_id}.jpg"
        if not url:
            return None
        return await self._raw.download(url, file_name or default)

    # --- чаты -------------------------------------------------------------

    async def get_chat(self, chat_id: int) -> Chat | None:
        raw = await self._raw.get_chat(chat_id)
        return Chat(self, raw) if raw else None

    async def get_dialogs(self, *, limit: int | None = None) -> AsyncIterator[Dialog]:
        async for raw in self._raw.iter_chats(limit=limit):
            yield Dialog(self, raw)

    async def join_chat(self, link: str) -> Chat | None:
        raw = await self._raw.join_chat(link)
        return Chat(self, raw) if raw else None

    async def leave_chat(self, chat_id: int) -> None:
        await self._raw.leave_chat(chat_id)

    async def set_chat_title(self, chat_id: int, title: str) -> None:
        await self._raw.set_chat_title(chat_id, title)

    async def set_chat_description(self, chat_id: int, description: str) -> None:
        await self._raw.set_chat_description(chat_id, description)

    async def pin_chat_message(
        self, chat_id: int, message_id: str, *, disable_notification: bool = False
    ) -> None:
        await self._raw.pin_message(chat_id, message_id, notify=not disable_notification)

    async def unpin_chat_message(self, chat_id: int) -> None:
        await self._raw.unpin_message(chat_id)

    async def get_chat_members(
        self, chat_id: int, *, limit: int = 200, query: str | None = None
    ) -> list[ChatMember]:
        raw = await self._raw.get_members(chat_id, count=limit, query=query)
        return [ChatMember(self, item) for item in raw]

    async def add_chat_members(
        self, chat_id: int, user_ids: Sequence[int] | int
    ) -> None:
        await self._raw.add_members(chat_id, user_ids)

    async def ban_chat_member(self, chat_id: int, user_id: int) -> None:
        await self._raw.block_members(chat_id, user_id)

    async def unban_chat_member(self, chat_id: int, user_id: int) -> None:
        await self._raw.update_members(chat_id, user_id, "unblock")

    async def promote_chat_member(
        self, chat_id: int, user_id: int, *, permissions: list[str] | None = None
    ) -> None:
        await self._raw.promote_members(chat_id, user_id, permissions)

    async def demote_chat_member(self, chat_id: int, user_id: int) -> None:
        await self._raw.demote_members(chat_id, user_id)

    async def get_chat_member(self, chat_id: int, user_id: int) -> ChatMember | None:
        for member in await self.get_chat_members(chat_id):
            if member.user_id == user_id:
                return member
        return None

    # --- пользователи ------------------------------------------------------

    async def get_me(self) -> User | None:
        raw = await self._raw.get_me()
        return User(self, raw) if raw else None

    async def get_users(
        self, user_ids: Sequence[int] | int
    ) -> User | list[User]:
        single = isinstance(user_ids, int)
        raw = await self._raw.get_contacts(user_ids)
        users = [User(self, item) for item in raw]
        if single:
            return users[0] if users else None  # type: ignore[return-value]
        return users

    async def get_contacts(self) -> list[User]:
        return [User(self, raw) async for raw in self._raw.iter_contacts()]

    async def block_user(self, user_id: int) -> None:
        await self._raw.block_user(user_id)

    async def unblock_user(self, user_id: int) -> None:
        await self._raw.unblock_user(user_id)

    async def resolve_phone(self, phone: str) -> User | None:
        """Ищет пользователя по номеру телефона."""
        raw = await self._raw.get_contact_by_phone(phone)
        return User(self, raw) if raw else None

    async def set_profile_name(
        self, first_name: str, last_name: str | None = None
    ) -> User:
        raw = await self._raw.update_profile(
            first_name=first_name, last_name=last_name
        )
        return User(self, raw)

    # --- прочее -----------------------------------------------------------

    async def invoke(self, opcode, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Вызывает произвольный опкод протокола напрямую."""
        return await self._raw.call(opcode, payload)

    def __repr__(self) -> str:
        state = "запущен" if self._started else "остановлен"
        return f"<Client {self.name!r} {state}>"


async def idle() -> None:
    """Блокируется до Ctrl+C."""
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    import signal

    for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):  # Windows
            pass
    await stop.wait()


def compose(clients: Sequence[Client]) -> Any:
    """Запускает несколько клиентов разом и ждёт остановки."""

    async def main():
        await asyncio.gather(*(client.start() for client in clients))
        try:
            await idle()
        finally:
            await asyncio.gather(*(client.stop() for client in clients))

    return asyncio.run(main())


__all__ = ["Client", "idle", "compose", "StopPropagation", "ContinuePropagation"]
