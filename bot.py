import asyncio
import logging
import sqlite3
import re
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

API_TOKEN = ''  

bot = Bot(token=API_TOKEN)
dp = Dispatcher()


class BotStates(StatesGroup):
    waiting_for_category_name = State()
    waiting_for_username = State()


def get_db():
    return sqlite3.connect("sno_bot.db")


# 1. Команда /start в ЛС
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.chat.type != "private":
        return  # Команда /start работает в ЛС

    kb = [
        [InlineKeyboardButton(text="📁 Категории", callback_data="show_categories")],
        [InlineKeyboardButton(text="🔔 Меню пинга", callback_data="ping_menu")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=kb)
    await message.answer(
        "Привет! Я бот СНО для управления участниками.\n\n"
        "💡 **Как пинговать в группе:**\n"
        "Напишите в чате группы: `/ping Название Категории` (например: `/ping Пресса`)",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


# 2. Пинг в группе по команде /ping
@dp.message(Command("ping"))
async def cmd_ping_group(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("⚠️ Укажите название категории!\nПример: `/ping Пресса`", parse_mode="Markdown")
        return

    cat_name = args[1].strip()
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT u.user_id, u.username, u.full_name 
        FROM users u
        JOIN user_categories uc ON u.user_id = uc.user_id
        JOIN categories c ON c.id = uc.category_id
        WHERE LOWER(c.name) = LOWER(?)
    """, (cat_name,))
    users = cursor.fetchall()
    conn.close()

    if not users:
        await message.reply(f"❌ Категория «{cat_name}» не найдена или в ней нет участников.")
        return

    mentions = []
    for user_id, username, full_name in users:
        name = full_name if full_name else (username or "Участник")
        mentions.append(f"[{name}](tg://user?id={user_id})")

    chunk_size = 10
    for i in range(0, len(mentions), chunk_size):
        chunk = mentions[i:i + chunk_size]
        text = f"📢 **Внимание, категория [{cat_name}]!**\n\n" + " ".join(chunk)
        await message.answer(text, parse_mode="Markdown")


# 3. Управление категориями (Кнопки)
@dp.callback_query(F.data == "show_categories")
async def show_categories(callback: types.CallbackQuery):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM categories")
    categories = cursor.fetchall()
    conn.close()

    kb = []
    for cat_id, cat_name in categories:
        kb.append([InlineKeyboardButton(text=cat_name, callback_data=f"cat_{cat_id}")])

    kb.append([InlineKeyboardButton(text="➕ Добавить категорию", callback_data="add_category")])
    kb.append([InlineKeyboardButton(text="🔙 На главную", callback_data="back_main")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=kb)
    await callback.message.edit_text("📁 **Список категорий СНО:**", reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()


@dp.callback_query(F.data == "add_category")
async def add_category_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите название новой категории (например: Пресса):")
    await state.set_state(BotStates.waiting_for_category_name)
    await callback.answer()


@dp.message(BotStates.waiting_for_category_name)
async def save_category(message: types.Message, state: FSMContext):
    cat_name = message.text.strip()
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO categories (name) VALUES (?)", (cat_name,))
        conn.commit()
        await message.answer(f"✅ Категория «{cat_name}» успешно создана!")
    except sqlite3.IntegrityError:
        await message.answer("⚠️ Такая категория уже существует.")
    finally:
        conn.close()
    await state.clear()


@dp.callback_query(F.data.startswith("cat_"))
async def view_category(callback: types.CallbackQuery):
    cat_id = int(callback.data.split("_")[1])

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM categories WHERE id = ?", (cat_id,))
    cat_name = cursor.fetchone()[0]

    cursor.execute("""
        SELECT u.username, u.full_name 
        FROM users u
        JOIN user_categories uc ON u.user_id = uc.user_id
        WHERE uc.category_id = ?
    """, (cat_id,))
    members = cursor.fetchall()
    conn.close()

    text = f"📁 **Категория: {cat_name}**\n\n"
    if members:
        text += "**Участники:**\n"
        for username, full_name in members:
            name = full_name if full_name else "Без имени"
            tag = f"(@{username})" if username else ""
            text += f"• {name} {tag}\n"
    else:
        text += "В этой категории пока нет участников."

    kb = [
        [InlineKeyboardButton(text="➕ Добавить участника", callback_data=f"add_user_{cat_id}")],
        [InlineKeyboardButton(text="🔙 Назад к категориям", callback_data="show_categories")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=kb)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()


@dp.callback_query(F.data.startswith("add_user_"))
async def start_add_user(callback: types.CallbackQuery, state: FSMContext):
    cat_id = int(callback.data.split("_")[2])
    await state.update_data(category_id=cat_id)
    await state.set_state(BotStates.waiting_for_username)

    await callback.message.answer(
        "Введите **username**, **ID** или отправьте ссылку вида `tg://user?id=...` пользователя:"
    )
    await callback.answer()


@dp.message(BotStates.waiting_for_username)
async def save_user_to_category(message: types.Message, state: FSMContext):
    text_input = message.text.strip()
    data = await state.get_data()
    cat_id = data.get("category_id")

    conn = get_db()
    cursor = conn.cursor()

    # 1. Пытаемся вытащить ID из ссылки вида tg://user?id=...
    match_id = re.search(r'id=(\d+)', text_input)

    if match_id:
        user_id = int(match_id.group(1))
        cursor.execute("SELECT user_id, full_name FROM users WHERE user_id = ?", (user_id,))
    # 2. Если ввели просто цифры (чистый ID)
    elif text_input.isdigit():
        user_id = int(text_input)
        cursor.execute("SELECT user_id, full_name FROM users WHERE user_id = ?", (user_id,))
    # 3. Если ввели обычный username (например, @ivanov)
    else:
        username = text_input.lstrip('@')
        cursor.execute("SELECT user_id, full_name FROM users WHERE LOWER(username) = LOWER(?)", (username,))

    user = cursor.fetchone()

    if not user:
        await message.answer(
            f"❌ Пользователь не найден в базе данных!\n"
            "Убедитесь, что этот человек есть в группе и юзербот уже скачал его данные."
        )
        conn.close()
        await state.clear()
        return

    user_id, full_name = user

    try:
        cursor.execute("INSERT INTO user_categories (user_id, category_id) VALUES (?, ?)", (user_id, cat_id))
        conn.commit()
        name_display = full_name if full_name else str(user_id)
        await message.answer(f"✅ Пользователь **{name_display}** успешно добавлен в категорию!")
    except sqlite3.IntegrityError:
        await message.answer(f"⚠️ Этот пользователь уже состоит в данной категории.")
    finally:
        conn.close()

    await state.clear()


@dp.callback_query(F.data == "ping_menu")
async def ping_menu(callback: types.CallbackQuery):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM categories")
    categories = cursor.fetchall()
    conn.close()

    kb = []
    for cat_id, cat_name in categories:
        kb.append([InlineKeyboardButton(text=f"📢 Пинг: {cat_name}", callback_data=f"ping_cat_{cat_id}")])
    kb.append([InlineKeyboardButton(text="🔙 На главную", callback_data="back_main")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=kb)
    await callback.message.edit_text("🔔 Выберите категорию для пинга в группе:", reply_markup=keyboard)
    await callback.answer()


@dp.callback_query(F.data.startswith("ping_cat_"))
async def trigger_ping(callback: types.CallbackQuery):
    await callback.answer("Лучше используйте команду /ping в самой группе!", show_alert=True)


@dp.callback_query(F.data == "back_main")
async def back_main(callback: types.CallbackQuery):
    kb = [
        [InlineKeyboardButton(text="📁 Категории", callback_data="show_categories")],
        [InlineKeyboardButton(text="🔔 Меню пинга", callback_data="ping_menu")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=kb)
    await callback.message.edit_text("Главное меню:", reply_markup=keyboard)
    await callback.answer()


async def main():
    logging.basicConfig(level=logging.INFO)
    print("Бот успешно запущен и готов к работе!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
