import sqlite3

conn = sqlite3.connect("database.db")
cur = conn.cursor()

columns = [
    ("language", "VARCHAR DEFAULT 'ru' NOT NULL"),
    ("language_selected", "BOOLEAN DEFAULT 0 NOT NULL"),
    ("is_premium", "BOOLEAN DEFAULT 0 NOT NULL"),
    ("premium_until", "DATETIME"),
]

for name, definition in columns:
    try:
        cur.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")
        print(f"Добавлена колонка {name}")
    except sqlite3.OperationalError as e:
        print(f"Пропущено {name}: {e}")

conn.commit()
conn.close()