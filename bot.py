import asyncio
import os
import json

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext

from config import BOT_TOKEN, USER_CONFIG_FILE
from google_utils import create_spreadsheet, append_row
from states import AddRecord, EditRecord
from google_utils import get_last_rows, update_row, delete_row

# Создаем бота и диспетчер
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# Главное меню
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить")],
        [KeyboardButton(text="✏️ Изменить")],
    ],
    resize_keyboard=True,
)


async def go_back_to_menu(message: Message, state: FSMContext):
    await message.answer("↩ Возврат в главное меню", reply_markup=main_menu)
    await state.clear()


# ========== START / MAIN MENU ==========


@dp.message(Command("start"))
async def start_handler(message: Message):
    if not os.path.exists(USER_CONFIG_FILE):
        sheet_url = create_spreadsheet()
        await message.answer(f"Таблица создана:\n{sheet_url}", reply_markup=main_menu)
    else:
        with open(USER_CONFIG_FILE, "r") as f:
            config = json.load(f)
        sheet_id = config["spreadsheet_id"]
        await message.answer(
            f"Таблица:\nhttps://docs.google.com/spreadsheets/d/{sheet_id}",
            reply_markup=main_menu,
        )


# ========== ADD RECORD ==========


@dp.message(F.text == "➕ Добавить")
async def add_start(message: Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Доход"), KeyboardButton(text="Расход")],
            [KeyboardButton(text="⬅ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer("Выберите тип записи:", reply_markup=kb)
    await state.set_state(AddRecord.choosing_type)


@dp.message(AddRecord.choosing_type, F.text == "⬅ Назад")
async def back_from_type_choice(message: Message, state: FSMContext):
    await go_back_to_menu(message, state)


@dp.message(AddRecord.choosing_type, F.text.in_(["Доход", "Расход"]))
async def type_chosen(message: Message, state: FSMContext):
    await state.update_data(entry_type=message.text)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅ Назад")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer("Введите: сумма, категория 1, категория 2", reply_markup=kb)
    await state.set_state(AddRecord.entering_data)


@dp.message(AddRecord.entering_data, F.text == "⬅ Назад")
async def back_from_data_entry(message: Message, state: FSMContext):
    await go_back_to_menu(message, state)


@dp.message(AddRecord.entering_data)
async def process_data(message: Message, state: FSMContext):
    user_data = await state.get_data()
    entry_type = user_data.get("entry_type")

    try:
        parts = [p.strip() for p in message.text.split(",")]
        if len(parts) != 3:
            raise ValueError("Неверный формат")

        amount = float(parts[0])
        cat1 = parts[1]
        cat2 = parts[2]

        from datetime import datetime

        row = [datetime.today().strftime("%Y-%m-%d"), entry_type, amount, cat1, cat2]
        append_row(row)

        await message.answer(
            f"✔ Запись добавлена: <b>{entry_type}</b> {amount}₽ — {cat1} / {cat2}",
            reply_markup=main_menu,
        )
        await state.clear()

    except Exception:
        await message.answer(
            "Ошибка формата. Введите: сумма, категория1, категория2\nПример: 1200, еда, кафе"
        )


# ========== EDIT / DELETE RECORD ==========


@dp.message(F.text == "✏️ Изменить")
async def edit_entry_handler(message: Message, state: FSMContext):
    rows = get_last_rows()
    if not rows:
        await message.answer("Нет доступных записей для изменения.")
        return

    text = "Выберите запись для изменения или удаления:\n"
    for i, row in enumerate(rows, 1):
        text += f"{i}) {row[0]} — {row[1]} {row[2]}₽ — {row[3]}/{row[4]}\n"

    buttons = [[KeyboardButton(text=str(i))] for i in range(1, len(rows) + 1)]
    buttons.append([KeyboardButton(text="⬅ Назад")])
    keyboard = ReplyKeyboardMarkup(
        keyboard=buttons, resize_keyboard=True, one_time_keyboard=True
    )

    await state.update_data(rows=rows)
    await message.answer(text, reply_markup=keyboard)
    await state.set_state(EditRecord.choosing_record)


@dp.message(EditRecord.choosing_record, F.text == "⬅ Назад")
async def back_from_choose_record(message: Message, state: FSMContext):
    await go_back_to_menu(message, state)


@dp.message(EditRecord.choosing_record)
async def choose_record(message: Message, state: FSMContext):
    data = await state.get_data()
    rows = data.get("rows")

    try:
        index = int(message.text)
        if not (1 <= index <= len(rows)):
            raise ValueError()

        await state.update_data(selected_index=index)
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(text="✏ Редактировать"),
                    KeyboardButton(text="🗑 Удалить"),
                    KeyboardButton(text="⬅ Назад"),
                ]
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await message.answer("Что сделать с записью?", reply_markup=kb)
        await state.set_state(EditRecord.choosing_action)

    except:
        await message.answer("Введите номер записи, нажав на одну из кнопок.")


@dp.message(EditRecord.choosing_action, F.text == "⬅ Назад")
async def back_from_choose_action(message: Message, state: FSMContext):
    await go_back_to_menu(message, state)


@dp.message(EditRecord.choosing_action, F.text == "✏ Редактировать")
async def edit_selected(message: Message, state: FSMContext):
    data = await state.get_data()
    rows = data["rows"]
    idx = data["selected_index"]
    old = rows[idx - 1]

    entry_type = old[1]
    new_type = "Доход" if entry_type == "Расход" else "Расход"

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=f"🔁 Сменить тип на {new_type}"),
                KeyboardButton(text="⬅ Назад"),
            ]
        ],
        resize_keyboard=True,
    )

    await message.answer(
        f"Текущая запись:\n{old[0]} — {entry_type} {old[2]}₽ — {old[3]}/{old[4]}\n\n"
        "Введите новые данные: сумма, категория 1, категория 2",
        reply_markup=kb,
    )
    await state.update_data(edit_type=entry_type)
    await state.set_state(EditRecord.updating_record)


