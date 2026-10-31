import asyncio
import sqlite3
from telethon import TelegramClient, events

# 1. Ваши данные от Telegram (получите на my.telegram.org)
API_ID =   #api_id 
API_HASH = ''  #api_hash

# ID или юзернейм группы 
TARGET_GROUP_ID =

client = TelegramClient('sno_session', API_ID, API_HASH)


def init_db():
    """Создаем таблицы в базе данных, если их еще нет"""
    conn = sqlite3.connect("sno_bot.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_categories (
            user_id INTEGER,
            category_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            FOREIGN KEY (category_id) REFERENCES categories (id),
            UNIQUE(user_id, category_id)
        )
    """)
    conn.commit()
    conn.close()


async def initial_sync():
    """Первичный сбор всех участников группы при запуске"""
    print("🔄 Запуск сканирования участников группы...")
    try:
        group_entity = await client.get_entity(TARGET_GROUP_ID)

        conn = sqlite3.connect("sno_bot.db")
        cursor = conn.cursor()

        async for user in client.iter_participants(group_entity):
            if user.bot:
                continue

            user_id = user.id
            username = user.username if user.username else None
            full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()

            cursor.execute("""
                INSERT OR REPLACE INTO users (user_id, username, full_name) 
                VALUES (?, ?, ?)
            """, (user_id, username, full_name))

        conn.commit()
        conn.close()
        print("✅ База участников успешно синхронизирована!")
    except Exception as e:
        print(f"⚠️ Ошибка при первичном сборе: {e}")


# Слушатель событий в реальном времени (Вариант 2)
@client.on(events.ChatAction())
async def handle_chat_action(event):
    if event.chat_id != TARGET_GROUP_ID:
        return

    conn = sqlite3.connect("sno_bot.db")
    cursor = conn.cursor()

    # Если кто-то вошел в группу
    if event.user_added or event.user_joined:
        user = await event.get_user()
        if user and not user.bot:
            user_id = user.id
            username = user.username if user.username else None
            full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()

            cursor.execute("""
                INSERT OR REPLACE INTO users (user_id, username, full_name) 
                VALUES (?, ?, ?)
            """, (user_id, username, full_name))
            conn.commit()
            print(f"➕ Новый участник добавлен в базу: {full_name} (@{username})")

    # Если кто-то вышел из группы
    elif event.user_left or event.user_kicked:
        user = await event.get_user()
        if user:
            user_id = user.id
            cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM user_categories WHERE user_id = ?", (user_id,))
            conn.commit()
            print(f"➖ Участник удален из базы (покинул группу): ID {user_id}")

    conn.close()


async def main():
    init_db()
    await client.start()
    print("🚀 Юзербот запущен и отслеживает события группы в реальном времени...")

    # Сначала собираем всех кто уже есть в группе
    await initial_sync()

    # Оставляем юзербота работать и слушать новые события
    await client.run_until_disconnected()


if __name__ == '__main__':
    asyncio.run(main())
