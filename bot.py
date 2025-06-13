import asyncio
import os
import json

from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command  # <-- вот так подключаем фильтр

from google_utils import create_spreadsheet
from config import BOT_TOKEN, USER_CONFIG_FILE

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


@dp.message(Command("start"))
async def start_handler(message: Message):
    if not os.path.exists(USER_CONFIG_FILE):
        sheet_url = create_spreadsheet()
        await message.answer(f"Таблица создана:\n{sheet_url}")
    else:
        with open(USER_CONFIG_FILE, "r") as f:
            config = json.load(f)
        sheet_id = config["spreadsheet_id"]
        await message.answer(
            f"Таблица:\nhttps://docs.google.com/spreadsheets/d/{sheet_id}"
        )


async def main():
    # Удаляем возможные вебхуки и запускаем polling
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
