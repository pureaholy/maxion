"""Вспомогательные функции: cid, телефоны, разметка текста."""

from __future__ import annotations

import itertools
import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Sequence

from .enums import ElementType

_cid_counter = itertools.count()


def next_cid() -> int:
    """Клиентский идентификатор сообщения (миллисекунды + счётчик).

    MAX использует его для дедупликации отправок, поэтому значение должно
    расти монотонно в пределах сессии.
    """
    return int(time.time() * 1000) * 100 + (next(_cid_counter) % 100)


def now_ms() -> int:
    return int(time.time() * 1000)


def normalize_phone(phone: str) -> str:
    """Приводит номер к формату +7XXXXXXXXXX."""
    digits = re.sub(r"\D", "", phone)
    if not digits:
        raise ValueError("Пустой номер телефона")
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    return "+" + digits


def chunks(seq: Sequence[Any], size: int) -> Iterator[Sequence[Any]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def clean(payload: dict[str, Any]) -> dict[str, Any]:
    """Убирает ключи со значением None -- сервер не любит пустые поля."""
    return {k: v for k, v in payload.items() if v is not None}


# --- разметка --------------------------------------------------------------


@dataclass(slots=True)
class Element:
    """Участок форматирования в тексте сообщения."""

    type: ElementType | str
    from_: int
    length: int
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "type": str(self.type),
            "from": self.from_,
            "length": self.length,
        }
        data.update(self.extra)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Element":
        extra = {k: v for k, v in data.items() if k not in ("type", "from", "length")}
        return cls(
            type=data.get("type", ""),
            from_=int(data.get("from", 0)),
            length=int(data.get("length", 0)),
            extra=extra,
        )


class Text:
    """Сборщик форматированного текста.

    Пример::

        t = Text("Привет, ").bold("мир").text("! ").link("док", "https://max.ru")
        await client.send_message(chat_id, t)
    """

    def __init__(self, text: str = ""):
        self._parts: list[str] = []
        self._elements: list[Element] = []
        self._len = 0
        if text:
            self.text(text)

    # --- служебное ---------------------------------------------------------

    def _append(
        self, value: str, kind: ElementType | None = None, **extra: Any
    ) -> "Text":
        if value:
            if kind is not None:
                self._elements.append(Element(kind, self._len, len(value), extra))
            self._parts.append(value)
            self._len += len(value)
        return self

    # --- API ---------------------------------------------------------------

    def text(self, value: str) -> "Text":
        return self._append(value)

    def bold(self, value: str) -> "Text":
        return self._append(value, ElementType.STRONG)

    def italic(self, value: str) -> "Text":
        return self._append(value, ElementType.EMPHASIZED)

    def underline(self, value: str) -> "Text":
        return self._append(value, ElementType.UNDERLINE)

    def strike(self, value: str) -> "Text":
        return self._append(value, ElementType.STRIKETHROUGH)

    def code(self, value: str) -> "Text":
        return self._append(value, ElementType.MONOSPACED)

    def code_block(self, value: str, language: str | None = None) -> "Text":
        extra = {"language": language} if language else {}
        return self._append(value, ElementType.CODE_BLOCK, **extra)

    def quote(self, value: str) -> "Text":
        return self._append(value, ElementType.QUOTE)

    def heading(self, value: str) -> "Text":
        return self._append(value, ElementType.HEADING)

    def link(self, value: str, url: str) -> "Text":
        return self._append(value, ElementType.LINK, url=url)

    def mention(self, value: str, user_id: int) -> "Text":
        return self._append(value, ElementType.USER_MENTION, userId=int(user_id))

    def newline(self, count: int = 1) -> "Text":
        return self._append("\n" * count)

    # --- результат ---------------------------------------------------------

    @property
    def value(self) -> str:
        return "".join(self._parts)

    @property
    def elements(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self._elements]

    def __str__(self) -> str:
        return self.value

    def __add__(self, other: "Text | str") -> "Text":
        if isinstance(other, str):
            return self.text(other)
        offset = self._len
        self._parts.append(other.value)
        self._len += len(other.value)
        for element in other._elements:
            self._elements.append(
                Element(
                    element.type,
                    element.from_ + offset,
                    element.length,
                    dict(element.extra),
                )
            )
        return self


_MD_PATTERNS: tuple[tuple[str, ElementType], ...] = (
    (r"```(?:(\w+)\n)?(.+?)```", ElementType.CODE_BLOCK),
    (r"\*\*(.+?)\*\*", ElementType.STRONG),
    (r"__(.+?)__", ElementType.UNDERLINE),
    (r"~~(.+?)~~", ElementType.STRIKETHROUGH),
    (r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", ElementType.EMPHASIZED),
    (r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", ElementType.EMPHASIZED),
    (r"`([^`]+?)`", ElementType.MONOSPACED),
)

_MD_LINK = re.compile(r"\[(.+?)\]\((\S+?)\)", re.S)


def parse_markdown(source: str) -> tuple[str, list[dict[str, Any]]]:
    """Разбирает markdown-подмножество и возвращает (text, elements).

    Поддерживается жирный, курсив, подчёркнутый, зачёркнутый, моноширинный,
    блок кода и ссылка вида [текст](url).
    """
    elements: list[Element] = []
    text = source

    def _shift(pos: int, delta: int) -> None:
        for element in elements:
            if element.from_ > pos:
                element.from_ += delta

    while True:
        match = _MD_LINK.search(text)
        if not match:
            break
        label, url = match.group(1), match.group(2)
        start = match.start()
        text = text[:start] + label + text[match.end() :]
        _shift(start, len(label) - (match.end() - start))
        elements.append(Element(ElementType.LINK, start, len(label), {"url": url}))

    for pattern, kind in _MD_PATTERNS:
        regex = re.compile(pattern, re.S)
        while True:
            match = regex.search(text)
            if not match:
                break
            groups = list(match.groups())
            body = groups[-1] or ""
            language = groups[0] if kind is ElementType.CODE_BLOCK else None
            start = match.start()
            text = text[:start] + body + text[match.end() :]
            _shift(start, len(body) - (match.end() - start))
            extra = {"language": language} if language else {}
            elements.append(Element(kind, start, len(body), extra))

    elements.sort(key=lambda e: (e.from_, e.length))
    return text, [e.to_dict() for e in elements]


def elements_from(raw: Iterable[dict[str, Any]] | None) -> list[Element]:
    return [Element.from_dict(item) for item in (raw or [])]
