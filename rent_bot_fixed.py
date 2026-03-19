import asyncio
import logging
import json
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ================== НАСТРОЙКИ ==================
logging.basicConfig(level=logging.INFO)
bot = Bot(token="8379999805:AAEZKuyfHrpCFvHvUvDOBzIXqBFDNbeFxV8")
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Файл для хранения данных
DATA_FILE = "/app/data/rent_data.json"

# 📢 ТЕСТОВЫЙ РЕЖИМ: True = минуты, False = дни
TEST_MODE = False

# ================== НАСТРОЙКИ ДОСТУПА ==================
ALLOWED_USERS = [651953211, 1901955703, 1793833215]

# ================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==================
active_rents_list = []
pending_rents_list = []   # Для списка ожидающих

# Фильтр для проверки доступа
from aiogram.filters import BaseFilter

class AllowedUsersFilter(BaseFilter):
    async def __call__(self, message: types.Message) -> bool:
        return message.from_user.id in ALLOWED_USERS

# Состояния для FSM
class RentStates(StatesGroup):
    waiting_for_track_number = State()
    waiting_for_rent_days = State()
    waiting_for_remove_confirm = State()
    waiting_for_new_rent_days = State()

# ================== РАБОТА С ДАННЫМИ ==================
def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    data = json.loads(content)
                    # Добавляем поле pending, если его нет
                    for rent in data["rents"].values():
                        if "pending" not in rent:
                            rent["pending"] = False
                    return data
                else:
                    return {"rents": {}, "blacklist": []}
        else:
            return {"rents": {}, "blacklist": []}
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка чтения JSON: {e}. Создаю новый файл")
        if os.path.exists(DATA_FILE):
            os.rename(DATA_FILE, DATA_FILE + ".bak")
        return {"rents": {}, "blacklist": []}
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        return {"rents": {}, "blacklist": []}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ================== КЛАВИАТУРЫ ==================
def get_main_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚲 Аренда")],
            [KeyboardButton(text="⏳ Ожидают решения")],
            [KeyboardButton(text="⛔ Черный список")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_rent_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Активные аренды")],
            [KeyboardButton(text="➕ Новая аренда")],
            [KeyboardButton(text="⏳ Продлить аренду")],
            [KeyboardButton(text="⏹ Остановить аренду")],
            [KeyboardButton(text="🔙 Назад")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_back_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Назад")]],
        resize_keyboard=True
    )
    return keyboard

def get_yes_no_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Да")],
            [KeyboardButton(text="❌ Нет")],
            [KeyboardButton(text="🔙 Назад")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_track_numbers_keyboard(track_numbers, prefix="select"):
    builder = InlineKeyboardBuilder()
    for number in track_numbers:
        builder.button(text=number, callback_data=f"{prefix}_{number}")
    builder.button(text="🔙 Назад", callback_data="back_to_rent")
    builder.adjust(1)
    return builder.as_markup()

def get_blacklist_keyboard(blacklist):
    builder = InlineKeyboardBuilder()
    for number in blacklist:
        builder.button(text=number, callback_data=f"blacklist_{number}")
    builder.button(text="🔙 Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_blacklist_actions_keyboard(track_number):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Убрать из ЧС", callback_data=f"remove_from_blacklist_{track_number}")
    builder.button(text="🔙 Назад", callback_data="back_to_blacklist")
    builder.adjust(1)
    return builder.as_markup()

def get_expired_notification_keyboard(track_number):
    """Кнопки в уведомлении: Продлить / Остановить / В ЧС"""
    builder = InlineKeyboardBuilder()
    builder.button(text="⏳ Продлить", callback_data=f"extend_from_notify_{track_number}")
    builder.button(text="⏹ Остановить", callback_data=f"stop_from_notify_{track_number}")
    builder.button(text="⛔ В ЧС", callback_data=f"to_blacklist_{track_number}")
    builder.adjust(3)
    return builder.as_markup()

# ================== ОБРАБОТЧИКИ ==================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.from_user.id not in ALLOWED_USERS:
        await message.answer("⛔ Доступ запрещён")
        return
    mode = "МИНУТЫ 🕐" if TEST_MODE else "ДНИ 📅"
    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\nРежим: {mode}",
        reply_markup=get_main_keyboard()
    )

@dp.message(Command("mode"))
async def show_mode(message: types.Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    mode = "МИНУТЫ 🕐 (тестовый)" if TEST_MODE else "ДНИ 📅 (рабочий)"
    await message.answer(f"Текущий режим: {mode}")

# ================== ГЛАВНОЕ МЕНЮ ==================
@dp.message(AllowedUsersFilter(), lambda message: message.text == "🚲 Аренда")
async def rent_menu(message: types.Message):
    await message.answer("Что хочешь сделать?", reply_markup=get_rent_keyboard())

@dp.message(AllowedUsersFilter(), lambda message: message.text == "⛔ Черный список")
async def show_blacklist(message: types.Message):
    data = load_data()
    if not data["blacklist"]:
        await message.answer("📭 Черный список пуст", reply_markup=get_main_keyboard())
        return
    await message.answer(
        "📋 Номера в черном списке. Нажми на номер чтобы убрать:",
        reply_markup=get_blacklist_keyboard(data["blacklist"])
    )

@dp.message(AllowedUsersFilter(), lambda message: message.text == "⏳ Ожидают решения")
async def show_pending_rents(message: types.Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    data = load_data()
    pending = [num for num, info in data["rents"].items() if info.get("pending", False)]
    if not pending:
        await message.answer("📭 Нет аренд, ожидающих решения", reply_markup=get_main_keyboard())
        return
    builder = InlineKeyboardBuilder()
    for i, number in enumerate(pending):
        builder.button(text=f"⚠️ {number}", callback_data=f"pending_{i}")
    builder.button(text="🔙 Назад", callback_data="back_to_main")
    builder.adjust(1)
    global pending_rents_list
    pending_rents_list = pending
    await message.answer("⚠️ Эти аренды требуют решения (срок истёк):", reply_markup=builder.as_markup())

@dp.message(AllowedUsersFilter(), lambda message: message.text == "🔙 Назад")
async def go_back(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        await state.clear()
    await message.answer("Выбери действие:", reply_markup=get_main_keyboard())

# ================== НОВАЯ АРЕНДА ==================
@dp.message(AllowedUsersFilter(), lambda message: message.text == "➕ Новая аренда")
async def new_rent_start(message: types.Message, state: FSMContext):
    await state.set_state(RentStates.waiting_for_track_number)
    await message.answer("🔢 Введи данные (можно с буквами и цифрами):", reply_markup=get_back_keyboard())

@dp.message(AllowedUsersFilter(), RentStates.waiting_for_track_number)
async def process_track_number(message: types.Message, state: FSMContext):
    track_number = message.text.strip()
    if not track_number:
        await message.answer("❌ Номер не может быть пустым.")
        return
    data = load_data()
    if track_number in data["blacklist"]:
        await message.answer("❌ Этот номер в черном списке!", reply_markup=get_main_keyboard())
        await state.clear()
        return
    await state.update_data(track_number=track_number)
    await state.set_state(RentStates.waiting_for_rent_days)
    await message.answer("⏳ На сколько аренда? (напиши число)", reply_markup=get_back_keyboard())

@dp.message(AllowedUsersFilter(), RentStates.waiting_for_rent_days)
async def process_rent_days(message: types.Message, state: FSMContext):
    try:
        days = int(message.text)
        if days < 1:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи число больше 0")
        return
    data_state = await state.get_data()
    track_number = data_state["track_number"]
    if TEST_MODE:
        end_date = datetime.now() + timedelta(minutes=days)
        date_str = end_date.strftime("%Y-%m-%d %H:%M")
        unit_word = "минут"
    else:
        end_date = datetime.now() + timedelta(days=days)
        date_str = end_date.strftime("%Y-%m-%d")
        unit_word = "дней"
    data = load_data()
    data["rents"][track_number] = {
        "end_date": date_str,
        "user_id": message.from_user.id,
        "username": message.from_user.username or message.from_user.first_name,
        "pending": False
    }
    save_data(data)
    time_display = end_date.strftime("%d.%m.%Y %H:%M") if TEST_MODE else end_date.strftime("%d.%m.%Y")
    await message.answer(
        f"✅ Окей, записал!\n📌 Номер: {track_number}\n⏱ Срок: {days} {unit_word}\n📅 Закончится: {time_display}",
        reply_markup=get_main_keyboard()
    )
    await state.clear()

# ================== АКТИВНЫЕ АРЕНДЫ ==================
@dp.message(AllowedUsersFilter(), lambda message: message.text == "📋 Активные аренды")
async def show_active_rents(message: types.Message):
    data = load_data()
    active = list(data["rents"].keys())
    print(f"📋 Активные аренды: {active}")
    
    if not active:
        await message.answer("📭 Нет активных аренд", reply_markup=get_rent_keyboard())
        return
    
    builder = InlineKeyboardBuilder()
    for i, number in enumerate(active):
        builder.button(text=number, callback_data=f"view_{i}")
    builder.button(text="🔙 Назад", callback_data="back_to_rent")
    builder.adjust(1)
    
    global active_rents_list
    active_rents_list = active
    
    await message.answer("📋 Список активных аренд:", reply_markup=builder.as_markup())

@dp.callback_query(AllowedUsersFilter(), lambda c: c.data.startswith("view_"))
async def view_rent_details(callback: types.CallbackQuery, state: FSMContext):
    print(f"🔍 view_rent_details вызван с callback_data: {callback.data}")
    
    # Сначала объявляем глобальные переменные!
    global active_rents_list
    
    index = int(callback.data.split("_")[1])
    print(f"🔍 Индекс: {index}")
    
    print(f"🔍 active_rents_list: {active_rents_list}")
    print(f"🔍 Длина списка: {len(active_rents_list)}")
    
    if index >= len(active_rents_list):
        print(f"❌ Ошибка: индекс {index} вне диапазона (макс: {len(active_rents_list)-1})")
        await callback.message.answer("❌ Ошибка: номер не найден")
        await callback.answer()
        return
    
    track_number = active_rents_list[index]
    print(f"✅ Найден номер: {track_number}")
    
    data = load_data()
    rent_info = data["rents"].get(track_number, {})
    end_date = rent_info.get("end_date", "неизвестно")
    
    if " " in end_date:
        end_date_formatted = datetime.strptime(end_date, "%Y-%m-%d %H:%M").strftime("%d.%m.%Y %H:%M")
    else:
        end_date_formatted = datetime.strptime(end_date, "%Y-%m-%d").strftime("%d.%m.%Y")
    
    builder = InlineKeyboardBuilder()
    builder.button(text="⏳ Продлить", callback_data=f"extend_{index}")
    builder.button(text="⏹ Остановить", callback_data=f"stop_{index}")
    builder.button(text="⛔ В ЧС", callback_data=f"to_blacklist_from_view_{index}")
    builder.button(text="🔙 Назад к списку", callback_data="back_to_active")
    builder.adjust(2)
    
    await callback.message.delete()
    await callback.message.answer(
        f"📌 Номер: {track_number}\n⏱ Заканчивается: {end_date_formatted}\n\nВыбери действие:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# ================== НОВЫЙ ОБРАБОТЧИК ДЛЯ КНОПКИ "В ЧС" ИЗ ПРОСМОТРА ==================
@dp.callback_query(AllowedUsersFilter(), lambda c: c.data.startswith("to_blacklist_from_view_"))
async def add_to_blacklist_from_view(callback: types.CallbackQuery):
    """Добавить номер в черный список из просмотра аренды"""
    print(f"🔍 Получен запрос на добавление в ЧС: {callback.data}")
    
    # Получаем индекс из callback_data
    index = int(callback.data.replace("to_blacklist_from_view_", ""))
    
    # Объявляем глобальную переменную только один раз!
    global active_rents_list
    
    # Проверяем, что индекс в пределах списка
    if index >= len(active_rents_list):
        await callback.message.answer("❌ Ошибка: номер не найден")
        await callback.answer()
        return
    
    # Получаем реальный номер по индексу
    track_number = active_rents_list[index]
    print(f"✅ Добавляем в ЧС номер: {track_number}")
    
    # Загружаем данные
    data = load_data()
    
    # Удаляем из аренд, если номер там есть
    if track_number in data["rents"]:
        del data["rents"][track_number]
        print(f"✅ Номер {track_number} удалён из аренд")
    
    # Добавляем в ЧС, если ещё не там
    if track_number not in data["blacklist"]:
        data["blacklist"].append(track_number)
        print(f"✅ Номер {track_number} добавлен в ЧС")
    
    # Сохраняем изменения
    save_data(data)
    
    # Обновляем глобальный список активных аренд
    active_rents_list = list(data["rents"].keys())
    
    # Отвечаем пользователю
    await callback.message.delete()
    await callback.message.answer(
        f"⛔ Номер {track_number} добавлен в черный список",
        reply_markup=get_main_keyboard()
    )
    await callback.answer()

@dp.callback_query(AllowedUsersFilter(), lambda c: c.data == "back_to_active")
async def back_to_active_list(callback: types.CallbackQuery):
    data = load_data()
    active = list(data["rents"].keys())
    if not active:
        await callback.message.delete()
        await callback.message.answer("📭 Нет активных аренд", reply_markup=get_rent_keyboard())
        await callback.answer()
        return
    builder = InlineKeyboardBuilder()
    for i, number in enumerate(active):
        builder.button(text=number, callback_data=f"view_{i}")
    builder.button(text="🔙 Назад", callback_data="back_to_rent")
    builder.adjust(1)
    global active_rents_list
    active_rents_list = active
    await callback.message.delete()
    await callback.message.answer("📋 Список активных аренд:", reply_markup=builder.as_markup())
    await callback.answer()

# ================== ПРОДЛИТЬ АРЕНДУ ==================
@dp.message(AllowedUsersFilter(), lambda message: message.text == "⏳ Продлить аренду")
async def extend_rent_start(message: types.Message):
    data = load_data()
    active = list(data["rents"].keys())
    if not active:
        await message.answer("📭 Нет активных аренд", reply_markup=get_rent_keyboard())
        return
    await message.answer("📋 Выбери номер для продления:", reply_markup=get_track_numbers_keyboard(active, "extend"))

# ================== ПРОДЛЕНИЕ ИЗ РАЗНЫХ МЕСТ ==================

@dp.callback_query(AllowedUsersFilter(), lambda c: c.data.startswith("extend_from_notify_"))
async def extend_from_notification(callback: types.CallbackQuery, state: FSMContext):
    """Продление из уведомления (номер прямо в callback)"""
    print(f"🔍 extend_from_notify: {callback.data}")
    
    # Получаем номер напрямую (не индекс!)
    track_number = callback.data.replace("extend_from_notify_", "")
    print(f"✅ Номер для продления: {track_number}")
    
    # Проверяем, существует ли такая аренда
    data = load_data()
    if track_number not in data["rents"]:
        await callback.message.answer("❌ Ошибка: аренда не найдена")
        await callback.answer()
        return
    
    await state.update_data(track_number=track_number)
    await state.set_state(RentStates.waiting_for_new_rent_days)
    
    await callback.message.delete()
    await callback.message.answer(
        f"📌 Номер {track_number}\n⏳ На сколько продлить? (напиши число)",
        reply_markup=get_back_keyboard()
    )
    await callback.answer()

@dp.callback_query(AllowedUsersFilter(), lambda c: c.data.startswith("extend_") and not c.data.startswith("extend_pending_") and not c.data.startswith("extend_from_notify_"))
async def extend_rent_callback(callback: types.CallbackQuery, state: FSMContext):
    """Продление из обычного меню (по индексу)"""
    print(f"🔍 extend_rent: {callback.data}")
    
    index = int(callback.data.split("_")[1])
    global active_rents_list
    
    if index >= len(active_rents_list):
        await callback.message.answer("❌ Ошибка: номер не найден")
        await callback.answer()
        return
    
    track_number = active_rents_list[index]
    print(f"✅ Номер для продления: {track_number}")
    
    await state.update_data(track_number=track_number)
    await state.set_state(RentStates.waiting_for_new_rent_days)
    
    await callback.message.delete()
    await callback.message.answer(
        f"📌 Номер {track_number}\n⏳ На сколько продлить? (напиши число)",
        reply_markup=get_back_keyboard()
    )
    await callback.answer()

@dp.callback_query(AllowedUsersFilter(), lambda c: c.data.startswith("extend_pending_"))
async def extend_pending_callback(callback: types.CallbackQuery, state: FSMContext):
    """Продление из списка ожидающих (по индексу)"""
    print(f"🔍 extend_pending: {callback.data}")
    
    index = int(callback.data.replace("extend_pending_", ""))
    global pending_rents_list
    
    if index >= len(pending_rents_list):
        await callback.message.answer("❌ Ошибка: номер не найден")
        await callback.answer()
        return
    
    track_number = pending_rents_list[index]
    print(f"✅ Номер для продления из ожидающих: {track_number}")
    
    await state.update_data(track_number=track_number)
    await state.set_state(RentStates.waiting_for_new_rent_days)
    
    await callback.message.delete()
    await callback.message.answer(
        f"📌 Номер {track_number}\n⏳ На сколько продлить? (напиши число)",
        reply_markup=get_back_keyboard()
    )
    await callback.answer()

@dp.message(AllowedUsersFilter(), RentStates.waiting_for_new_rent_days)
async def process_extend_days(message: types.Message, state: FSMContext):
    try:
        days = int(message.text)
        if days < 1:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи число больше 0")
        return
    data_state = await state.get_data()
    track_number = data_state["track_number"]
    data = load_data()
    if track_number not in data["rents"]:
        await message.answer("❌ Ошибка: аренда не найдена")
        await state.clear()
        return
    if TEST_MODE:
        current_end = datetime.strptime(data["rents"][track_number]["end_date"], "%Y-%m-%d %H:%M")
        new_end = current_end + timedelta(minutes=days)
        data["rents"][track_number]["end_date"] = new_end.strftime("%Y-%m-%d %H:%M")
        time_display = new_end.strftime("%d.%m.%Y %H:%M")
        unit_word = "минут"
    else:
        current_end = datetime.strptime(data["rents"][track_number]["end_date"], "%Y-%m-%d")
        new_end = current_end + timedelta(days=days)
        data["rents"][track_number]["end_date"] = new_end.strftime("%Y-%m-%d")
        time_display = new_end.strftime("%d.%m.%Y")
        unit_word = "дней"
    data["rents"][track_number]["username"] = message.from_user.username or message.from_user.first_name
    data["rents"][track_number]["pending"] = False   # снимаем флаг ожидания
    save_data(data)
    await message.answer(
        f"✅ Окей, продлил!\n📌 Номер: {track_number}\n⏱ Продление: {days} {unit_word}\n📅 Новый срок до: {time_display}",
        reply_markup=get_main_keyboard()
    )
    await state.clear()

# ================== ОСТАНОВИТЬ АРЕНДУ ==================
@dp.message(AllowedUsersFilter(), lambda message: message.text == "⏹ Остановить аренду")
async def stop_rent_start(message: types.Message):
    data = load_data()
    active = list(data["rents"].keys())
    if not active:
        await message.answer("📭 Нет активных аренд", reply_markup=get_rent_keyboard())
        return
    builder = InlineKeyboardBuilder()
    for i, number in enumerate(active):
        builder.button(text=number, callback_data=f"stop_{i}")
    builder.button(text="🔙 Назад", callback_data="back_to_rent")
    builder.adjust(1)
    global active_rents_list
    active_rents_list = active
    await message.answer("📋 Выбери номер для остановки:", reply_markup=builder.as_markup())

@dp.callback_query(AllowedUsersFilter(), lambda c: c.data.startswith("stop_") and not c.data.startswith("stop_pending_"))
async def stop_rent_confirm(callback: types.CallbackQuery, state: FSMContext):
    index = int(callback.data.split("_")[1])
    global active_rents_list
    if index >= len(active_rents_list):
        await callback.message.answer("❌ Ошибка: номер не найден")
        await callback.answer()
        return
    track_number = active_rents_list[index]
    await state.update_data(track_number=track_number)
    await state.set_state(RentStates.waiting_for_remove_confirm)
    await callback.message.delete()
    await callback.message.answer(
        f"❓ Прекратить аренду номера {track_number}?",
        reply_markup=get_yes_no_keyboard()
    )
    await callback.answer()

@dp.message(AllowedUsersFilter(), RentStates.waiting_for_remove_confirm)
async def process_stop_confirm(message: types.Message, state: FSMContext):
    if message.text == "✅ Да":
        data_state = await state.get_data()
        track_number = data_state["track_number"]
        data = load_data()
        if track_number in data["rents"]:
            del data["rents"][track_number]
            save_data(data)
            await message.answer(f"✅ Аренда номера {track_number} прекращена")
        else:
            await message.answer("❌ Ошибка: номер не найден")
    elif message.text == "❌ Нет":
        await message.answer("⏺ Отменено")
    else:
        await message.answer("❌ Используй кнопки Да/Нет")
        return
    await state.clear()
    await message.answer("Выбери действие:", reply_markup=get_main_keyboard())

# ================== ЧЕРНЫЙ СПИСОК ==================
@dp.callback_query(AllowedUsersFilter(), lambda c: c.data.startswith("blacklist_"))
async def blacklist_item_selected(callback: types.CallbackQuery):
    track_number = callback.data.split("_")[1]
    await callback.message.delete()
    await callback.message.answer(
        f"📌 Номер {track_number} в черном списке.\nЧто делаем?",
        reply_markup=get_blacklist_actions_keyboard(track_number)
    )
    await callback.answer()

@dp.callback_query(AllowedUsersFilter(), lambda c: c.data.startswith("remove_from_blacklist_"))
async def remove_from_blacklist(callback: types.CallbackQuery, state: FSMContext):
    track_number = callback.data.replace("remove_from_blacklist_", "")
    data = load_data()
    if track_number in data["blacklist"]:
        data["blacklist"].remove(track_number)
        save_data(data)
        await state.update_data(track_number=track_number)
        await state.set_state(RentStates.waiting_for_rent_days)
        await callback.message.delete()
        await callback.message.answer(
            f"✅ Номер {track_number} убран из ЧС\n⏳ На сколько аренда? (напиши число)",
            reply_markup=get_back_keyboard()
        )
    await callback.answer()


@dp.callback_query(AllowedUsersFilter(), lambda c: c.data.startswith("stop_from_notify_"))
async def stop_from_notification(callback: types.CallbackQuery):
    # Получаем номер из callback_data
    prefix = "stop_from_notify_"
    track_number = callback.data[len(prefix):]  # более надёжный способ
    print(f"🔍 Получен stop для номера: {track_number}")  # для отладки
    
    data = load_data()
    if track_number in data["rents"]:
        del data["rents"][track_number]
        save_data(data)
        await callback.message.delete()
        await callback.message.answer(f"✅ Аренда {track_number} остановлена", reply_markup=get_main_keyboard())
        print(f"✅ Аренда {track_number} успешно остановлена")
    else:
        await callback.message.answer("❌ Ошибка: аренда не найдена")
        print(f"❌ Аренда {track_number} не найдена в данных")
    await callback.answer()

@dp.callback_query(AllowedUsersFilter(), lambda c: c.data.startswith("to_blacklist_"))
async def add_to_blacklist(callback: types.CallbackQuery):
    track_number = callback.data.replace("to_blacklist_", "")
    data = load_data()
    if track_number in data["rents"]:
        del data["rents"][track_number]
    if track_number not in data["blacklist"]:
        data["blacklist"].append(track_number)
        save_data(data)
    await callback.message.delete()
    await callback.message.answer(f"⛔ Номер {track_number} добавлен в черный список", reply_markup=get_main_keyboard())
    await callback.answer()

# ================== ОБРАБОТЧИКИ ДЛЯ PENDING ==================
@dp.callback_query(AllowedUsersFilter(), lambda c: c.data.startswith("extend_pending_"))
async def extend_pending_callback(callback: types.CallbackQuery, state: FSMContext):
    """Продление из списка ожидающих"""
    print(f"🔍 extend_pending_callback вызван с {callback.data}")
    
    index = int(callback.data.replace("extend_pending_", ""))
    global pending_rents_list
    
    if index >= len(pending_rents_list):
        await callback.message.answer("❌ Ошибка: номер не найден")
        await callback.answer()
        return
    
    track_number = pending_rents_list[index]
    print(f"✅ Продлеваем из ожидающих номер: {track_number}")
    
    await state.update_data(track_number=track_number)
    await state.set_state(RentStates.waiting_for_new_rent_days)
    
    await callback.message.delete()
    await callback.message.answer(
        f"📌 Номер {track_number}\n⏳ На сколько продлить? (напиши число)",
        reply_markup=get_back_keyboard()
    )
    await callback.answer()

@dp.callback_query(AllowedUsersFilter(), lambda c: c.data.startswith("stop_pending_"))
async def stop_pending_callback(callback: types.CallbackQuery, state: FSMContext):
    """Остановка из списка ожидающих"""
    index = int(callback.data.replace("stop_pending_", ""))
    global pending_rents_list
    if index >= len(pending_rents_list):
        await callback.message.answer("❌ Ошибка: номер не найден")
        await callback.answer()
        return
    
    track_number = pending_rents_list[index]
    await state.update_data(track_number=track_number)
    await state.set_state(RentStates.waiting_for_remove_confirm)
    
    await callback.message.delete()
    await callback.message.answer(
        f"❓ Прекратить аренду номера {track_number}?",
        reply_markup=get_yes_no_keyboard()
    )
    await callback.answer()

@dp.callback_query(AllowedUsersFilter(), lambda c: c.data.startswith("blacklist_pending_"))
async def blacklist_pending_callback(callback: types.CallbackQuery):
    """Добавление в ЧС из списка ожидающих"""
    index = int(callback.data.replace("blacklist_pending_", ""))
    global pending_rents_list
    if index >= len(pending_rents_list):
        await callback.message.answer("❌ Ошибка: номер не найден")
        await callback.answer()
        return
    
    track_number = pending_rents_list[index]
    data = load_data()
    
    # Удаляем из аренд
    if track_number in data["rents"]:
        del data["rents"][track_number]
    
    # Добавляем в ЧС
    if track_number not in data["blacklist"]:
        data["blacklist"].append(track_number)
    
    save_data(data)
    
    await callback.message.delete()
    await callback.message.answer(
        f"⛔ Номер {track_number} добавлен в черный список",
        reply_markup=get_main_keyboard()
    )
    await callback.answer()

@dp.callback_query(AllowedUsersFilter(), lambda c: c.data.startswith("pending_"))
async def pending_rent_details(callback: types.CallbackQuery, state: FSMContext):
    index = int(callback.data.split("_")[1])
    global pending_rents_list
    if index >= len(pending_rents_list):
        await callback.message.answer("❌ Ошибка: номер не найден")
        await callback.answer()
        return
    track_number = pending_rents_list[index]
    data = load_data()
    rent_info = data["rents"].get(track_number, {})
    end_date = rent_info.get("end_date", "неизвестно")
    builder = InlineKeyboardBuilder()
    builder.button(text="⏳ Продлить", callback_data=f"extend_pending_{index}")
    builder.button(text="⏹ Остановить", callback_data=f"stop_pending_{index}")
    builder.button(text="⛔ В ЧС", callback_data=f"blacklist_pending_{index}")
    builder.button(text="✅ Уже решено", callback_data=f"resolve_pending_{index}")
    builder.button(text="🔙 Назад", callback_data="back_to_pending")
    builder.adjust(2)
    await callback.message.delete()
    await callback.message.answer(
        f"⚠️ Номер: {track_number}\n⏱ Срок истёк: {end_date}\n\nВыбери действие:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@dp.callback_query(AllowedUsersFilter(), lambda c: c.data.startswith("resolve_pending_"))
async def resolve_pending(callback: types.CallbackQuery):
    index = int(callback.data.replace("resolve_pending_", ""))
    global pending_rents_list
    if index >= len(pending_rents_list):
        await callback.message.answer("❌ Ошибка: номер не найден")
        await callback.answer()
        return
    track_number = pending_rents_list[index]
    data = load_data()
    if track_number in data["rents"]:
        data["rents"][track_number]["pending"] = False
        save_data(data)
    await callback.message.delete()
    await callback.message.answer(f"✅ Аренда {track_number} убрана из списка ожидающих", reply_markup=get_main_keyboard())
    await callback.answer()

# ================== КНОПКИ НАЗАД ==================
@dp.callback_query(AllowedUsersFilter(), lambda c: c.data == "back_to_rent")
async def back_to_rent_menu(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("Что хочешь сделать?", reply_markup=get_rent_keyboard())
    await callback.answer()

@dp.callback_query(AllowedUsersFilter(), lambda c: c.data == "back_to_main")
async def back_to_main_menu(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("Выбери действие:", reply_markup=get_main_keyboard())
    await callback.answer()

@dp.callback_query(AllowedUsersFilter(), lambda c: c.data == "back_to_blacklist")
async def back_to_blacklist(callback: types.CallbackQuery):
    data = load_data()
    await callback.message.delete()
    if data["blacklist"]:
        await callback.message.answer("📋 Номера в черном списке:", reply_markup=get_blacklist_keyboard(data["blacklist"]))
    else:
        await callback.message.answer("📭 Черный список пуст", reply_markup=get_main_keyboard())
    await callback.answer()

@dp.callback_query(AllowedUsersFilter(), lambda c: c.data == "back_to_pending")
async def back_to_pending(callback: types.CallbackQuery):
    data = load_data()
    pending = [num for num, info in data["rents"].items() if info.get("pending", False)]
    if not pending:
        await callback.message.delete()
        await callback.message.answer("📭 Нет аренд, ожидающих решения", reply_markup=get_main_keyboard())
        await callback.answer()
        return
    builder = InlineKeyboardBuilder()
    for i, number in enumerate(pending):
        builder.button(text=f"⚠️ {number}", callback_data=f"pending_{i}")
    builder.button(text="🔙 Назад", callback_data="back_to_main")
    builder.adjust(1)
    global pending_rents_list
    pending_rents_list = pending
    await callback.message.delete()
    await callback.message.answer("⚠️ Эти аренды требуют решения:", reply_markup=builder.as_markup())
    await callback.answer()

# ================== УВЕДОМЛЕНИЯ ==================
async def check_expired_rents():
    while True:
        try:
            now_msk = datetime.utcnow() + timedelta(hours=3)
            if now_msk.hour == 20 and 0 <= now_msk.minute <= 1:
                print(f"⏰ {now_msk.strftime('%d.%m.%Y %H:%M')} - Проверка аренд")
                data = load_data()
                today = now_msk.date()
                for track_number, rent_info in data["rents"].items():
                    try:
                        date_str = rent_info["end_date"].strip()
                        if " " in date_str:
                            end_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
                            end_date_only = end_date.date()
                        else:
                            end_date_only = datetime.strptime(date_str, "%Y-%m-%d").date()
                        if end_date_only == today:
                            print(f"📢 Аренда {track_number} заканчивается сегодня")
                            data["rents"][track_number]["pending"] = True
                            sent_count = 0
                            for user_id in ALLOWED_USERS:
                                try:
                                    await bot.send_message(
                                        user_id,
                                        f"⚠️ НАПОМИНАНИЕ В 20:00!\n"
                                        f"📌 Номер: {track_number}\n"
                                        f"⏱ СРОК АРЕНДЫ ИСТЕК!\n\n"
                                        f"Этот номер требует решения.\n"
                                        f"Зайди в меню '⏳ Ожидают решения'",
                                        reply_markup=get_expired_notification_keyboard(track_number)
                                    )
                                    sent_count += 1
                                except Exception as e:
                                    print(f"❌ Не удалось отправить пользователю {user_id}: {e}")
                            print(f"✅ Уведомление о {track_number} отправлено {sent_count} пользователям")
                    except Exception as e:
                        print(f"❌ Ошибка обработки {track_number}: {e}")
                        continue
                save_data(data)
                await asyncio.sleep(60)
            await asyncio.sleep(60)
        except Exception as e:
            logging.error(f"Ошибка в проверке уведомлений: {e}")
            await asyncio.sleep(60)

# ================== ЗАПУСК ==================
async def main():
    asyncio.create_task(check_expired_rents())
    mode = "ТЕСТОВЫЙ (минуты)" if TEST_MODE else "РАБОЧИЙ (дни)"
    print(f"✅ Бот запущен!\n📊 Режим: {mode}\n👥 Доступ разрешен для {len(ALLOWED_USERS)} пользователей")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())