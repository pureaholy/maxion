"""Базовая модель: типизированная обёртка над сырым payload.

Сервер MAX регулярно добавляет поля, поэтому модели ничего не выбрасывают:
исходный словарь всегда доступен в :attr:`Model.raw`, а неизвестные ключи
читаются через ``model["ключ"]`` или ``model.get("ключ")``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterator, Mapping, Sequence, TypeVar

if TYPE_CHECKING:  # pragma: no cover
    from ..client import MaxClient

T = TypeVar("T", bound="Model")


class Model:
    """Обёртка над словарём ответа."""

    __slots__ = ("raw", "_client")

    def __init__(self, raw: Mapping[str, Any] | None = None, client: "MaxClient | None" = None):
        self.raw: dict[str, Any] = dict(raw or {})
        self._client = client

    # --- доступ к сырым данным --------------------------------------------

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def __contains__(self, key: object) -> bool:
        return key in self.raw

    def __iter__(self) -> Iterator[str]:
        return iter(self.raw)

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.raw)

    # --- конструирование ---------------------------------------------------

    @classmethod
    def parse(
        cls: type[T], raw: Mapping[str, Any] | None, client: "MaxClient | None" = None
    ) -> T | None:
        if raw is None:
            return None
        return cls(raw, client)

    @classmethod
    def parse_list(
        cls: type[T],
        raw: Sequence[Mapping[str, Any]] | None,
        client: "MaxClient | None" = None,
    ) -> list[T]:
        return [cls(item, client) for item in (raw or []) if isinstance(item, Mapping)]

    # --- служебное ---------------------------------------------------------

    @property
    def client(self) -> "MaxClient":
        if self._client is None:
            raise RuntimeError("Модель не привязана к клиенту")
        return self._client

    def _int(self, *keys: str) -> int | None:
        for key in keys:
            value = self.raw.get(key)
            if value is not None:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return None
        return None

    def _str(self, *keys: str) -> str | None:
        for key in keys:
            value = self.raw.get(key)
            if value is not None:
                return str(value)
        return None

    def __repr__(self) -> str:
        name = type(self).__name__
        ident = self.raw.get("id") or self.raw.get("chatId") or self.raw.get("userId")
        preview = f" id={ident}" if ident is not None else ""
        return f"<{name}{preview} {len(self.raw)} полей>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Model) and type(other) is type(self) and other.raw == self.raw

    def __hash__(self) -> int:
        ident = self.raw.get("id")
        return hash((type(self).__name__, ident)) if ident is not None else id(self)
