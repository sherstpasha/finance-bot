import asyncio
import os
import json
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext

from config import BOT_TOKEN, USER_CONFIG_FILE
from google_utils import (
    create_spreadsheet,
    append_row,
    get_last_rows,
    update_row,
    delete_row,
)
from states import AddRecord, EditRecord
from middlewares import AccessMiddleware

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# Главное меню: Доход, Расход, Изменить, Удалить
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Доход"), KeyboardButton(text="Расход")],
        [KeyboardButton(text="Изменить"), KeyboardButton(text="Удалить")],
    ],
    resize_keyboard=True,
)


async def cleanup_and_confirm(
    chat_id: int,
    msg_ids: list[int],
    confirm_text: str | None = None,
    reply_markup: ReplyKeyboardMarkup | None = None,
):
    # удаляем промежуточные
    for mid in msg_ids:
        try:
            await bot.delete_message(chat_id, mid)
        except:
            pass

    # если нужно отправить клавиатуру — даже без текста
    if reply_markup:
        text = confirm_text if confirm_text is not None else "\u200b"
        await bot.send_message(
            chat_id,
            text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )
    # иначе, если дали только текст — отправляем его
    elif confirm_text is not None:
        await bot.send_message(
            chat_id,
            confirm_text,
            parse_mode=ParseMode.HTML,
        )


# ========== START ==========


@dp.message(Command("start"))
async def start_handler(message: Message, state: FSMContext):
    if not os.path.exists(USER_CONFIG_FILE):
        sheet_url = create_spreadsheet()
        await message.answer(f"Таблица создана:\n{sheet_url}", reply_markup=main_menu)
    else:
        with open(USER_CONFIG_FILE, "r") as f:
            sheet_id = json.load(f)["spreadsheet_id"]
        await message.answer(
            f"Таблица:\nhttps://docs.google.com/spreadsheets/d/{sheet_id}",
            reply_markup=main_menu,
        )
    await state.clear()


# ========== ADD RECORD (Income/Expense) ==========


async def _ask_for_data(message: Message, state: FSMContext, entry_type: str):
    await state.set_data({"msg_ids": [message.message_id], "entry_type": entry_type})
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅ Назад")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    bot_msg = await message.answer(
        "Введите: сумма, категория 1, категория 2\nПример: 1200, еда, кафе",
        reply_markup=kb,
    )
    data = await state.get_data()
    await state.update_data(msg_ids=data["msg_ids"] + [bot_msg.message_id])
    await state.set_state(AddRecord.entering_data)


@dp.message(F.text == "Доход")
async def add_income(message: Message, state: FSMContext):
    await _ask_for_data(message, state, "Доход")


@dp.message(F.text == "Расход")
async def add_expense(message: Message, state: FSMContext):
    await _ask_for_data(message, state, "Расход")


@dp.message(AddRecord.entering_data)
async def process_data(message: Message, state: FSMContext):
    data = await state.get_data()
    msg_ids = data["msg_ids"] + [message.message_id]

    # Назад → просто показать главное меню
    if message.text == "⬅ Назад":
        await cleanup_and_confirm(
            message.chat.id, msg_ids, confirm_text=None, reply_markup=main_menu
        )
        return await state.clear()

    entry_type = data["entry_type"]
    try:
        parts = [p.strip() for p in message.text.split(",")]
        if len(parts) != 3:
            raise ValueError
        amount = float(parts[0])
        cat1, cat2 = parts[1], parts[2]
        append_row(
            [datetime.today().strftime("%Y-%m-%d"), entry_type, amount, cat1, cat2]
        )

        await cleanup_and_confirm(
            message.chat.id,
            msg_ids,
            confirm_text=f"✔ Запись добавлена: <b>{entry_type}</b> {amount}₽ — {cat1} / {cat2}",
            reply_markup=main_menu,
        )

    except:
        await message.answer("Ошибка формата. Пример: 1200, еда, кафе")
    finally:
        await state.clear()


# ========== EDIT / DELETE ==========


@dp.message(F.text == "Изменить")
async def edit_start(message: Message, state: FSMContext):
    rows = get_last_rows()
    if not rows:
        return await message.answer(
            "Нет записей для изменения.", reply_markup=main_menu
        )

    recent = rows[-5:]
    await state.set_data(
        {"msg_ids": [message.message_id], "rows": recent, "action": "edit"}
    )

    text = "Выберите запись для редактирования:\n"
    for i, row in enumerate(recent, 1):
        text += f"{i}) {row[0]} — {row[1]} {row[2]}₽ — {row[3]}/{row[4]}\n"

    buttons = [[KeyboardButton(text=str(i))] for i in range(1, len(recent) + 1)]
    buttons.append([KeyboardButton(text="⬅ Назад")])
    kb = ReplyKeyboardMarkup(
        keyboard=buttons, resize_keyboard=True, one_time_keyboard=True
    )

    bot_msg = await message.answer(text, reply_markup=kb)
    data = await state.get_data()
    await state.update_data(msg_ids=data["msg_ids"] + [bot_msg.message_id])
    await state.set_state(EditRecord.choosing_record)


