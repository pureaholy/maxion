"""Авторизация, сессии, двухфакторка."""

from __future__ import annotations

import logging
from typing import Any

from ..const import DEFAULT_USER_AGENT_OBJECT
from ..enums import AuthTokenType, AuthType, LoginTokenType
from ..errors import AuthError, RpcError, SessionExpiredError, TwoFactorRequired
from ..opcodes import Opcode
from ..types import DeviceSession, Profile
from ..utils import clean, normalize_phone
from .base import MethodsBase

log = logging.getLogger(__name__)


class AuthMethods(MethodsBase):
    """Опкоды 6, 8, 16-23, 96-116, 290."""

    # --- инициализация сессии ---------------------------------------------

    async def session_init(
        self,
        *,
        user_agent: dict[str, Any] | None = None,
        device_id: str | None = None,
        client_session_id: int | None = None,
        instance_id: str | None = None,
    ) -> dict[str, Any]:
        """SESSION_INIT (6). Первый пакет любого соединения."""
        agent = dict(DEFAULT_USER_AGENT_OBJECT)
        agent.update(user_agent or {})
        payload = clean(
            {
                "userAgent": agent,
                "deviceId": device_id or self.session.device_id,
                "clientSessionId": client_session_id,
                "mt_instanceid": instance_id,
            }
        )
        return await self.invoke(Opcode.SESSION_INIT, payload)

    async def login2(
        self,
        *,
        config_hash: str | None = None,
        contacts_sync: int = 0,
        need_profile: bool = True,
    ) -> dict[str, Any]:
        """LOGIN2 (8). Догрузка конфигурации и профиля."""
        return await self.invoke(
            Opcode.LOGIN2,
            clean(
                {
                    "configHash": config_hash,
                    "contactsSync": contacts_sync,
                    "needProfile": need_profile,
                }
            ),
        )

    # --- вход по номеру ----------------------------------------------------

    async def request_code(
        self,
        phone: str,
        *,
        language: str | None = "ru",
        auth_type: AuthType | str = AuthType.START_AUTH,
        mode: list[str] | str | None = None,
    ) -> dict[str, Any]:
        """AUTH_REQUEST (17). Запрашивает код подтверждения.

        :returns: payload с ``token`` (его нужно передать в :meth:`sign_in`),
            ``codeLength``, ``requestCountLeft``, ``requestMaxDuration``.
        """
        phone = normalize_phone(phone)
        device = getattr(self, "device", None)
        if device is not None and not device.supports_phone_auth:
            log.warning(
                "Профиль %s -- браузерный, а в web-версии MAX вход по номеру "
                "телефона вырезан. Если сервер откажет, используйте "
                'MaxClient(..., device="android").',
                device.device_type,
            )
        try:
            payload = await self.invoke(
                Opcode.AUTH_REQUEST,
                clean(
                    {
                        "phone": phone,
                        "type": str(auth_type),
                        "mode": mode,
                        "language": language,
                    }
                ),
            )
        except RpcError as exc:
            if device is not None and not device.supports_phone_auth:
                raise AuthError(
                    f"{exc}. Вход по номеру телефона недоступен для профиля "
                    f"{device.device_type}: создайте клиент как "
                    'MaxClient(..., device="android") -- или '
                    'MaxClient(..., transport="tcp"), где профиль телефона '
                    "подставляется сам."
                ) from exc
            raise
        self.session.phone = phone
        return payload

    async def resend_code(self, phone: str, *, language: str = "ru") -> dict[str, Any]:
        """AUTH_REQUEST (17) с типом RESEND_CODE."""
        return await self.request_code(
            phone, language=language, auth_type=AuthType.RESEND_CODE
        )

    async def sign_in(
        self,
        code: str | int,
        token: str,
        *,
        token_type: AuthTokenType | str = AuthTokenType.CHECK_CODE,
    ) -> Profile:
        """AUTH (18). Подтверждает код и получает токен логина."""
        payload = await self.invoke(
            Opcode.AUTH,
            {
                "token": token,
                "verifyCode": str(code),
                "authTokenType": str(token_type),
            },
        )
        challenge = payload.get("passwordChallenge")
        if challenge:
            raise TwoFactorRequired(challenge)
        login_token = _extract_login_token(payload)
        if not login_token:
            raise AuthError("Сервер не вернул токен логина")
        profile = Profile(payload.get("profile") or {}, self)  # type: ignore[arg-type]
        self._store_login(login_token, profile)
        return profile

    async def login_by_token(
        self,
        token: str | None = None,
        *,
        interactive: bool = True,
        chats_sync: int = 0,
        contacts_sync: int = 0,
        presence_sync: int = -1,
        drafts_sync: int = 0,
        calls_sync: int = 0,
        banners_sync: int = 0,
        config_hash: str | None = None,
        last_login: int | None = None,
        chats_count: int | None = None,
        chat_cache_fingerprint: Any = None,
        chats_count_groups: Any = None,
        exp: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """LOGIN (19). Вход по сохранённому токену.

        Возвращает полный payload: профиль, чаты, контакты, конфиг.
        """
        token = token or self.session.token
        if not token:
            raise SessionExpiredError("Нет сохранённого токена")
        payload = await self.invoke(
            Opcode.LOGIN,
            clean(
                {
                    "interactive": interactive,
                    "token": token,
                    "chatsSync": chats_sync,
                    "contactsSync": contacts_sync,
                    "presenceSync": presence_sync,
                    "draftsSync": drafts_sync,
                    "callsSync": calls_sync,
                    "bannersSync": banners_sync,
                    "configHash": config_hash,
                    "lastLogin": last_login,
                    "chatsCount": chats_count,
                    "chatCacheFingerprint": chat_cache_fingerprint,
                    "chatsCountGroups": chats_count_groups,
                    "exp": exp,
                }
            ),
        )
        profile = Profile(payload.get("profile") or {}, self)  # type: ignore[arg-type]
        self._store_login(payload.get("token") or token, profile)
        return payload

    async def auth_confirm(
        self,
        token: str,
        *,
        token_type: LoginTokenType | str = LoginTokenType.REGISTRATION,
        first_name: str | None = None,
        last_name: str | None = None,
        photo_id: int | None = None,
        avatar_type: str | None = None,
    ) -> dict[str, Any]:
        """AUTH_CONFIRM (23). Завершает регистрацию нового аккаунта."""
        return await self.invoke(
            Opcode.AUTH_CONFIRM,
            clean(
                {
                    "token": token,
                    "tokenType": str(token_type),
                    "firstName": first_name,
                    "lastName": last_name,
                    "photoId": photo_id,
                    "avatarType": avatar_type,
                }
            ),
        )

    async def logout(self, push_token: str | None = None) -> dict[str, Any]:
        """LOGOUT (20). Завершает сессию на сервере и чистит локальную."""
        payload = await self.invoke(Opcode.LOGOUT, clean({"pushToken": push_token}))
        self.session.clear()
        return payload

    # --- двухфакторная аутентификация -------------------------------------

    async def get_2fa_details(self, track_id: str | None = None) -> dict[str, Any]:
        """AUTH_2FA_DETAILS (104). Что настроено во втором факторе."""
        return await self.invoke(
            Opcode.AUTH_2FA_DETAILS, clean({"trackId": track_id})
        )

    async def create_auth_track(
        self, type_: str | None = None, **payload: Any
    ) -> dict[str, Any]:
        """AUTH_CREATE_TRACK (112). Начинает трек 2FA и выдаёт ``trackId``."""
        return await self.invoke(
            Opcode.AUTH_CREATE_TRACK, clean({"type": type_, **payload})
        )

    async def check_password(
        self, password: str, track_id: str | None = None
    ) -> dict[str, Any]:
        """AUTH_CHECK_PASSWORD (113). Шаг трека 2FA."""
        return await self.invoke(
            Opcode.AUTH_CHECK_PASSWORD,
            clean({"password": password, "trackId": track_id}),
        )

    async def login_check_password(
        self, password: str, track_id: str | None = None
    ) -> Profile:
        """AUTH_LOGIN_CHECK_PASSWORD (115). Второй фактор при входе."""
        payload = await self.invoke(
            Opcode.AUTH_LOGIN_CHECK_PASSWORD,
            clean({"password": password, "trackId": track_id}),
        )
        login_token = _extract_login_token(payload)
        profile = Profile(payload.get("profile") or {}, self)  # type: ignore[arg-type]
        if login_token:
            self._store_login(login_token, profile)
        return profile

    async def validate_password(
        self, password: str, track_id: str | None = None
    ) -> dict[str, Any]:
        """AUTH_VALIDATE_PASSWORD (107)."""
        return await self.invoke(
            Opcode.AUTH_VALIDATE_PASSWORD,
            clean({"password": password, "trackId": track_id}),
        )

    async def validate_hint(
        self, hint: str, track_id: str | None = None
    ) -> dict[str, Any]:
        """AUTH_VALIDATE_HINT (108)."""
        return await self.invoke(
            Opcode.AUTH_VALIDATE_HINT, clean({"hint": hint, "trackId": track_id})
        )

    async def set_2fa(
        self,
        password: str | None = None,
        *,
        hint: str | None = None,
        track_id: str | None = None,
        remove: bool | None = None,
        expected_capabilities: list[str] | None = None,
    ) -> dict[str, Any]:
        """AUTH_SET_2FA (111). ``remove=True`` снимает пароль."""
        return await self.invoke(
            Opcode.AUTH_SET_2FA,
            clean(
                {
                    "password": password,
                    "hint": hint,
                    "trackId": track_id,
                    "remove2fa": remove,
                    "expectedCapabilities": expected_capabilities,
                }
            ),
        )

    async def check_email(
        self, code: str, track_id: str | None = None
    ) -> dict[str, Any]:
        """AUTH_CHECK_EMAIL (110). Подтверждает код, присланный на почту."""
        return await self.invoke(
            Opcode.AUTH_CHECK_EMAIL,
            clean({"verifyCode": str(code), "trackId": track_id}),
        )

    async def verify_email(
        self, email: str, track_id: str | None = None
    ) -> dict[str, Any]:
        """AUTH_VERIFY_EMAIL (109). Запрашивает код на почту."""
        return await self.invoke(
            Opcode.AUTH_VERIFY_EMAIL, clean({"email": email, "trackId": track_id})
        )

    async def restore_password(
        self,
        *,
        password: str | None = None,
        hint: str | None = None,
        track_id: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """AUTH_LOGIN_RESTORE_PASSWORD (101). Сброс пароля 2FA по треку."""
        return await self.invoke(
            Opcode.AUTH_LOGIN_RESTORE_PASSWORD,
            clean(
                {"password": password, "hint": hint, "trackId": track_id, **extra}
            ),
        )

    async def delete_profile_by_login(
        self, track_id: str | None = None, *, delete: bool = True
    ) -> dict[str, Any]:
        """AUTH_LOGIN_PROFILE_DELETE (116)."""
        return await self.invoke(
            Opcode.AUTH_LOGIN_PROFILE_DELETE,
            clean({"trackId": track_id, "delete": delete}),
        )

    async def approve_qr(self, qr_link: str) -> dict[str, Any]:
        """AUTH_QR_APPROVE (290). Подтверждает вход по QR с другого устройства.

        На проводе передаётся сама ссылка из QR-кода — поле ``qrLink``.
        """
        return await self.invoke(Opcode.AUTH_QR_APPROVE, {"qrLink": qr_link})

    # --- привязка телефона -------------------------------------------------

    async def bind_phone_request(self, phone: str) -> dict[str, Any]:
        """PHONE_BIND_REQUEST (98)."""
        return await self.invoke(
            Opcode.PHONE_BIND_REQUEST, {"phone": normalize_phone(phone)}
        )

    async def bind_phone_confirm(self, token: str, code: str | int) -> dict[str, Any]:
        """PHONE_BIND_CONFIRM (99)."""
        return await self.invoke(
            Opcode.PHONE_BIND_CONFIRM, {"token": token, "verifyCode": str(code)}
        )

    async def share_phone_to_webapp(
        self,
        bot_id: int,
        *,
        chat_id: int | None = None,
        status: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """PHONE_WEBAPP_SHARE (106). Отдаёт номер мини-приложению бота."""
        return await self.invoke(
            Opcode.PHONE_WEBAPP_SHARE,
            clean(
                {"botId": bot_id, "webappChatId": chat_id, "status": status, **extra}
            ),
        )

    # --- активные сессии ---------------------------------------------------

    async def get_sessions(self) -> list[DeviceSession]:
        """SESSIONS_INFO (96). Список устройств, где выполнен вход."""
        payload = await self.invoke(Opcode.SESSIONS_INFO, {})
        raw = payload.get("sessions") or payload.get("info") or []
        return DeviceSession.parse_list(raw, self)  # type: ignore[arg-type]

    async def close_sessions(
        self, session_ids: list[int] | int | None = None, *, all_others: bool = False
    ) -> dict[str, Any]:
        """SESSIONS_CLOSE (97). Завершает чужие сессии."""
        if isinstance(session_ids, int):
            session_ids = [session_ids]
        return await self.invoke(
            Opcode.SESSIONS_CLOSE,
            clean({"ids": session_ids, "all": all_others or None}),
        )

    # --- удаление профиля --------------------------------------------------

    async def delete_profile(
        self, *, delete: bool = True, type_: str | None = None
    ) -> dict[str, Any]:
        """PROFILE_DELETE (199). Необратимо удаляет аккаунт."""
        return await self.invoke(
            Opcode.PROFILE_DELETE, clean({"delete": delete, "type": type_})
        )

    async def get_profile_delete_time(self) -> dict[str, Any]:
        """PROFILE_DELETE_TIME (200)."""
        return await self.invoke(Opcode.PROFILE_DELETE_TIME, {})

    # --- служебное ---------------------------------------------------------

    def _store_login(self, token: str, profile: Profile) -> None:
        self.session.token = token
        if profile.id:
            self.session.user_id = profile.id
        if profile.phone:
            self.session.phone = profile.phone
        if profile.name:
            self.session.name = profile.name
        self.session.save()
        log.info("Авторизован как %s (id=%s)", profile.name, profile.id)


def _extract_login_token(payload: dict[str, Any]) -> str | None:
    """Достаёт токен логина из ``tokenAttrs.LOGIN.token``."""
    attrs = payload.get("tokenAttrs")
    if isinstance(attrs, dict):
        login = attrs.get("LOGIN")
        if isinstance(login, dict) and login.get("token"):
            return str(login["token"])
    return payload.get("token")
