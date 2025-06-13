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
