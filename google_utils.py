import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import re

from config import GOOGLE_CREDENTIALS_FILE, USER_CONFIG_FILE, OWNER_EMAIL

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def authorize_gspread():
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        GOOGLE_CREDENTIALS_FILE, SCOPES
    )
    return gspread.authorize(creds)


def _load_config():
    with open(USER_CONFIG_FILE, "r") as f:
        return json.load(f)


def normalize(text: str) -> str:
    """Оставляет только буквы и цифры, приводит к нижнему регистру."""
    return re.sub(r"[^0-9a-zA-Zа-яА-Я]", "", text).lower()


def create_spreadsheet():
    client = authorize_gspread()
    spreadsheet = client.create("Финансы")
    worksheet = spreadsheet.sheet1
    worksheet.insert_row(["Дата", "Тип", "Сумма", "Категория 1", "Категория 2"], 1)
    # Доступ на чтение для OWNER_EMAIL
    if OWNER_EMAIL:
        spreadsheet.share(OWNER_EMAIL, perm_type="user", role="reader")

    # сохраняем id
    with open(USER_CONFIG_FILE, "w") as f:
        json.dump({"spreadsheet_id": spreadsheet.id}, f)

    return f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}"


def append_row(row):
    client = authorize_gspread()
    cfg = _load_config()
    sheet = client.open_by_key(cfg["spreadsheet_id"]).sheet1
    sheet.append_row(row)


def get_last_rows(n=5):
    client = authorize_gspread()
    cfg = _load_config()
    sheet = client.open_by_key(cfg["spreadsheet_id"]).sheet1
    all_rows = sheet.get_all_values()
    return all_rows[1:][-n:]  # без заголовка


def update_row(row_index, new_row):
    client = authorize_gspread()
    cfg = _load_config()
    sheet = client.open_by_key(cfg["spreadsheet_id"]).sheet1
    for col, val in enumerate(new_row, start=1):
        sheet.update_cell(row_index, col, val)


def delete_row(row_index):
    client = authorize_gspread()
    cfg = _load_config()
    sheet = client.open_by_key(cfg["spreadsheet_id"]).sheet1
    sheet.delete_rows(row_index)


# === Категории ===


def create_category_sheet_if_missing():
    client = authorize_gspread()
    cfg = _load_config()
    spreadsheet = client.open_by_key(cfg["spreadsheet_id"])
    try:
        spreadsheet.worksheet("Категории")
    except gspread.exceptions.WorksheetNotFound:
        spreadsheet.add_worksheet("Категории", rows=100, cols=2)


def get_categories() -> set[tuple[str, str]]:
    """Возвращает множество нормализованных пар (cat1, cat2)."""
    client = authorize_gspread()
    cfg = _load_config()
    ws = client.open_by_key(cfg["spreadsheet_id"]).worksheet("Категории")
    vals = ws.get_all_values()
    result = set()
    for row in vals:
        if len(row) >= 2:
            result.add((normalize(row[0]), normalize(row[1])))
    return result


def add_category_to_sheet(cat1: str, cat2: str):
    """Добавляет новую пару в лист 'Категории'."""
    client = authorize_gspread()
    cfg = _load_config()
    ws = client.open_by_key(cfg["spreadsheet_id"]).worksheet("Категории")
    ws.append_row([cat1, cat2])
