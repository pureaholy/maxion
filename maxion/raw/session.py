"""Хранилище сессии: токен логина, deviceId, идентификатор пользователя."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Session:
    """Всё, что нужно, чтобы залогиниться без SMS повторно.

    ``device_id`` привязан к сессии на сервере: если его поменять, токен
    перестанет подходить и потребуется новый код.
    """

    token: str | None = None
    device_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    phone: str | None = None
    user_id: int | None = None
    name: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    path: Path | None = field(default=None, repr=False, compare=False)

    # --- файловое хранилище ------------------------------------------------

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> "Session":
        """Читает сессию из файла; если файла нет -- создаёт пустую."""
        p = Path(path)
        if not p.exists():
            return cls(path=p)
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls(path=p)
        session = cls(
            token=data.get("token"),
            device_id=data.get("device_id") or str(uuid.uuid4()),
            phone=data.get("phone"),
            user_id=data.get("user_id"),
            name=data.get("name"),
            extra=data.get("extra") or {},
        )
        session.path = p
        return session

    def save(self, path: str | os.PathLike[str] | None = None) -> None:
        """Атомарно записывает сессию на диск с правами 0600."""
        target = Path(path) if path else self.path
        if target is None:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data.pop("path", None)
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, target)
            try:
                os.chmod(target, 0o600)
            except OSError:  # ФС без POSIX-прав
                pass
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        self.path = target

    def clear(self) -> None:
        """Забывает токен (device_id сохраняем -- он привязан к устройству)."""
        self.token = None
        self.user_id = None
        self.save()

    @property
    def authorized(self) -> bool:
        return bool(self.token)