@dp.message(EditRecord.choosing_action, F.text == "🗑 Удалить")
async def delete_selected(message: Message, state: FSMContext):
    data = await state.get_data()
    row_num = len(get_last_rows()) - data["selected_index"] + 2
    delete_row(row_num)
    await message.answer("🗑 Запись удалена.", reply_markup=main_menu)
    await state.clear()


@dp.message(EditRecord.updating_record, F.text == "⬅ Назад")
async def back_from_updating(message: Message, state: FSMContext):
    await go_back_to_menu(message, state)


@dp.message(EditRecord.updating_record, F.text.startswith("🔁 Сменить тип"))
async def switch_type(message: Message, state: FSMContext):
    data = await state.get_data()
    rows = data["rows"]
    idx = data["selected_index"]
    old = rows[idx - 1]
    current = data["edit_type"]
    new_type = "Доход" if current == "Расход" else "Расход"

    new_row = [old[0], new_type, old[2], old[3], old[4]]
    row_num = len(get_last_rows()) - idx + 2
    update_row(row_num, new_row)

    await message.answer(
        f"✅ Тип записи изменён на <b>{new_type}</b> и сохранён.",
        reply_markup=main_menu,
    )
    await state.clear()


@dp.message(EditRecord.updating_record)
async def apply_update(message: Message, state: FSMContext):
    data = await state.get_data()
    rows = data.get("rows")
    idx = data["selected_index"]
    old = rows[idx - 1]
    new_type = data.get("edit_type", old[1])

    try:
        parts = [p.strip() for p in message.text.split(",")]
        if len(parts) != 3:
            raise ValueError()
        amount = float(parts[0])
        cat1, cat2 = parts[1], parts[2]

        from datetime import datetime

        new_row = [old[0], new_type, amount, cat1, cat2]
        row_num = len(get_last_rows()) - idx + 2
        update_row(row_num, new_row)

        await message.answer("✔ Запись обновлена.", reply_markup=main_menu)
        await state.clear()

    except:
        await message.answer("Ошибка формата. Пример: 1500, транспорт, метро")


# ========== GLOBAL BACK HANDLER ==========


@dp.message(F.text == "⬅ Назад")
async def global_back(message: Message, state: FSMContext):
    await go_back_to_menu(message, state)


# ========== RUN ==========


async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
