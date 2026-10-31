import sqlite3


def init_db():
    conn = sqlite3.connect("sno_bot.db")
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT
        )
    """)

    # Таблица категорий (Проектный офис, Пресса и т.д.)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    """)

    # Таблица связи пользователей с категориями
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_categories (
            user_id INTEGER,
            category_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            FOREIGN KEY (category_id) REFERENCES categories (id),
            PRIMARY KEY (user_id, category_id)
        )
    """)

    conn.commit()
    conn.close()
    print("База данных успешно инициализирована!")


if __name__ == "__main__":
    init_db()