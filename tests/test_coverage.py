"""Гарантия полноты: каждый вызываемый опкод обёрнут методом.

Если после перегенерации ``maxion/raw/opcodes.py`` из свежего APK появился новый
опкод — этот тест упадёт и назовёт его. Так покрытие не разъезжается молча.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

from maxion.raw.client import MaxClient
from maxion.raw.opcodes import NOTIFICATION_OPCODES, Opcode

METHODS_DIR = Path(__file__).resolve().parent.parent / "maxion" / "raw" / "methods"

#: Опкоды, которые сервер шлёт сам — вызывать их клиенту незачем.
SERVER_INITIATED = {op.name for op in NOTIFICATION_OPCODES}


def covered_opcodes() -> dict[str, str]:
    """``{имя опкода: файл, где обёрнут}``."""
    covered: dict[str, str] = {}
    for path in sorted(METHODS_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for name in re.findall(r"Opcode\.([A-Z][A-Z0-9_]*)", text):
            covered.setdefault(name, path.name)
    return covered


def test_every_callable_opcode_has_a_wrapper():
    covered = covered_opcodes()
    missing = sorted(
        op.name
        for op in Opcode
        if op.name not in SERVER_INITIATED and op.name not in covered
    )
    assert not missing, "не обёрнуты опкоды: " + ", ".join(missing)


def test_all_stories_opcodes_are_wrapped():
    covered = covered_opcodes()
    stories = [
        op for op in Opcode if op.name.startswith("STORIES_")
    ]
    assert len(stories) == 11
    missing = [op.name for op in stories if op.name not in covered]
    assert not missing, "истории без обёртки: " + ", ".join(missing)
    assert all(covered[op.name] == "stories.py" for op in stories)


def test_notification_opcodes_have_event_classes():
    from maxion.raw.events import UPDATE_CLASSES

    uncovered = sorted(
        op.name
        for op in Opcode
        if op.name.startswith("NOTIF_") and int(op) not in UPDATE_CLASSES
    )
    assert not uncovered, "нет класса события для: " + ", ".join(uncovered)


def test_no_duplicate_method_names_across_mixins():
    """Миксины не должны молча перекрывать методы друг друга."""
    seen: dict[str, str] = {}
    clashes: list[str] = []
    for path in sorted(METHODS_DIR.glob("*.py")):
        if path.name in ("__init__.py", "base.py"):
            continue
        for name in re.findall(r"^    async def (\w+)\(", path.read_text(encoding="utf-8"), re.M):
            if name in seen:
                clashes.append(f"{name}: {seen[name]} и {path.name}")
            seen[name] = path.name
    assert not clashes, "конфликт имён методов: " + "; ".join(clashes)


def test_client_exposes_every_wrapper():
    """Все методы миксинов действительно доступны на клиенте."""
    public = {
        name
        for name, _ in inspect.getmembers(MaxClient, inspect.isfunction)
        if not name.startswith("_")
    }
    for path in sorted(METHODS_DIR.glob("*.py")):
        if path.name in ("__init__.py", "base.py"):
            continue
        for name in re.findall(
            r"^    async def ([a-z]\w*)\(", path.read_text(encoding="utf-8"), re.M
        ):
            assert name in public, f"{name} из {path.name} не виден на MaxClient"


EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def test_examples_call_only_existing_client_methods():
    """Примеры не должны ссылаться на несуществующие методы клиента."""
    # dir() по экземпляру, чтобы попали и атрибуты из __init__ (me, session, …).
    # Примеры бывают и низкоуровневые, и высокоуровневые — знаем оба клиента.
    from maxion import Client as HighLevelClient

    public = set(dir(MaxClient())) | set(dir(HighLevelClient(workdir=".")))
    problems: list[str] = []
    for path in sorted(EXAMPLES_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for name in set(re.findall(r"\bclient\.(\w+)", text)):
            if name not in public:
                problems.append(f"{path.name}: client.{name}")
    assert not problems, "нет таких методов: " + ", ".join(sorted(problems))


#: Опкоды, у обёрток которых схема запроса неизвестна: параметры принимаются
#: как ``**payload``. Список закреплён намеренно — новый такой метод должен
#: попасть сюда осознанно, а не появиться незаметно.
UNKNOWN_SCHEMA = {
    "MSG_SEARCH_TOUCH",
    "GET_INBOUND_CALLS",
    "EXTERNAL_CALLBACK",
    "GET_LAST_MENTIONS",
    "STICKER_CREATE",
    "ASSETS_LIST_MODIFY",
    "OK_TOKEN",
}


def wrapper_signatures() -> dict[str, tuple[list[str], bool]]:
    """``{опкод: (именованные параметры, есть ли **kwargs)}``."""
    import ast

    result: dict[str, tuple[list[str], bool]] = {}
    for path in sorted(METHODS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for func in ast.walk(tree):
            if not isinstance(func, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            if func.name.startswith("_"):
                continue
            opcodes = {
                node.attr
                for node in ast.walk(func)
                if isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "Opcode"
            }
            if len(opcodes) != 1:
                continue
            names = [a.arg for a in func.args.args if a.arg != "self"]
            names += [a.arg for a in func.args.kwonlyargs]
            opcode = opcodes.pop()
            previous = result.get(opcode)
            if previous and previous[0]:
                continue  # уже есть типизированная обёртка
            result[opcode] = (names, func.args.kwarg is not None)
    return result


def test_every_callable_opcode_has_named_parameters_or_is_listed():
    """Обёртка должна брать именованные аргументы, а не только **payload."""
    signatures = wrapper_signatures()
    untyped = {
        name
        for name, (names, has_kwargs) in signatures.items()
        if not names and has_kwargs
    }
    assert untyped == UNKNOWN_SCHEMA, (
        "изменился список обёрток без разобранной схемы: "
        f"лишние {sorted(untyped - UNKNOWN_SCHEMA)}, "
        f"пропали {sorted(UNKNOWN_SCHEMA - untyped)}"
    )


def test_unknown_schema_methods_say_so_in_docstring():
    """У таких обёрток в докстроке должно быть честно написано про схему."""
    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in METHODS_DIR.glob("*.py")
    )
    for opcode in sorted(UNKNOWN_SCHEMA):
        marker = f"{opcode} ("
        index = sources.find(marker)
        assert index != -1, f"нет докстроки для {opcode}"
        assert "Схема запроса неизвестна" in sources[index : index + 400], (
            f"{opcode}: докстрока не предупреждает о неизвестной схеме"
        )
