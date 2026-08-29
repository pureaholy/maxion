"""Загрузка и скачивание медиа."""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any, BinaryIO

from ..const import UPLOAD_HEADERS
from ..errors import MaxError
from ..opcodes import Opcode
from ..types import Message
from ..utils import clean
from .base import MethodsBase


class MediaMethods(MethodsBase):
    """Опкоды 80-83, 87-89, 202, 301.

    Загрузка идёт в два шага: у сервера запрашивается URL заливки, файл
    отправляется обычным multipart POST, после чего сервер присылает
    NOTIF_ATTACH (136) с готовым вложением.
    """

    # --- низкоуровневые запросы слотов ------------------------------------

    async def request_photo_upload(
        self, count: int = 1, *, type_: str | None = None, profile: bool | None = None
    ) -> dict[str, Any]:
        """PHOTO_UPLOAD (80). ``profile=True`` — слот под аватар."""
        return await self.invoke(
            Opcode.PHOTO_UPLOAD,
            clean({"count": count, "type": type_, "profile": profile}),
        )

    async def request_video_upload(
        self,
        count: int = 1,
        *,
        type_: str | None = None,
        uploader_type: str | None = None,
    ) -> dict[str, Any]:
        """VIDEO_UPLOAD (82)."""
        return await self.invoke(
            Opcode.VIDEO_UPLOAD,
            clean({"count": count, "type": type_, "uploaderType": uploader_type}),
        )

    async def request_file_upload(self, count: int = 1) -> dict[str, Any]:
        """FILE_UPLOAD (87)."""
        return await self.invoke(Opcode.FILE_UPLOAD, {"count": count})

    async def request_sticker_upload(self, count: int = 1) -> dict[str, Any]:
        """STICKER_UPLOAD (81)."""
        return await self.invoke(Opcode.STICKER_UPLOAD, {"count": count})

    # --- загрузка ----------------------------------------------------------

    async def upload_photo(
        self,
        file: str | os.PathLike[str] | bytes | BinaryIO,
        *,
        chat_id: int | None = None,
        filename: str = "image.jpg",
    ) -> dict[str, Any]:
        """Загружает фото и возвращает готовое вложение ``{_type: PHOTO, ...}``."""
        info = await self.request_photo_upload()
        url = info.get("url")
        if not url:
            raise MaxError("Сервер не выдал URL для загрузки фото")
        if chat_id is not None:
            await self.send_typing(chat_id, "PHOTO")
        data = await self._post_upload(url, file, filename, "image/jpeg")
        photos = (data or {}).get("photos") or {}
        if not photos:
            raise MaxError(f"Неожиданный ответ загрузчика: {data!r}")
        token = next(iter(photos.values())).get("token")
        return {"_type": "PHOTO", "photoToken": token}

    async def upload_video(
        self,
        file: str | os.PathLike[str] | bytes | BinaryIO,
        *,
        chat_id: int | None = None,
        filename: str = "video.mp4",
        timeout: float = 600.0,
    ) -> dict[str, Any]:
        """Загружает видео и дожидается его обработки сервером."""
        info = await self.request_video_upload()
        slots = info.get("info") or []
        if not slots:
            raise MaxError("Сервер не выдал слот для видео")
        slot = slots[0]
        if chat_id is not None:
            await self.send_typing(chat_id, "VIDEO")
        waiter = self._attach_waiter("videoId", int(slot["videoId"]))
        await self._post_upload(slot["url"], file, filename, "video/mp4")
        await self._await_attach(waiter, timeout)
        return {"_type": "VIDEO", "videoId": int(slot["videoId"]), "token": slot.get("token")}

    async def upload_file(
        self,
        file: str | os.PathLike[str] | bytes | BinaryIO,
        *,
        chat_id: int | None = None,
        filename: str | None = None,
        timeout: float = 600.0,
    ) -> dict[str, Any]:
        """Загружает произвольный файл."""
        name = filename or _guess_name(file)
        info = await self.request_file_upload()
        slots = info.get("info") or []
        if not slots:
            raise MaxError("Сервер не выдал слот для файла")
        slot = slots[0]
        if chat_id is not None:
            await self.send_typing(chat_id, "FILE")
        waiter = self._attach_waiter("fileId", int(slot["fileId"]))
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        await self._post_upload(slot["url"], file, name, mime)
        await self._await_attach(waiter, timeout)
        return {"_type": "FILE", "fileId": int(slot["fileId"]), "name": name}

    # --- отправка с медиа --------------------------------------------------

    async def send_photo(
        self, chat_id: int, file: str | os.PathLike[str] | bytes | BinaryIO, caption: str = "", **kwargs
    ) -> Message:
        """Загружает фото и сразу отправляет его в чат."""
        attach = await self.upload_photo(file, chat_id=chat_id)
        return await self.send_message(chat_id, caption, attaches=[attach], **kwargs)

    async def send_video(
        self, chat_id: int, file: str | os.PathLike[str] | bytes | BinaryIO, caption: str = "", **kwargs
    ) -> Message:
        attach = await self.upload_video(file, chat_id=chat_id)
        return await self.send_message(chat_id, caption, attaches=[attach], **kwargs)

    async def send_file(
        self,
        chat_id: int,
        file: str | os.PathLike[str] | bytes | BinaryIO,
        caption: str = "",
        *,
        filename: str | None = None,
        **kwargs,
    ) -> Message:
        attach = await self.upload_file(file, chat_id=chat_id, filename=filename)
        return await self.send_message(chat_id, caption, attaches=[attach], **kwargs)

    # --- скачивание --------------------------------------------------------

    async def get_video_url(
        self, chat_id: int, message_id: str, video_id: int
    ) -> dict[str, Any]:
        """VIDEO_PLAY (83). Прямые ссылки на видео по качествам."""
        payload = await self.invoke(
            Opcode.VIDEO_PLAY,
            {"videoId": video_id, "chatId": chat_id, "messageId": str(message_id)},
        )
        return {
            key: value
            for key, value in payload.items()
            if key not in ("cache", "EXTERNAL") and isinstance(value, str)
        }

    async def get_file_url(self, chat_id: int, message_id: str, file_id: int) -> str | None:
        """FILE_DOWNLOAD (88). Прямая ссылка на файл."""
        payload = await self.invoke(
            Opcode.FILE_DOWNLOAD,
            {"fileId": file_id, "chatId": chat_id, "messageId": str(message_id)},
        )
        return payload.get("url")

    async def get_audio_url(
        self,
        chat_id: int,
        message_id: str,
        audio_id: int,
        *,
        token: str | None = None,
    ) -> dict[str, Any]:
        """AUDIO_PLAY (301). Прямая ссылка на голосовое или аудио."""
        return await self.invoke(
            Opcode.AUDIO_PLAY,
            clean(
                {
                    "audioId": audio_id,
                    "chatId": chat_id,
                    "messageId": str(message_id),
                    "token": token,
                }
            ),
        )

    async def download(self, url: str, dest: str | os.PathLike[str]) -> Path:
        """Скачивает файл по прямой ссылке."""
        session = await self._http()
        path = Path(dest)
        path.parent.mkdir(parents=True, exist_ok=True)
        async with session.get(url, headers=UPLOAD_HEADERS) as response:
            response.raise_for_status()
            with path.open("wb") as fh:
                async for chunk in response.content.iter_chunked(1 << 16):
                    fh.write(chunk)
        return path

    async def get_link_info(self, url: str) -> dict[str, Any]:
        """LINK_INFO (89). На проводе поле называется ``link``, не ``url``."""
        return await self.invoke(Opcode.LINK_INFO, {"link": url})

    async def transcribe(
        self,
        chat_id: int,
        message_id: str,
        media_id: int | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """TRANSCRIBE_MEDIA (202). Расшифровка голосового сообщения."""
        return await self.invoke(
            Opcode.TRANSCRIBE_MEDIA,
            clean(
                {
                    "chatId": chat_id,
                    "messageId": str(message_id),
                    "mediaId": media_id,
                    **extra,
                }
            ),
        )

    # --- внутреннее --------------------------------------------------------

    async def _post_upload(
        self,
        url: str,
        file: str | os.PathLike[str] | bytes | BinaryIO,
        filename: str,
        mimetype: str,
    ) -> dict[str, Any] | None:
        import aiohttp

        session = await self._http()
        payload, close_after = _open(file)
        form = aiohttp.FormData()
        form.add_field("file", payload, filename=filename, content_type=mimetype)
        try:
            async with session.post(url, headers=UPLOAD_HEADERS, data=form) as response:
                response.raise_for_status()
                try:
                    return await response.json(content_type=None)
                except Exception:
                    return None
        finally:
            if close_after and hasattr(payload, "close"):
                payload.close()


def _open(file: Any) -> tuple[Any, bool]:
    if isinstance(file, (bytes, bytearray)):
        return bytes(file), False
    if isinstance(file, (str, os.PathLike)):
        return open(file, "rb"), True
    return file, False


def _guess_name(file: Any) -> str:
    if isinstance(file, (str, os.PathLike)):
        return Path(file).name
    name = getattr(file, "name", None)
    return Path(str(name)).name if name else "file.bin"
