"""Приём входящего звонка MAX.

    pip install "maxion[calls]"
    python examples/answer_call.py

Каркас на форматах, снятых с живого звонка. Когда кто-то звонит, приходит
событие ``call`` (NOTIF_CALL_START) с параметрами WebRTC в поле vcp; из них
собирается :class:`maxion.calls.Call`, который поднимает трубку и гонит
аудио-обмен через wss://videowebrtc.okcdn.ru.

Замечание: это последний, ещё не проверенный живым звонком, шаг. Все три
уровня протокола (опкоды MAX, сигнализация OK, WebRTC-медиа) разобраны и
покрыты тестами; здесь они соединены в сценарий.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maxion import Client
from maxion.calls import Call

app = Client("my_account")


@app.raw.router.on("call")
async def on_incoming_call(update):
    """NOTIF_CALL_START — кто-то звонит."""
    print(
        f"Входящий звонок: caller={update.caller_id} "
        f"тип={update.type} conversation={update.conversation_id}"
    )
    cfg = update.config()
    if cfg is None:
        print("  нет vcp — не разобрать параметры звонка")
        return
    print(f"  канал: {cfg.signaling_url}")
    print(f"  STUN: {cfg.stun}")
    print(f"  TURN: {cfg.turn}")

    call = Call.incoming(update)
    try:
        # ответить, транслируя звук из файла (или microphone=True с микрофона)
        await call.answer(audio="hello.wav")
        print("  трубка поднята, идёт обмен...")
        await asyncio.wait_for(call.wait_hangup(), timeout=120)
    except asyncio.TimeoutError:
        print("  таймаут звонка")
    finally:
        await call.hangup()
        print("  звонок завершён")


async def main() -> None:
    await app.start()
    print(f"Вошли как {app.me.full_name}. Ждём входящих звонков (Ctrl+C — выход).")
    await app.idle()


if __name__ == "__main__":
    asyncio.run(main())
