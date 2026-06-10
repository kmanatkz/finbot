"""
Разовый запуск для GitHub Actions: подключается, догоняет новые заявки
во всех школах и выходит. Состояние (state.json) сохраняется между запусками.
"""
import asyncio
import os

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

import main as m

load_dotenv()


async def run() -> None:
    session = os.getenv("SESSION_STRING", "")
    if not session:
        print("[ERROR] SESSION_STRING не задан")
        return

    client = TelegramClient(StringSession(session), m.API_ID, m.API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        print("[ERROR] Сессия Telegram недействительна")
        return
    print("Telegram: подключено")

    schools = m.load_schools()["schools"]
    state = m.load_state()
    bot_map = await m.resolve_bot_ids(client, schools)
    for bid, info in bot_map.items():
        info["bot_id"] = bid

    await m.catch_up(client, bot_map, state)
    await client.disconnect()
    print("Готово.")


if __name__ == "__main__":
    asyncio.run(run())
