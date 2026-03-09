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
DATA_FILE = "rent_data.json"

# 📢 ТЕСТОВЫЙ РЕЖИМ: True = минуты, False = дни
TEST_MODE = False

# ================== НАСТРОЙКИ ДОСТУПА ==================
ALLOWED_USERS = [651953211, 1901955703, 1793833215]

# ================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==================
active_rents_list = []  # Для хранения списка активных аренд
extend_rents_list = []  # Для продления

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
    """Загружает данные из JSON файла"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "rents": {},
        "blacklist": []
    }

def save_data(data):
    """Сохраняет данные в JSON файл"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ================== КЛАВИАТУРЫ ==================
def get_main_keyboard():
    """Главное меню"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚲 Аренда")],
            [KeyboardButton(text="⛔ Черный список")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_rent_keyboard():
    """Меню аренды (с новой кнопкой Активные аренды)"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Активные аренды")],  # Новая кнопка!
            [KeyboardButton(text="➕ Новая аренда")],
            [KeyboardButton(text="⏳ Продлить аренду")],
            [KeyboardButton(text="⏹ Остановить аренду")],
            [KeyboardButton(text="🔙 Назад")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_back_keyboard():
    """Кнопка назад"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Назад")]],
        resize_keyboard=True
    )
    return keyboard

def get_yes_no_keyboard():
    """Кнопки Да/Нет"""
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
    """Создает инлайн клавиатуру со списком номеров"""
    builder = InlineKeyboardBuilder()
    for number in track_numbers:
        builder.button(text=number, callback_data=f"{prefix}_{number}")
    builder.button(text="🔙 Назад", callback_data="back_to_rent")
    builder.adjust(1)
    return builder.as_markup()

def get_blacklist_keyboard(blacklist):
    """Клавиатура для черного списка"""
    builder = InlineKeyboardBuilder()
    for number in blacklist:
        builder.button(text=number, callback_data=f"blacklist_{number}")
    builder.button(text="🔙 Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_blacklist_actions_keyboard(track_number):
    """Кнопки для номера в черном списке"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Убрать из ЧС", callback_data=f"remove_from_blacklist_{track_number}")
    builder.button(text="🔙 Назад", callback_data="back_to_blacklist")
    builder.adjust(1)
    return builder.as_markup()

def get_expired_notification_keyboard(track_number):
    """Кнопки в уведомлении об истечении срока"""
    builder = InlineKeyboardBuilder()
    builder.button(text="⏳ Продлить", callback_data=f"extend_from_notify_{track_number}")
    builder.button(text="⛔ В ЧС", callback_data=f"to_blacklist_{track_number}")
    builder.adjust(2)
    return builder.as_markup()

# ================== ОБРАБОТЧИКИ ==================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    if message.from_user.id not in ALLOWED_USERS:
        await message.answer(
            "⛔ Извини, этот бот только для ограниченного круга лиц.\n"
            "Если считаешь, что ошибка — свяжись с администратором."
        )
        return
    
    mode = "МИНУТЫ 🕐" if TEST_MODE else "ДНИ 📅"
    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n"
        f"Режим: {mode}\n\n"
        f"Выбери действие:",
        reply_markup=get_main_keyboard()
    )

@dp.message(Command("mode"))
async def show_mode(message: types.Message):
    """Показать текущий режим"""
    if message.from_user.id not in ALLOWED_USERS:
        return
    
    mode = "МИНУТЫ 🕐 (тестовый)" if TEST_MODE else "ДНИ 📅 (рабочий)"
    await message.answer(f"Текущий режим: {mode}")

# ================== ГЛАВНОЕ МЕНЮ ==================
@dp.message(AllowedUsersFilter(), lambda message: message.text == "🚲 Аренда")
async def rent_menu(message: types.Message):
    """Меню аренды"""
    await message.answer("Что хочешь сделать?", reply_markup=get_rent_keyboard())

@dp.message(AllowedUsersFilter(), lambda message: message.text == "⛔ Черный список")
async def show_blacklist(message: types.Message):
    """Показать черный список"""
    data = load_data()
    if not data["blacklist"]:
        await message.answer("📭 Черный список пуст", reply_markup=get_main_keyboard())
        return
    
    await message.answer(
        "📋 Номера в черном списке. Нажми на номер чтобы убрать:",
        reply_markup=get_blacklist_keyboard(data["blacklist"])
    )

