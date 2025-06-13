import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
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


def create_spreadsheet():
    client = authorize_gspread()
    spreadsheet = client.create("Финансы")

    worksheet = spreadsheet.sheet1
    worksheet.insert_row(["Дата", "Тип", "Сумма", "Категория 1", "Категория 2"], 1)

    # Даем доступ указанному email
    if OWNER_EMAIL:
        spreadsheet.share(OWNER_EMAIL, perm_type="user", role="writer")

    with open(USER_CONFIG_FILE, "w") as f:
        json.dump({"spreadsheet_id": spreadsheet.id}, f)

    return f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}"


def append_row(row):
    client = authorize_gspread()
    with open(USER_CONFIG_FILE, "r") as f:
        spreadsheet_id = json.load(f)["spreadsheet_id"]
    sheet = client.open_by_key(spreadsheet_id).sheet1
    sheet.append_row(row)


def get_last_rows(n=5):
    client = authorize_gspread()
    with open(USER_CONFIG_FILE, "r") as f:
        spreadsheet_id = json.load(f)["spreadsheet_id"]
    sheet = client.open_by_key(spreadsheet_id).sheet1
    all_rows = sheet.get_all_values()
    return all_rows[1:][-n:]  # без заголовков


def update_row(row_index, new_row):
    client = authorize_gspread()
    with open(USER_CONFIG_FILE, "r") as f:
        spreadsheet_id = json.load(f)["spreadsheet_id"]
    sheet = client.open_by_key(spreadsheet_id).sheet1
    for i, value in enumerate(new_row, 1):
        sheet.update_cell(row_index, i, value)


def delete_row(row_index):
    client = authorize_gspread()
    with open(USER_CONFIG_FILE, "r") as f:
        spreadsheet_id = json.load(f)["spreadsheet_id"]
    sheet = client.open_by_key(spreadsheet_id).sheet1
    sheet.delete_rows(row_index)
