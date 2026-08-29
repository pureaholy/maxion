"""Разбор разметки текста: markdown и HTML.

Возвращает пару ``(текст, elements)`` — второе уходит в поле ``elements``
протокола MAX.
"""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any

from .enums import MessageEntityType, ParseMode
from .raw.utils import parse_markdown

#: HTML-тег -> тип элемента протокола.
HTML_TAGS = {
    "b": MessageEntityType.BOLD,
    "strong": MessageEntityType.BOLD,
    "i": MessageEntityType.ITALIC,
    "em": MessageEntityType.ITALIC,
    "u": MessageEntityType.UNDERLINE,
    "ins": MessageEntityType.UNDERLINE,
    "s": MessageEntityType.STRIKETHROUGH,
    "strike": MessageEntityType.STRIKETHROUGH,
    "del": MessageEntityType.STRIKETHROUGH,
    "code": MessageEntityType.CODE,
    "pre": MessageEntityType.PRE,
    "blockquote": MessageEntityType.BLOCKQUOTE,
    "a": MessageEntityType.TEXT_LINK,
}


class _HtmlParser(HTMLParser):
    """Собирает чистый текст и список элементов форматирования."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text: list[str] = []
        self.length = 0
        self.elements: list[dict[str, Any]] = []
        self._open: list[tuple[str, int, dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in HTML_TAGS:
            self._open.append((tag, self.length, {k: v or "" for k, v in attrs}))

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._open) - 1, -1, -1):
            name, start, attrs = self._open[index]
            if name != tag:
                continue
            del self._open[index]
            length = self.length - start
            if length <= 0:
                return
            element: dict[str, Any] = {
                "type": HTML_TAGS[tag].raw,
                "from": start,
                "length": length,
            }
            if tag == "a" and attrs.get("href"):
                element["url"] = attrs["href"]
            self.elements.append(element)
            return

    def handle_data(self, data: str) -> None:
        self.text.append(data)
        self.length += len(data)

    def result(self) -> tuple[str, list[dict[str, Any]]]:
        self.close()
        self.elements.sort(key=lambda e: (e["from"], e["length"]))
        return "".join(self.text), self.elements


def parse_html(source: str) -> tuple[str, list[dict[str, Any]]]:
    """``<b>жирный</b>`` и прочие теги -> текст и elements."""
    parser = _HtmlParser()
    parser.feed(source)
    return parser.result()


def parse(
    text: str, parse_mode: ParseMode | str | None = None
) -> tuple[str, list[dict[str, Any]]]:
    """Разбирает текст согласно режиму.

    ``None`` и :attr:`ParseMode.DEFAULT` означают markdown.
    :attr:`ParseMode.DISABLED` оставляет текст как есть.
    """
    if parse_mode is None:
        parse_mode = ParseMode.DEFAULT
    if isinstance(parse_mode, str):
        parse_mode = ParseMode(parse_mode.lower())

    if parse_mode is ParseMode.DISABLED:
        return text, []
    if parse_mode is ParseMode.HTML:
        return parse_html(text)
    return parse_markdown(text)


__all__ = ["parse", "parse_html", "HTML_TAGS"]