@dp.message(F.text == "Удалить")
async def delete_start(message: Message, state: FSMContext):
    rows = get_last_rows()
    if not rows:
        return await message.answer("Нет записей для удаления.", reply_markup=main_menu)

    recent = rows[-5:]
    await state.set_data(
        {"msg_ids": [message.message_id], "rows": recent, "action": "delete"}
    )

    text = "Выберите запись для удаления:\n"
    for i, row in enumerate(recent, 1):
        text += f"{i}) {row[0]} — {row[1]} {row[2]}₽ — {row[3]}/{row[4]}\n"

    buttons = [[KeyboardButton(text=str(i))] for i in range(1, len(recent) + 1)]
    buttons.append([KeyboardButton(text="⬅ Назад")])
    kb = ReplyKeyboardMarkup(
        keyboard=buttons, resize_keyboard=True, one_time_keyboard=True
    )

    bot_msg = await message.answer(text, reply_markup=kb)
    data = await state.get_data()
    await state.update_data(msg_ids=data["msg_ids"] + [bot_msg.message_id])
    await state.set_state(EditRecord.choosing_record)


@dp.message(EditRecord.choosing_record)
async def choose_record(message: Message, state: FSMContext):
    data = await state.get_data()
    msg_ids = data["msg_ids"] + [message.message_id]

    # Назад → просто главное меню
    if message.text == "⬅ Назад":
        await cleanup_and_confirm(
            message.chat.id, msg_ids, confirm_text=None, reply_markup=main_menu
        )
        return await state.clear()

    try:
        idx = int(message.text) - 1
        rows = data["rows"]
        if not (0 <= idx < len(rows)):
            raise ValueError
    except:
        return await message.answer("Нажмите кнопку с номером записи.")

    action = data["action"]
    selected = rows[idx]
    all_rows = get_last_rows()
    real_row = len(all_rows) - len(rows) + idx + 2  # +2 из-за заголовка

    if action == "delete":
        delete_row(real_row)
        await cleanup_and_confirm(
            message.chat.id,
            msg_ids,
            confirm_text="🗑 Запись удалена.",
            reply_markup=main_menu,
        )
        return await state.clear()

    # action == "edit"
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅ Назад")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    prompt = (
        f"Текущая запись:\n"
        f"{selected[0]} — {selected[1]} {selected[2]}₽ — {selected[3]}/{selected[4]}\n\n"
        "Введите новые данные через запятую:\n"
        "Дата (ГГГГ-ММ-ДД), сумма, категория 1, категория 2\n"
        "Пример: 2025-06-14, 1500, транспорт, метро"
    )
    bot_msg = await message.answer(prompt, reply_markup=kb)

    data = await state.get_data()
    await state.update_data(
        msg_ids=msg_ids + [bot_msg.message_id], selected_row=selected, real_row=real_row
    )
    await state.set_state(EditRecord.updating_record)


@dp.message(EditRecord.updating_record)
async def apply_update(message: Message, state: FSMContext):
    data = await state.get_data()
    msg_ids = data["msg_ids"] + [message.message_id]

    # Назад → главное меню
    if message.text == "⬅ Назад":
        await cleanup_and_confirm(
            message.chat.id, msg_ids, confirm_text=None, reply_markup=main_menu
        )
        return await state.clear()

    parts = [p.strip() for p in message.text.split(",")]
    if len(parts) != 4:
        return await message.answer(
            "Ошибка формата. Введите: дата, сумма, категория1, категория2\n"
            "Пример: 2025-06-14, 1500, транспорт, метро"
        )

    date_str, amount_str, cat1, cat2 = parts
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return await message.answer("Неверный формат даты. Используй ГГГГ-ММ-ДД.")
    try:
        amount = float(amount_str)
    except ValueError:
        return await message.answer(
            "Неверный формат суммы. Введите число, например 1500."
        )

    entry_type = data["selected_row"][1]
    update_row(data["real_row"], [date_str, entry_type, amount, cat1, cat2])

    await cleanup_and_confirm(
        message.chat.id,
        msg_ids,
        confirm_text="✔ Запись обновлена.",
        reply_markup=main_menu,
    )
    await state.clear()


# ========== RUN ==========


async def main():
    dp.message.middleware(AccessMiddleware())
    dp.callback_query.middleware(AccessMiddleware())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
