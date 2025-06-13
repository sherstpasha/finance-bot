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

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить")],
        [KeyboardButton(text="✏️ Изменить")],
    ],
    resize_keyboard=True,
)


async def cleanup_and_confirm(
    chat_id: int,
    msg_ids: list[int],
    confirm_text: str,
    reply_markup: ReplyKeyboardMarkup = None,
):
    # удаляем накопленные по списку
    for mid in msg_ids:
        try:
            await bot.delete_message(chat_id, mid)
        except:
            pass
    # отправляем одно подтверждение
    await bot.send_message(
        chat_id, confirm_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML
    )


# ========== START / MAIN MENU ==========


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


# ========== ADD RECORD ==========


@dp.message(F.text == "➕ Добавить")
async def add_start(message: Message, state: FSMContext):
    # инициализируем список msg_ids
    await state.set_data({"msg_ids": [message.message_id]})

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Доход"), KeyboardButton(text="Расход")],
            [KeyboardButton(text="⬅ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    bot_msg = await message.answer("Выберите тип записи:", reply_markup=kb)

    # читаем контекст и добавляем id бота
    data = await state.get_data()
    msg_ids = data["msg_ids"] + [bot_msg.message_id]
    await state.update_data(msg_ids=msg_ids)

    await state.set_state(AddRecord.choosing_type)


@dp.message(AddRecord.choosing_type, F.text.in_(["Доход", "Расход"]))
async def type_chosen(message: Message, state: FSMContext):
    data = await state.get_data()
    msg_ids = data["msg_ids"] + [message.message_id]
    await state.update_data(entry_type=message.text, msg_ids=msg_ids)

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅ Назад")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    bot_msg = await message.answer(
        "Введите: сумма, категория 1, категория 2", reply_markup=kb
    )

    data = await state.get_data()
    await state.update_data(msg_ids=data["msg_ids"] + [bot_msg.message_id])
    await state.set_state(AddRecord.entering_data)


@dp.message(AddRecord.entering_data)
async def process_data(message: Message, state: FSMContext):
    data = await state.get_data()
    msg_ids = data["msg_ids"] + [message.message_id]

    # кнопка Назад
    if message.text == "⬅ Назад":
        await cleanup_and_confirm(
            message.chat.id, msg_ids, "Главное меню:", reply_markup=main_menu
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

        confirm = f"✔ Запись добавлена: <b>{entry_type}</b> {amount}₽ — {cat1} / {cat2}"
        await cleanup_and_confirm(
            message.chat.id, msg_ids, confirm, reply_markup=main_menu
        )
    except:
        await message.answer("Ошибка формата. Пример: 1200, еда, кафе")
    finally:
        await state.clear()


# ========== EDIT / DELETE RECORD ==========


@dp.message(F.text == "✏️ Изменить")
async def edit_start(message: Message, state: FSMContext):
    rows = get_last_rows()
    if not rows:
        return await message.answer(
            "Нет записей для изменения.", reply_markup=main_menu
        )

    # инициализируем msg_ids и сохраняем строки
    await state.set_data({"msg_ids": [message.message_id], "rows": rows})

    text = "Выберите запись:\n"
    for i, row in enumerate(rows, 1):
        text += f"{i}) {row[0]} — {row[1]} {row[2]}₽ — {row[3]}/{row[4]}\n"

    buttons = [[KeyboardButton(text=str(i))] for i in range(1, len(rows) + 1)]
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

    if message.text == "⬅ Назад":
        await cleanup_and_confirm(
            message.chat.id, msg_ids, "Главное меню:", reply_markup=main_menu
        )
        return await state.clear()

    rows = data["rows"]
    try:
        idx = int(message.text)
        if not 1 <= idx <= len(rows):
            raise ValueError

        await state.update_data(selected_index=idx, msg_ids=msg_ids)

        kb = ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(text="✏ Редактировать"),
                    KeyboardButton(text="🗑 Удалить"),
                ],
                [KeyboardButton(text="⬅ Назад")],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        bot_msg = await message.answer("Что сделать с записью?", reply_markup=kb)

        data = await state.get_data()
        await state.update_data(msg_ids=data["msg_ids"] + [bot_msg.message_id])
        await state.set_state(EditRecord.choosing_action)
    except:
        await message.answer("Нажмите кнопку с номером записи.")


@dp.message(EditRecord.choosing_action)
async def action_selected(message: Message, state: FSMContext):
    data = await state.get_data()
    msg_ids = data["msg_ids"] + [message.message_id]

    if message.text == "⬅ Назад":
        await cleanup_and_confirm(
            message.chat.id, msg_ids, "Главное меню:", reply_markup=main_menu
        )
        return await state.clear()

    idx = data["selected_index"]
    old = data["rows"][idx - 1]

    # удаление
    if message.text == "🗑 Удалить":
        row_num = len(get_last_rows()) - idx + 2
        delete_row(row_num)
        await cleanup_and_confirm(
            message.chat.id, msg_ids, "🗑 Запись удалена.", reply_markup=main_menu
        )
        return await state.clear()

    # редактирование
    new_type = "Доход" if old[1] == "Расход" else "Расход"
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=f"🔁 Сменить тип на {new_type}"),
                KeyboardButton(text="⬅ Назад"),
            ],
        ],
        resize_keyboard=True,
    )
    prompt = (
        f"Текущая запись:\n"
        f"{old[0]} — {old[1]} {old[2]}₽ — {old[3]}/{old[4]}\n\n"
        "Введите: сумма, категория 1, категория 2"
    )
    bot_msg = await message.answer(prompt, reply_markup=kb)

    data = await state.get_data()
    await state.update_data(
        msg_ids=data["msg_ids"] + [bot_msg.message_id], edit_type=old[1]
    )
    await state.set_state(EditRecord.updating_record)


@dp.message(EditRecord.updating_record)
async def apply_update(message: Message, state: FSMContext):
    data = await state.get_data()
    msg_ids = data["msg_ids"] + [message.message_id]

    # Назад
    if message.text == "⬅ Назад":
        await cleanup_and_confirm(
            message.chat.id, msg_ids, "Главное меню:", reply_markup=main_menu
        )
        return await state.clear()

    idx = data["selected_index"] - 1
    old = data["rows"][idx]
    edit_type = data.get("edit_type", old[1])

    # смена типа
    if message.text.startswith("🔁 Сменить тип"):
        new_type = "Доход" if edit_type == "Расход" else "Расход"
        row_num = len(get_last_rows()) - idx + 1
        update_row(row_num, [old[0], new_type, old[2], old[3], old[4]])
        await cleanup_and_confirm(
            message.chat.id, msg_ids, "✅ Тип изменён.", reply_markup=main_menu
        )
        return await state.clear()

    # обновление данных
    try:
        parts = [p.strip() for p in message.text.split(",")]
        if len(parts) != 3:
            raise ValueError
        amount = float(parts[0])
        cat1, cat2 = parts[1], parts[2]
        new_row = [old[0], edit_type, amount, cat1, cat2]
        row_num = len(get_last_rows()) - idx + 1
        update_row(row_num, new_row)
        await cleanup_and_confirm(
            message.chat.id, msg_ids, "✔ Запись обновлена.", reply_markup=main_menu
        )
    except:
        await message.answer("Ошибка формата. Пример: 1500, транспорт, метро")
    finally:
        await state.clear()


# ========== RUN ==========


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
