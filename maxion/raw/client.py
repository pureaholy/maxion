"""Клиент MAX: соединение, RPC, события."""

from __future__ import annotations

import asyncio
import itertools
import logging
import os
import signal
from typing import Any, Awaitable, Callable

from .const import (
    PING_INTERVAL,
    RECONNECT_DELAYS,
    REQUEST_TIMEOUT,
)
from .errors import (
    MaxError,
    NotAuthorizedError,
    NotConnectedError,
    RpcError,
    SessionExpiredError,
    TimeoutError_,
    TransportError,
    rpc_error,
)
from .device import Device
from .events import Update, parse_update
from .methods import Methods
from .opcodes import NOTIFICATION_OPCODES, Opcode
from .protocol import Packet
from .router import Router
from .session import Session
from .transport import BaseTransport, build_transport
from .types import Chat, Profile, User

log = logging.getLogger(__name__)

CodeCallback = Callable[[], str | int | Awaitable[str | int]]

_DEVICE_PRESETS = {
    "web": Device.web,
    "android": Device.android,
    "ios": Device.ios,
    "desktop": Device.desktop,
}


class MaxClient(Methods):
    """Асинхронный клиент внутреннего API MAX.

    Пример::

        async with MaxClient("my.session") as client:
            await client.start(phone="+79991234567")
            await client.send_message(chat_id, "привет")
    """

    def __init__(
        self,
        session: str | os.PathLike[str] | Session | None = None,
        *,
        transport: str | BaseTransport = "ws",
        device: "Device | str | None" = None,
        device_id: str | None = None,
        user_agent: dict[str, Any] | None = None,
        auto_reconnect: bool = True,
        ping_interval: float = PING_INTERVAL,
        request_timeout: float = REQUEST_TIMEOUT,
        router: Router | None = None,
        **transport_kwargs: Any,
    ):
        if isinstance(session, Session):
            self.session = session
        elif session is None:
            self.session = Session()
        else:
            self.session = Session.load(session)
        if device_id:
            self.session.device_id = device_id

        self._transport_factory = (
            (lambda: transport)
            if isinstance(transport, BaseTransport)
            else (lambda: build_transport(transport, **transport_kwargs))
        )
        self.transport: BaseTransport = self._transport_factory()
        if device is None:
            self.device = Device.for_transport(self.transport.device_type)
        elif isinstance(device, str):
            self.device = _DEVICE_PRESETS[device.lower()]()
        else:
            self.device = device
        self.user_agent = user_agent or {}
        self.auto_reconnect = auto_reconnect
        self.ping_interval = ping_interval
        self.request_timeout = request_timeout
        self.router = router or Router("client")

        self.me: Profile | None = None
        self.contacts_cache: dict[int, User] = {}
        self.chats_cache: dict[int, Chat] = {}
        self.config: dict[str, Any] = {}

        self._seq = itertools.count(1)
        self._pending: dict[int, asyncio.Future[Packet]] = {}
        self._attach_waiters: dict[tuple[str, int], asyncio.Future[dict[str, Any]]] = {}
        self._recv_task: asyncio.Task | None = None
        self._ping_task: asyncio.Task | None = None
        self._http_session: Any = None
        self._closing = False
        self._disconnected = asyncio.Event()
        self._connected_once = False

    # --- готовые конфигурации ----------------------------------------------

    @classmethod
    def mobile(
        cls,
        session: str | os.PathLike[str] | Session | None = None,
        **kwargs: Any,
    ) -> "MaxClient":
        """Клиент, неотличимый от мобильного приложения.

        Бинарный протокол поверх TLS (``api.oneme.ru:443``, ver 10, MsgPack +
        LZ4) и android-профиль устройства, снятый с APK. Именно этот режим
        умеет авторизацию по номеру телефона.
        """
        kwargs.setdefault("transport", "tcp")
        kwargs.setdefault("device", Device.android())
        return cls(session, **kwargs)

    @classmethod
    def web(
        cls,
        session: str | os.PathLike[str] | Session | None = None,
        **kwargs: Any,
    ) -> "MaxClient":
        """Клиент как web.max.ru: WebSocket и JSON-кадры."""
        kwargs.setdefault("transport", "ws")
        kwargs.setdefault("device", Device.web())
        return cls(session, **kwargs)

    # --- состояние ---------------------------------------------------------

    @property
    def user_id(self) -> int | None:
        return self.session.user_id

    @property
    def is_connected(self) -> bool:
        return self.transport.is_connected

    @property
    def is_authorized(self) -> bool:
        return bool(self.session.token and self.me is not None)

    # --- соединение --------------------------------------------------------

    async def connect(self) -> None:
        """Открывает соединение и отправляет SESSION_INIT."""
        if self.transport.is_connected:
            return
        self._closing = False
        self._disconnected.clear()
        await self.transport.connect()
        self._recv_task = asyncio.create_task(self._recv_loop(), name="maxion-recv")
        await self.session_init(
            user_agent={**self.device.to_user_agent(), **self.user_agent},
            **self.device.session_extras(),
        )
        self._connected_once = True
        log.info("Соединение установлено как %s", self.device)

    async def disconnect(self) -> None:
        """Закрывает соединение и все фоновые задачи."""
        self._closing = True
        await self._stop_ping()
        if self._recv_task:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except (asyncio.CancelledError, Exception):
                pass
            self._recv_task = None
        await self.transport.close()
        for future in self._pending.values():
            if not future.done():
                future.set_exception(TransportError("Соединение закрыто"))
        self._pending.clear()
        if self._http_session is not None:
            await self._http_session.close()
            self._http_session = None
        self._disconnected.set()
        log.info("Соединение закрыто")

    close = disconnect

    async def __aenter__(self) -> "MaxClient":
        await self.connect()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.disconnect()

    # --- RPC ---------------------------------------------------------------

    async def request(
        self,
        opcode: Opcode | int,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Packet:
        """Отправляет запрос и ждёт ответный кадр."""
        if not self.transport.is_connected:
            raise NotConnectedError("Клиент не подключён — вызовите connect()")
        seq = next(self._seq) & 0xFFFF
        packet = Packet(
            opcode=int(opcode),
            payload=payload or {},
            seq=seq,
            cmd=0,
            ver=self.transport.rpc_version,
        )
        future: asyncio.Future[Packet] = asyncio.get_running_loop().create_future()
        self._pending[seq] = future
        log.debug("-> %s %s", packet.name, packet.payload)
        try:
            await self.transport.send(packet)
        except Exception:
            self._pending.pop(seq, None)
            raise
        try:
            response = await asyncio.wait_for(
                future, timeout if timeout is not None else self.request_timeout
            )
        except asyncio.TimeoutError as exc:
            self._pending.pop(seq, None)
            raise TimeoutError_(
                f"{Opcode(int(opcode)).name if int(opcode) in Opcode._value2member_map_ else opcode}: "
                "сервер не ответил"
            ) from exc
        log.debug("<- %s %s", response.name, response.payload)
        return response

    async def invoke(
        self,
        opcode: Opcode | int,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Как :meth:`request`, но возвращает payload и бросает :class:`RpcError`."""
        response = await self.request(opcode, payload, timeout=timeout)
        if response.is_error:
            raise rpc_error(response.opcode, response.payload)
        return response.payload

    async def notify(
        self, opcode: Opcode | int, payload: dict[str, Any] | None = None
    ) -> None:
        """Отправляет кадр, не дожидаясь ответа."""
        if not self.transport.is_connected:
            raise NotConnectedError("Клиент не подключён")
        packet = Packet(
            opcode=int(opcode),
            payload=payload or {},
            seq=next(self._seq) & 0xFFFF,
            cmd=0,
            ver=self.transport.rpc_version,
        )
        await self.transport.send(packet)

    # --- авторизация высокого уровня ---------------------------------------

    async def start(
        self,
        phone: str | None = None,
        *,
        code: str | int | CodeCallback | None = None,
        password: str | None = None,
    ) -> Profile:
        """Логинится: по сохранённому токену либо по SMS-коду.

        :param code: готовый код, либо функция (можно async), которая его вернёт.
            По умолчанию код спрашивается через ``input()``.
        """
        if not self.transport.is_connected:
            await self.connect()

        if self.session.token:
            try:
                payload = await self.login_by_token()
                self._absorb_login(payload)
                return self.me  # type: ignore[return-value]
            except (RpcError, SessionExpiredError) as exc:
                log.warning("Токен не подошёл (%s), нужен новый вход", exc)
                self.session.clear()

        phone = phone or self.session.phone
        if not phone:
            raise NotAuthorizedError("Нужен номер телефона для входа")

        auth = await self.request_code(phone)
        token = auth.get("token")
        if not token:
            raise NotAuthorizedError("Сервер не выдал токен для подтверждения кода")

        value = code
        if value is None:
            value = await asyncio.to_thread(
                input, f"Код из MAX для {phone} ({auth.get('codeLength', 6)} цифр): "
            )
        elif callable(value):
            result = value()
            value = await result if asyncio.iscoroutine(result) else result

        from .errors import TwoFactorRequired

        try:
            profile = await self.sign_in(str(value).strip(), token)
        except TwoFactorRequired as exc:
            if not password:
                password = await asyncio.to_thread(input, "Пароль двухфакторки: ")
            # Второй фактор идёт по треку: его id приходит в challenge.
            track_id = exc.challenge.get("trackId") or token
            profile = await self.login_check_password(password, track_id)

        self.me = profile
        await self._start_ping()
        return profile

    def _absorb_login(self, payload: dict[str, Any]) -> None:
        """Раскладывает по кешам всё, что пришло в LOGIN."""
        self.me = Profile(payload.get("profile") or {}, self)
        self.config = payload.get("config") or {}
        for raw in payload.get("contacts") or []:
            user = User(raw, self)
            if user.id is not None:
                self.contacts_cache[user.id] = user
        for raw in payload.get("chats") or []:
            chat = Chat(raw, self)
            if chat.id is not None:
                self.chats_cache[chat.id] = chat
        log.info(
            "Загружено: чатов %d, контактов %d",
            len(self.chats_cache),
            len(self.contacts_cache),
        )

    async def get_me(self, *, refresh: bool = False) -> Profile | None:
        """Текущий профиль (из кеша или через LOGIN2)."""
        if self.me is not None and not refresh:
            return self.me
        payload = await self.login2(need_profile=True)
        self.me = Profile(payload.get("profile") or {}, self)
        return self.me

    # --- события -----------------------------------------------------------

    def include_router(self, router: Router) -> Router:
        """Подключает роутер обработчиков."""
        return self.router.include_router(router)

    def on(self, event: str = "raw", *filters):
        """Декоратор регистрации обработчика прямо на клиенте."""
        return self.router.on(event, *filters)

    def on_message(self, *filters):
        return self.router.on_message(*filters)

    def on_raw(self, *filters):
        return self.router.on_raw(*filters)

    async def run_until_disconnected(self) -> None:
        """Блокируется, пока соединение живо. Ctrl+C завершает корректно."""
        loop = asyncio.get_running_loop()
        for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
            if sig is None:
                continue
            try:
                loop.add_signal_handler(sig, self._disconnected.set)
            except (NotImplementedError, RuntimeError):  # Windows
                pass
        try:
            await self._disconnected.wait()
        except asyncio.CancelledError:
            pass
        finally:
            await self.disconnect()

    idle = run_until_disconnected

    # --- цикл приёма -------------------------------------------------------

    async def _recv_loop(self) -> None:
        while True:
            try:
                packet = await self.transport.recv()
            except asyncio.CancelledError:
                return
            except TransportError as exc:
                if self._closing:
                    return
                log.warning("Приём прерван: %s", exc)
                asyncio.create_task(self._reconnect())
                return
            except Exception:
                log.exception("Неожиданная ошибка в цикле приёма")
                continue
            try:
                self._dispatch(packet)
            except Exception:
                log.exception("Ошибка обработки кадра %s", packet.name)

    def _dispatch(self, packet: Packet) -> None:
        """Раздаёт кадр: ответ на запрос, ожидание вложения или событие."""
        future = self._pending.pop(packet.seq, None)
        if future is not None and not future.done() and packet.opcode not in NOTIFICATION_OPCODES:
            future.set_result(packet)
            return

        if packet.opcode == Opcode.NOTIF_ATTACH:
            self._resolve_attach(packet.payload)

        if packet.opcode == Opcode.PING:
            return

        update = parse_update(self, packet)
        self._cache_from_update(update)
        asyncio.create_task(self.router.feed(update))

        if packet.opcode == Opcode.RECONNECT and self.auto_reconnect:
            asyncio.create_task(self._reconnect())

    def _cache_from_update(self, update: Update) -> None:
        payload = update.payload
        raw_chat = payload.get("chat")
        if isinstance(raw_chat, dict):
            chat = Chat(raw_chat, self)
            if chat.id is not None:
                self.chats_cache[chat.id] = chat
        raw_contact = payload.get("contact")
        if isinstance(raw_contact, dict):
            user = User(raw_contact, self)
            if user.id is not None:
                self.contacts_cache[user.id] = user

    # --- ожидание NOTIF_ATTACH ---------------------------------------------

    def _attach_waiter(self, key: str, value: int) -> asyncio.Future[dict[str, Any]]:
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._attach_waiters[(key, value)] = future
        return future

    def _resolve_attach(self, payload: dict[str, Any]) -> None:
        for key in ("videoId", "fileId", "photoId", "audioId"):
            value = payload.get(key)
            if value is None:
                continue
            future = self._attach_waiters.pop((key, int(value)), None)
            if future is not None and not future.done():
                future.set_result(payload)

    async def _await_attach(
        self, future: asyncio.Future[dict[str, Any]], timeout: float
    ) -> dict[str, Any]:
        try:
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError as exc:
            raise TimeoutError_("Сервер не подтвердил обработку файла") from exc

    # --- keepalive ---------------------------------------------------------

    async def _start_ping(self) -> None:
        if self._ping_task is None and self.ping_interval > 0:
            self._ping_task = asyncio.create_task(self._ping_loop(), name="maxion-ping")

    async def _stop_ping(self) -> None:
        task, self._ping_task = self._ping_task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    async def _ping_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.ping_interval)
                await self.ping()
            except asyncio.CancelledError:
                return
            except (TimeoutError_, TransportError) as exc:
                log.warning("Пинг не прошёл: %s", exc)
                if self.auto_reconnect and not self._closing:
                    asyncio.create_task(self._reconnect())
                return
            except Exception:
                log.exception("Ошибка в цикле пинга")

    # --- переподключение ---------------------------------------------------

    async def _reconnect(self) -> None:
        if self._closing or not self.auto_reconnect:
            self._disconnected.set()
            return
        await self._stop_ping()
        await self.transport.close()
        for future in self._pending.values():
            if not future.done():
                future.set_exception(TransportError("Переподключение"))
        self._pending.clear()

        for attempt, delay in enumerate(
            itertools.chain(RECONNECT_DELAYS, itertools.repeat(RECONNECT_DELAYS[-1])),
            start=1,
        ):
            if self._closing:
                return
            log.info("Переподключение через %.0f с (попытка %d)", delay, attempt)
            await asyncio.sleep(delay)
            try:
                self.transport = self._transport_factory()
                await self.connect()
                if self.session.token:
                    payload = await self.login_by_token()
                    self._absorb_login(payload)
                    await self._start_ping()
                log.info("Переподключились")
                return
            except Exception as exc:
                log.warning("Не удалось переподключиться: %s", exc)
                await self.transport.close()

    # --- http --------------------------------------------------------------

    async def _http(self):
        """Ленивая aiohttp-сессия для загрузки файлов."""
        if self._http_session is None:
            try:
                import aiohttp
            except ImportError as exc:  # pragma: no cover
                raise MaxError("Для загрузки файлов нужен aiohttp") from exc
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    def __repr__(self) -> str:
        state = "подключён" if self.is_connected else "отключён"
        return f"<MaxClient {state} user_id={self.user_id}>"
