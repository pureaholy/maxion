"""Отправка медиа и скачивание вложений.

    python examples/send_media.py -68093732121255 cat.jpg
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maxion.raw import MaxClient, Text
from maxion.raw.enums import AttachType


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("chat_id", type=int)
    parser.add_argument("file", type=Path, nargs="?")
    parser.add_argument("--phone")
    parser.add_argument("--pull", action="store_true", help="скачать вложения из чата")
    args = parser.parse_args()

    async with MaxClient("media.session") as client:
        await client.start(phone=args.phone)

        if args.file:
            suffix = args.file.suffix.lower()
            caption = Text("Отправлено через ").code("maxion" / "raw")
            if suffix in (".jpg", ".jpeg", ".png", ".webp"):
                message = await client.send_photo(args.chat_id, args.file, caption)
            elif suffix in (".mp4", ".mov", ".mkv"):
                message = await client.send_video(args.chat_id, args.file, caption)
            else:
                message = await client.send_file(args.chat_id, args.file, caption)
            print(f"Отправлено: {message.id}")

        if args.pull:
            out = Path("downloads")
            out.mkdir(exist_ok=True)
            messages = await client.get_chat_media(
                args.chat_id, attach_types=["PHOTO", "VIDEO", "FILE"]
            )
            print(f"Сообщений с медиа: {len(messages)}")
            for message in messages:
                for attach in message.attaches:
                    if attach.type == AttachType.FILE.value:
                        url = await client.get_file_url(
                            args.chat_id, message.id, attach.file_id
                        )
                        name = attach.name or f"{attach.file_id}.bin"
                    elif attach.type == AttachType.VIDEO.value:
                        urls = await client.get_video_url(
                            args.chat_id, message.id, attach.video_id
                        )
                        url = next(iter(urls.values()), None)
                        name = f"{attach.video_id}.mp4"
                    elif attach.type == AttachType.PHOTO.value:
                        url, name = attach.url, f"{attach.photo_id}.jpg"
                    else:
                        continue
                    if not url:
                        continue
                    path = await client.download(url, out / name)
                    print(f"  {path}")


if __name__ == "__main__":
    asyncio.run(main())