@dp.message(AllowedUsersFilter(), lambda message: message.text == "🔙 Назад")
async def go_back(message: types.Message, state: FSMContext):
    """Обработчик кнопки назад"""
    current_state = await state.get_state()
    if current_state:
        await state.clear()
    await message.answer("Выбери действие:", reply_markup=get_main_keyboard())

# ================== НОВАЯ АРЕНДА ==================
@dp.message(AllowedUsersFilter(), lambda message: message.text == "➕ Новая аренда")
async def new_rent_start(message: types.Message, state: FSMContext):
    """Начать новую аренду"""
    await state.set_state(RentStates.waiting_for_track_number)
    await message.answer(
        "🔢 Введи данные (можно с буквами и цифрами):",
        reply_markup=get_back_keyboard()
    )

@dp.message(AllowedUsersFilter(), RentStates.waiting_for_track_number)
async def process_track_number(message: types.Message, state: FSMContext):
    """Получаем трек-номер"""
    track_number = message.text.strip()
    
    if not track_number:
        await message.answer("❌ Номер не может быть пустым. Введи трек-номер:")
        return
    
    data = load_data()
    if track_number in data["blacklist"]:
        await message.answer(
            "❌ Этот номер в черном списке!",
            reply_markup=get_main_keyboard()
        )
        await state.clear()
        return
    
    await state.update_data(track_number=track_number)
    await state.set_state(RentStates.waiting_for_rent_days)
    
    await message.answer(
        "⏳ На сколько аренда? (напиши число)",
        reply_markup=get_back_keyboard()
    )

@dp.message(AllowedUsersFilter(), RentStates.waiting_for_rent_days)
async def process_rent_days(message: types.Message, state: FSMContext):
    """Получаем срок аренды и сохраняем"""
    try:
        days = int(message.text)
        if days < 1:
            raise ValueError
    except ValueError:
        await message.answer("❌ Пожалуйста, введи число больше 0")
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
        "username": message.from_user.username or message.from_user.first_name  # ← вот это добавить!
    }
    save_data(data)
    
    time_display = end_date.strftime("%d.%m.%Y %H:%M") if TEST_MODE else end_date.strftime("%d.%m.%Y")
    
    await message.answer(
        f"✅ Окей, записал!\n"
        f"📌 Номер: {track_number}\n"
        f"⏱ Срок: {days} {unit_word}\n"
        f"📅 Закончится: {time_display}",
        reply_markup=get_main_keyboard()
    )
    await state.clear()

