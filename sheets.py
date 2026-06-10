import os
from datetime import datetime
from pathlib import Path

import gspread

# Файлы токенов
CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
AUTHORIZED_USER_FILE = "authorized_user.json"

# Соответствие колонок таблицы:
# A  Дата поступления заявки
# B  Контрагент
# C  Контакты
# D  Статус поставщика
# E  Сумма
# F  Назначение платежа
# G  Статья бюджета
# H  Дата оплаты заявки
# I  Номер заявки
# J  Комментарий (прикреплённые файлы)
# K  Комментарий Регионального


def _get_client() -> gspread.Client:
    """
    Авторизация через OAuth2.
    При первом запуске открывает браузер для входа в Google.
    Токен сохраняется в authorized_user.json — повторный вход не нужен.
    """
    return gspread.oauth(
        credentials_filename=CREDENTIALS_FILE,
        authorized_user_filename=AUTHORIZED_USER_FILE,
    )


def append_request(
    spreadsheet_id: str,
    sheet_name: str,
    request_data: dict,
    credentials_file: str = CREDENTIALS_FILE,
) -> bool:
    """
    Добавляет строки заявки в указанный лист Google Sheets.
    Возвращает True при успехе.
    """
    try:
        client = _get_client()
        spreadsheet = client.open_by_key(spreadsheet_id)
    except Exception as exc:
        print(f"  [ERROR] Не удалось подключиться к Google Sheets: {exc}")
        return False

    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        print(f"  [ERROR] Лист «{sheet_name}» не найден в таблице!")
        return False
    except Exception as exc:
        print(f"  [ERROR] Ошибка при открытии листа «{sheet_name}»: {exc}")
        return False

    today = datetime.now().strftime("%d.%m")
    request_num = request_data.get("request_number", "")
    files_note = ", ".join(request_data.get("files", []))
    items = request_data.get("items", [])

    rows_to_add = []
    if items:
        for item in items:
            rows_to_add.append(_build_row(
                date=today,
                amount=item["amount"],
                category=item["category"],
                request_num=request_num,
                files_note=files_note,
            ))
    else:
        rows_to_add.append(_build_row(
            date=today,
            amount=request_data.get("total_amount", ""),
            category="",
            request_num=request_num,
            files_note=files_note,
        ))

    cell_format = {
        "horizontalAlignment": "CENTER",
        "verticalAlignment": "MIDDLE",
        "textFormat": {
            "fontFamily": "Times New Roman",
            "fontSize": 13,
        },
    }

    try:
        for row in rows_to_add:
            resp = worksheet.append_row(row, value_input_option="USER_ENTERED")
            # Применяем форматирование к только что добавленной строке
            try:
                updated_range = resp["updates"]["updatedRange"]  # "Лист!A12:K12"
                cell_range = updated_range.split("!", 1)[1]
                worksheet.format(cell_range, cell_format)
            except Exception as fmt_exc:
                print(f"  [WARN] Не удалось отформатировать строку: {fmt_exc}")
        return True
    except Exception as exc:
        print(f"  [ERROR] Ошибка при записи строки: {exc}")
        return False


def _build_row(date, amount, category, request_num, files_note) -> list:
    return [
        date,            # A: Дата поступления заявки
        "",              # B: Контрагент
        "",              # C: Контакты
        "",              # D: Статус поставщика
        amount,          # E: Сумма
        "",              # F: Назначение платежа
        category,        # G: Статья бюджета
        "не оплачено",  # H: Дата оплаты заявки
        request_num,     # I: Номер заявки
        "",              # J: Комментарий (оставляем пустым для твоих заметок)
        "",              # K: Комментарий Регионального
    ]
