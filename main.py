"""
Финансовый мониторинг заявок: Telegram → Google Sheets
Запуск: python main.py

Особенности:
- Слушает новые заявки в реальном времени.
- При запуске «догоняет» заявки, пришедшие пока бот был выключен
  (защита от пропусков — ни одна заявка не теряется).
"""
import asyncio
import json
import os
from datetime import datetime

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.sessions import StringSession

from parser import is_request_message, parse_request_message
from sheets import append_request

load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
SESSION_STRING = os.getenv("SESSION_STRING", "")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")

STATE_FILE = "state.json"


# ── Состояние (последняя обработанная заявка каждой школы) ──────────────────

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_state(state: dict) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"  [WARN] Не удалось сохранить состояние: {exc}")


def load_schools() -> dict:
    # На сервере (GitHub Actions) список школ берётся из переменной SCHOOLS_JSON,
    # локально — из файла schools.json.
    raw = os.getenv("SCHOOLS_JSON", "")
    if raw.strip():
        return json.loads(raw)
    with open("schools.json", "r", encoding="utf-8") as f:
        return json.load(f)


async def resolve_bot_ids(client: TelegramClient, schools: list) -> dict:
    """username ботов → {bot_id: {school_name, sheet_name, entity}}"""
    mapping = {}
    print("Загружаю школы:")
    for school in schools:
        username = school.get("bot_username", "").strip().lstrip("@")
        sheet = school.get("sheet_name", "")
        name = school.get("name", username)

        if not username or not sheet:
            print(f"  ⚠  {name}: пропущен (нет bot_username или sheet_name)")
            continue

        try:
            entity = await client.get_entity(username)
            mapping[entity.id] = {
                "school_name": name,
                "sheet_name": sheet,
                "entity": entity,
            }
            print(f"  ✓  {name}: @{username} → лист «{sheet}»")
        except Exception as exc:
            print(f"  ✗  {name}: не удалось найти @{username} — {exc}")

    return mapping


async def process_message(msg, bot_info: dict, state: dict, *, source: str) -> None:
    """Обрабатывает одно сообщение-заявку и пишет в таблицу."""
    text = getattr(msg, "text", "") or ""
    bot_id = bot_info["bot_id"]

    def advance():
        prev = state.get(str(bot_id), 0)
        if msg.id > prev:
            state[str(bot_id)] = msg.id
            save_state(state)

    # Не заявка — просто двигаем указатель, чтобы не пересматривать.
    if not is_request_message(text):
        advance()
        return

    school = bot_info["school_name"]
    sheet = bot_info["sheet_name"]
    ts = datetime.now().strftime("%H:%M:%S")

    request = parse_request_message(text)
    tag = "(догнал)" if source == "catchup" else ""
    print(f"\n[{ts}] Новая заявка от «{school}» {tag}")
    print(f"  Номер  : {request['request_number'] or '—'}")
    print(f"  Сумма  : {request['total_amount'] or '—'} тг")
    print(f"  Статей : {len(request['items'])}")
    if request["files"]:
        print(f"  Файлы  : {', '.join(request['files'])}")

    ok = append_request(
        spreadsheet_id=SPREADSHEET_ID,
        sheet_name=sheet,
        request_data=request,
    )
    if ok:
        print(f"  ✓ Записано в лист «{sheet}»")
        advance()  # двигаем указатель ТОЛЬКО при успешной записи
    else:
        print(f"  ✗ Ошибка записи в лист «{sheet}» — заявка повторится при следующем запуске")


async def catch_up(client: TelegramClient, bot_map: dict, state: dict) -> None:
    """Догоняет заявки, пришедшие пока бот был выключен."""
    print("\nПроверяю пропущенные заявки...")
    total = 0
    for bot_id, info in bot_map.items():
        info["bot_id"] = bot_id
        entity = info["entity"]
        last_id = state.get(str(bot_id))

        # Первый запуск для этой школы — просто запоминаем текущую позицию,
        # старую историю не импортируем.
        if last_id is None:
            newest = 0
            async for m in client.iter_messages(entity, limit=1):
                newest = m.id
            state[str(bot_id)] = newest
            continue

        # Собираем все сообщения новее last_id (от старых к новым).
        missed = []
        async for m in client.iter_messages(entity, min_id=last_id):
            missed.append(m)
        for m in reversed(missed):
            before = total
            await process_message(m, info, state, source="catchup")
            if is_request_message(getattr(m, "text", "") or ""):
                total += 1

    save_state(state)
    if total:
        print(f"Догнал пропущенных заявок: {total}")
    else:
        print("Пропущенных заявок нет.")


async def main() -> None:
    print("=" * 50)
    print("  Финансовый мониторинг заявок")
    print(f"  {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print("=" * 50)

    if not API_ID or not API_HASH:
        print("\n[ERROR] Заполни TELEGRAM_API_ID и TELEGRAM_API_HASH в файле .env")
        return
    if not SPREADSHEET_ID:
        print("\n[ERROR] Заполни SPREADSHEET_ID в файле .env")
        return
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"\n[ERROR] Файл {CREDENTIALS_FILE} не найден.")
        return

    schools_config = load_schools()
    state = load_state()

    if SESSION_STRING:
        client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
        print("\nРежим: облачная сессия (SESSION_STRING)")
    else:
        client = TelegramClient("userbot_session", API_ID, API_HASH)
        print("\nРежим: локальная сессия (userbot_session.session)")

    await client.start()
    print("Telegram: подключено\n")

    bot_map = await resolve_bot_ids(client, schools_config["schools"])
    if not bot_map:
        print("\n[ERROR] Ни один бот не найден. Проверь schools.json")
        return

    # Записываем bot_id в info для удобства
    for bid, info in bot_map.items():
        info["bot_id"] = bid

    # Догоняем пропущенное
    await catch_up(client, bot_map, state)

    @client.on(events.NewMessage())
    async def on_new_message(event):
        info = bot_map.get(event.sender_id)
        if info:
            await process_message(event.message, info, state, source="live")

    print(f"\nМониторинг запущен. Слежу за {len(bot_map)} ботами. Ctrl+C для остановки.\n")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