# ================== АКТИВНЫЕ АРЕНДЫ (НОВЫЕ ФУНКЦИИ) ==================
@dp.message(AllowedUsersFilter(), lambda message: message.text == "📋 Активные аренды")
async def show_active_rents(message: types.Message):
    """Показать список активных аренд"""
    if message.from_user.id not in ALLOWED_USERS:
        return
    
    data = load_data()
    active_rents = list(data["rents"].keys())
    
    if not active_rents:
        await message.answer("📭 Нет активных аренд", reply_markup=get_rent_keyboard())
        return
    
    builder = InlineKeyboardBuilder()
    for i, number in enumerate(active_rents):
        builder.button(text=number, callback_data=f"view_{i}")
    builder.button(text="🔙 Назад", callback_data="back_to_rent")
    builder.adjust(1)
    
    global active_rents_list
    active_rents_list = active_rents
    
    await message.answer(
        "📋 Список активных аренд. Нажми на номер для действий:",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(AllowedUsersFilter(), lambda c: c.data.startswith("view_"))
async def view_rent_details(callback: types.CallbackQuery, state: FSMContext):
    """Показать детали аренды и действия"""
    if callback.from_user.id not in ALLOWED_USERS:
        await callback.answer()
        return
    
    index = int(callback.data.split("_")[1])
    
    global active_rents_list
    if index >= len(active_rents_list):
        await callback.message.answer("❌ Ошибка: номер не найден")
        await callback.answer()
        return
    
    track_number = active_rents_list[index]
    
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
        f"📌 Номер: {track_number}\n"
        f"⏱ Заканчивается: {end_date_formatted}\n\n"
        f"Выбери действие:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@dp.callback_query(AllowedUsersFilter(), lambda c: c.data.startswith("to_blacklist_from_view_"))
async def add_to_blacklist_from_view(callback: types.CallbackQuery):
    """Добавить номер в черный список из просмотра аренды"""
    if callback.from_user.id not in ALLOWED_USERS:
        await callback.answer()
        return
    
    index = int(callback.data.replace("to_blacklist_from_view_", ""))
    
    global active_rents_list
    if index >= len(active_rents_list):
        await callback.message.answer("❌ Ошибка: номер не найден")
        await callback.answer()
        return
    
    track_number = active_rents_list[index]
    
    data = load_data()
    if track_number in data["rents"]:
        del data["rents"][track_number]
    if track_number not in data["blacklist"]:
        data["blacklist"].append(track_number)
        save_data(data)
    
    await callback.message.delete()
    await callback.message.answer(
        f"⛔ Номер {track_number} добавлен в черный список",
        reply_markup=get_rent_keyboard()
    )
    await callback.answer()

@dp.callback_query(AllowedUsersFilter(), lambda c: c.data == "back_to_active")
async def back_to_active_list(callback: types.CallbackQuery):
    """Вернуться к списку активных аренд"""
    if callback.from_user.id not in ALLOWED_USERS:
        await callback.answer()
        return
    
    data = load_data()
    active_rents = list(data["rents"].keys())
    
    if not active_rents:
        await callback.message.delete()
        await callback.message.answer("📭 Нет активных аренд", reply_markup=get_rent_keyboard())
        await callback.answer()
        return
    
    builder = InlineKeyboardBuilder()
    for i, number in enumerate(active_rents):
        builder.button(text=number, callback_data=f"view_{i}")
    builder.button(text="🔙 Назад", callback_data="back_to_rent")
    builder.adjust(1)
    
    global active_rents_list
    active_rents_list = active_rents
    
    await callback.message.delete()
    await callback.message.answer(
        "📋 Список активных аренд:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# ================== ПРОДЛИТЬ АРЕНДУ ==================
@dp.message(AllowedUsersFilter(), lambda message: message.text == "⏳ Продлить аренду")
async def extend_rent_start(message: types.Message):
    """Показать список активных аренд для продления"""
    data = load_data()
    active_rents = list(data["rents"].keys())
    
    if not active_rents:
        await message.answer("📭 Нет активных аренд", reply_markup=get_rent_keyboard())
        return
    
    await message.answer(
        "📋 Выбери номер для продления:",
        reply_markup=get_track_numbers_keyboard(active_rents, "extend")
    )

@dp.callback_query(AllowedUsersFilter(), lambda c: c.data.startswith("extend_"))
async def extend_rent_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора номера для продления"""
    track_number = callback.data.split("_")[1]
    
    await state.update_data(track_number=track_number)
    await state.set_state(RentStates.waiting_for_new_rent_days)
    
    await callback.message.delete()
    await callback.message.answer(
        f"📌 Номер {track_number}\n"
        f"⏳ На сколько продлить? (напиши число)",
        reply_markup=get_back_keyboard()
    )
    await callback.answer()

@dp.message(AllowedUsersFilter(), RentStates.waiting_for_new_rent_days)
async def process_extend_days(message: types.Message, state: FSMContext):
    """Обработка срока продления"""
    try:
        days = int(message.text)
        if days < 1:
            raise ValueError
    except ValueError:
        await message.answer("❌ Пожалуйста, введи число больше 0")
        return
    
    data_state = await state.get_data()
    track_number = data_state["track_number"]
    
    # Обновляем дату окончания
    data = load_data()
    
    if TEST_MODE:
        # Для минут
        current_end = datetime.strptime(data["rents"][track_number]["end_date"], "%Y-%m-%d %H:%M")
        new_end = current_end + timedelta(minutes=days)
        data["rents"][track_number]["end_date"] = new_end.strftime("%Y-%m-%d %H:%M")
        time_display = new_end.strftime("%d.%m.%Y %H:%M")
        unit_word = "минут"
    else:
        # Для дней
        current_end = datetime.strptime(data["rents"][track_number]["end_date"], "%Y-%m-%d")
        new_end = current_end + timedelta(days=days)
        data["rents"][track_number]["end_date"] = new_end.strftime("%Y-%m-%d")
        time_display = new_end.strftime("%d.%m.%Y")
        unit_word = "дней"
    
    # 👇 ВОТ СЮДА добавь эти строки:
    data["rents"][track_number]["username"] = message.from_user.username or message.from_user.first_name
    
    save_data(data)
    
    await message.answer(
        f"✅ Окей, продлил!\n"
        f"📌 Номер: {track_number}\n"
        f"⏱ Продление: {days} {unit_word}\n"
        f"📅 Новый срок до: {time_display}",
        reply_markup=get_main_keyboard()
    )
    await state.clear()

# ================== ОСТАНОВИТЬ АРЕНДУ ==================
@dp.message(AllowedUsersFilter(), lambda message: message.text == "⏹ Остановить аренду")
async def stop_rent_start(message: types.Message):
    """Показать список активных аренд для остановки"""
    data = load_data()
    active_rents = list(data["rents"].keys())
    
    if not active_rents:
        await message.answer("📭 Нет активных аренд", reply_markup=get_rent_keyboard())
        return
    
    builder = InlineKeyboardBuilder()
    for number in active_rents:
        short_number = number[:30]
        builder.button(text=number, callback_data=f"stop_{short_number}")
    builder.button(text="🔙 Назад", callback_data="back_to_rent")
    builder.adjust(1)
    
    await message.answer(
        "📋 Выбери номер для остановки:",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(AllowedUsersFilter(), lambda c: c.data.startswith("stop_"))
async def stop_rent_confirm(callback: types.CallbackQuery, state: FSMContext):
    """Подтверждение остановки аренды"""
    track_number = callback.data.split("_")[1]
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
    """Обработка подтверждения остановки"""
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
        await message.answer("❌ Пожалуйста, используй кнопки Да/Нет")
        return
    
    await state.clear()
    await message.answer("Выбери действие:", reply_markup=get_main_keyboard())

# ================== ЧЕРНЫЙ СПИСОК ==================
@dp.callback_query(AllowedUsersFilter(), lambda c: c.data.startswith("blacklist_"))
async def blacklist_item_selected(callback: types.CallbackQuery):
    """Выбран номер из черного списка"""
    track_number = callback.data.split("_")[1]
    
    await callback.message.delete()
    await callback.message.answer(
        f"📌 Номер {track_number} в черном списке.\nЧто делаем?",
        reply_markup=get_blacklist_actions_keyboard(track_number)
    )
    await callback.answer()

@dp.callback_query(AllowedUsersFilter(), lambda c: c.data.startswith("remove_from_blacklist_"))
async def remove_from_blacklist(callback: types.CallbackQuery, state: FSMContext):
    """Убрать номер из черного списка"""
    track_number = callback.data.replace("remove_from_blacklist_", "")
    
    data = load_data()
    if track_number in data["blacklist"]:
        data["blacklist"].remove(track_number)
        save_data(data)
        
        await state.update_data(track_number=track_number)
        await state.set_state(RentStates.waiting_for_rent_days)
        
        await callback.message.delete()
        await callback.message.answer(
            f"✅ Номер {track_number} убран из ЧС\n"
            f"⏳ На сколько аренда? (напиши число)",
            reply_markup=get_back_keyboard()
        )
    await callback.answer()

@dp.callback_query(AllowedUsersFilter(), lambda c: c.data.startswith("to_blacklist_"))
async def add_to_blacklist(callback: types.CallbackQuery):
    """Добавить номер в черный список (из уведомления)"""
    track_number = callback.data.replace("to_blacklist_", "")
    
    data = load_data()
    if track_number in data["rents"]:
        del data["rents"][track_number]
    if track_number not in data["blacklist"]:
        data["blacklist"].append(track_number)
        save_data(data)
    
    await callback.message.delete()
    await callback.message.answer(
        f"⛔ Номер {track_number} добавлен в черный список",
        reply_markup=get_main_keyboard()
    )
    await callback.answer()

# ================== ПРОДЛЕНИЕ ИЗ УВЕДОМЛЕНИЯ ==================
@dp.callback_query(AllowedUsersFilter(), lambda c: c.data.startswith("extend_from_notify_"))
async def extend_from_notification(callback: types.CallbackQuery, state: FSMContext):
    """Продление из уведомления"""
    track_number = callback.data.replace("extend_from_notify_", "")
    await state.update_data(track_number=track_number)
    await state.set_state(RentStates.waiting_for_new_rent_days)
    
    await callback.message.delete()
    await callback.message.answer(
        f"📌 Номер {track_number}\n"
        f"⏳ На сколько продлить? (напиши число)",
        reply_markup=get_back_keyboard()
    )
    await callback.answer()

# ================== КНОПКИ НАЗАД ==================
@dp.callback_query(AllowedUsersFilter(), lambda c: c.data == "back_to_rent")
async def back_to_rent_menu(callback: types.CallbackQuery):
    """Вернуться в меню аренды"""
    await callback.message.delete()
    await callback.message.answer(
        "Что хочешь сделать?",
        reply_markup=get_rent_keyboard()
    )
    await callback.answer()

@dp.callback_query(AllowedUsersFilter(), lambda c: c.data == "back_to_main")
async def back_to_main_menu(callback: types.CallbackQuery):
    """Вернуться в главное меню"""
    await callback.message.delete()
    await callback.message.answer(
        "Выбери действие:",
        reply_markup=get_main_keyboard()
    )
    await callback.answer()

@dp.callback_query(AllowedUsersFilter(), lambda c: c.data == "back_to_blacklist")
async def back_to_blacklist(callback: types.CallbackQuery):
    """Вернуться к списку черного списка"""
    data = load_data()
    await callback.message.delete()
    if data["blacklist"]:
        await callback.message.answer(
            "📋 Номера в черном списке:",
            reply_markup=get_blacklist_keyboard(data["blacklist"])
        )
    else:
        await callback.message.answer(
            "📭 Черный список пуст",
            reply_markup=get_main_keyboard()
        )
    await callback.answer()

# ================== УВЕДОМЛЕНИЯ ==================
async def check_expired_rents():
    """Проверяет аренды и отправляет уведомления ВСЕМ пользователям в 20:00 МСК"""
    while True:
        try:
            now_msk = datetime.utcnow() + timedelta(hours=3)
            
            if now_msk.hour == 20 and 0 <= now_msk.minute <= 1:
                print(f"⏰ {now_msk.strftime('%d.%m.%Y %H:%M')} - Проверяю аренды, заканчивающиеся сегодня")
                
                data = load_data()
                today = now_msk.date()
                
                # Проходим по всем активным арендам
                for track_number, rent_info in list(data["rents"].items()):
                    try:
                        date_str = rent_info["end_date"].strip()
                        
                        # Получаем дату окончания аренды
                        if " " in date_str:
                            end_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
                            end_date_only = end_date.date()
                        else:
                            end_date_only = datetime.strptime(date_str, "%Y-%m-%d").date()
                        
                        # Если аренда заканчивается сегодня
                        if end_date_only == today:
                            print(f"📢 Аренда {track_number} заканчивается сегодня, отправляю уведомления ВСЕМ")
                            
                            # Отправляем уведомление КАЖДОМУ разрешенному пользователю
                            sent_count = 0
                            for user_id in ALLOWED_USERS:
                                try:
                                    await bot.send_message(
                                        user_id,
                                        f"⚠️ НАПОМИНАНИЕ В 20:00!\n"
                                        f"📌 Номер: {track_number}\n"
                                        f"⏱ СРОК АРЕНДЫ ИСТЕКАЕТ СЕГОДНЯ!\n\n"
                                        f"Этот номер был добавлен пользователем @{rent_info.get('username', 'неизвестно')}\n\n"
                                        f"Что делаем?",
                                        reply_markup=get_expired_notification_keyboard(track_number)
                                    )
                                    sent_count += 1
                                except Exception as e:
                                    print(f"❌ Не удалось отправить пользователю {user_id}: {e}")
                            
                            print(f"✅ Уведомление о {track_number} отправлено {sent_count} пользователям")
                            
                            # Удаляем запись после уведомления, чтобы не отправлять завтра
                            del data["rents"][track_number]
                            save_data(data)
                    
                    except Exception as e:
                        print(f"❌ Ошибка обработки {track_number}: {e}")
                        continue
                
                # Ждем минуту, чтобы не отправить повторно
                await asyncio.sleep(60)
            
            # Проверяем каждую минуту
            await asyncio.sleep(60)
            
        except Exception as e:
            logging.error(f"Ошибка в проверке уведомлений: {e}")
            await asyncio.sleep(60)

# ================== ЗАПУСК ==================
async def main():
    asyncio.create_task(check_expired_rents())
    
    mode = "ТЕСТОВЫЙ (минуты)" if TEST_MODE else "РАБОЧИЙ (дни)"
    print(f"✅ Бот запущен!")
    print(f"📊 Режим: {mode}")
    print(f"👥 Доступ разрешен для {len(ALLOWED_USERS)} пользователей")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())