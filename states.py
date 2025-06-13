from aiogram.fsm.state import State, StatesGroup


class ConfirmCategory(StatesGroup):
    ask = State()


class AddRecord(StatesGroup):
    choosing_type = State()
    entering_data = State()


class EditRecord(StatesGroup):
    choosing_record = State()
    choosing_action = State()
    updating_record = State()
