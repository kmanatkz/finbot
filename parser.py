import re


def is_request_message(text: str) -> bool:
    """Проверяет, является ли сообщение заявкой на оплату."""
    if not text:
        return False
    return "Заявка" in text and ("тг" in text or "ИТОГО" in text)


def parse_request_message(text: str) -> dict:
    """
    Парсит текст заявки из Telegram-бота.

    Ожидаемый формат:
        Заявка№000000137
        ----------------------------------------
        ИТОГО:65 000 тг.
        1) Строительство/Ремонт: 65 000 тг.
        ----------------------------------------
        Прикрепленные файлы(1 шт):
        1) DOC-20250820-WA0000.
    """
    result = {
        "request_number": "",
        "total_amount": "",
        "items": [],
        "files": [],
    }

    if not text:
        return result

    # Номер заявки: "Заявка№000000137" → "137" (только число, без префикса и нулей)
    num_match = re.search(r"Заявка[№#](\d+)", text, re.IGNORECASE)
    if num_match:
        digits = num_match.group(1).lstrip("0") or "0"
        result["request_number"] = digits

    # Итоговая сумма: "ИТОГО:65 000 тг."
    # Обрабатываем пробелы и неразрывные пробелы ( ) как разделители тысяч
    total_match = re.search(
        r"ИТОГО\s*[:\s]\s*([\d\s \xa0]+?)\s*тг", text, re.IGNORECASE
    )
    if total_match:
        raw = total_match.group(1)
        result["total_amount"] = _clean_amount(raw)

    # Статьи: "1) Строительство/Ремонт: 65 000 тг."
    for match in re.finditer(
        r"\d+\)\s+(.+?):\s*([\d\s \xa0]+?)\s*тг", text
    ):
        category = match.group(1).strip()
        amount = _clean_amount(match.group(2))
        # Пропускаем строки с «ИТОГО» чтобы не дублировать
        if "итого" not in category.lower():
            result["items"].append({"category": category, "amount": amount})

    # Прикреплённые файлы: раздел после "Прикрепленные файлы"
    files_block = re.search(
        r"Прикрепленные файлы[^:]*:(.*)", text, re.DOTALL | re.IGNORECASE
    )
    if files_block:
        names = re.findall(r"\d+\)\s+(.+?)(?:\n|$)", files_block.group(1))
        result["files"] = [n.strip().rstrip(".") for n in names if n.strip()]

    return result


def _clean_amount(raw: str) -> str:
    """Убирает пробелы-разделители тысяч, оставляет только цифры."""
    return re.sub(r"[\s \xa0]", "", raw).strip()
