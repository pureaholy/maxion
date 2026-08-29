"""Контакты и присутствие."""

from __future__ import annotations

from typing import Any

from ..enums import ContactUpdateAction, StatusType
from ..opcodes import Opcode
from ..types import Presence, User
from ..utils import clean, normalize_phone
from .base import MethodsBase


class ContactMethods(MethodsBase):
    """Опкоды 32-46."""

    async def get_contacts(self, user_ids: list[int] | int, chat_id: int | None = None) -> list[User]:
        """CONTACT_INFO (32). Информация о пользователях по id."""
        if isinstance(user_ids, int):
            user_ids = [user_ids]
        payload = await self.invoke(
            Opcode.CONTACT_INFO,
            clean({"contactIds": list(user_ids), "chat_id": chat_id}),
        )
        users = User.parse_list(payload.get("contacts"), self)  # type: ignore[arg-type]
        self._cache_contacts(users)
        return users

    async def get_contact(self, user_id: int) -> User | None:
        """Одиночная обёртка над CONTACT_INFO."""
        contacts = await self.get_contacts([user_id])
        return contacts[0] if contacts else None

    async def get_contact_by_phone(self, phone: str) -> User | None:
        """CONTACT_INFO_BY_PHONE (46)."""
        payload = await self.invoke(
            Opcode.CONTACT_INFO_BY_PHONE, {"phone": normalize_phone(phone)}
        )
        raw = payload.get("contact")
        if not raw:
            contacts = payload.get("contacts") or []
            raw = contacts[0] if contacts else None
        user = User.parse(raw, self)  # type: ignore[arg-type]
        if user:
            self._cache_contacts([user])
        return user

    async def add_contact(self, user_id: int, **payload: Any) -> dict[str, Any]:
        """CONTACT_ADD (33)."""
        return await self.invoke(
            Opcode.CONTACT_ADD, clean({"contactId": user_id, **payload})
        )

    async def update_contact(
        self,
        user_id: int,
        action: ContactUpdateAction | str,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> User | None:
        """CONTACT_UPDATE (34). Добавить, удалить, заблокировать, переименовать."""
        payload = await self.invoke(
            Opcode.CONTACT_UPDATE,
            clean(
                {
                    "contactId": user_id,
                    "action": str(action),
                    "firstName": first_name,
                    "lastName": last_name,
                }
            ),
        )
        return User.parse(payload.get("contact"), self)  # type: ignore[arg-type]

    async def save_contact(self, user_id: int) -> User | None:
        """CONTACT_UPDATE с action=ADD."""
        return await self.update_contact(user_id, ContactUpdateAction.ADD)

    async def remove_contact(self, user_id: int) -> User | None:
        """CONTACT_UPDATE с action=REMOVE."""
        return await self.update_contact(user_id, ContactUpdateAction.REMOVE)

    async def block_user(self, user_id: int) -> User | None:
        """CONTACT_UPDATE с action=BLOCK."""
        return await self.update_contact(user_id, ContactUpdateAction.BLOCK)

    async def unblock_user(self, user_id: int) -> User | None:
        """CONTACT_UPDATE с action=UNBLOCK."""
        return await self.update_contact(user_id, ContactUpdateAction.UNBLOCK)

    async def rename_contact(
        self, user_id: int, first_name: str, last_name: str | None = None
    ) -> User | None:
        """CONTACT_UPDATE с action=RENAME."""
        return await self.update_contact(
            user_id,
            ContactUpdateAction.RENAME,
            first_name=first_name,
            last_name=last_name,
        )

    async def get_presence(self, user_ids: list[int] | int) -> dict[int, Presence]:
        """CONTACT_PRESENCE (35). Онлайн-статусы."""
        if isinstance(user_ids, int):
            user_ids = [user_ids]
        payload = await self.invoke(Opcode.CONTACT_PRESENCE, {"contactIds": list(user_ids)})
        raw = payload.get("presence") or {}
        return {int(k): Presence(v, self) for k, v in raw.items()}  # type: ignore[arg-type]

    async def get_contact_list(
        self,
        *,
        status: StatusType | str = StatusType.ACTIVE,
        offset: int = 0,
        count: int = 200,
    ) -> list[User]:
        """CONTACT_LIST (36). Список сохранённых контактов."""
        payload = await self.invoke(
            Opcode.CONTACT_LIST,
            {"status": str(status), "from": offset, "count": count},
        )
        users = User.parse_list(payload.get("contacts"), self)  # type: ignore[arg-type]
        self._cache_contacts(users)
        return users

    async def iter_contacts(self, *, chunk: int = 200, status: StatusType | str = StatusType.ACTIVE):
        """Постранично обходит весь список контактов."""
        offset = 0
        while True:
            batch = await self.get_contact_list(status=status, offset=offset, count=chunk)
            if not batch:
                return
            for user in batch:
                yield user
            if len(batch) < chunk:
                return
            offset += len(batch)

    async def search_contacts(self, query: str, *, count: int = 30) -> list[User]:
        """CONTACT_SEARCH (37)."""
        payload = await self.invoke(
            Opcode.CONTACT_SEARCH, {"query": query, "count": count}
        )
        return User.parse_list(payload.get("contacts"), self)  # type: ignore[arg-type]

    async def get_mutual_contacts(self, user_id: int, *, count: int = 30) -> list[User]:
        """CONTACT_MUTUAL (38). Общие контакты."""
        payload = await self.invoke(
            Opcode.CONTACT_MUTUAL, {"contactId": user_id, "count": count}
        )
        return User.parse_list(payload.get("contacts"), self)  # type: ignore[arg-type]

    async def sort_contacts(self, contact_ids: list[int]) -> dict[str, Any]:
        """CONTACT_SORT (40). Задаёт пользовательский порядок контактов."""
        return await self.invoke(Opcode.CONTACT_SORT, {"contactIds": contact_ids})

    async def verify_contact(self, user_id: int, **payload: Any) -> dict[str, Any]:
        """CONTACT_VERIFY (42)."""
        return await self.invoke(
            Opcode.CONTACT_VERIFY, clean({"contactId": user_id, **payload})
        )

    # --- служебное ---------------------------------------------------------

    def _cache_contacts(self, users: list[User]) -> None:
        cache = getattr(self, "contacts_cache", None)
        if cache is None:
            return
        for user in users:
            if user.id is not None:
                cache[user.id] = user
