import sqlite3
import os

# Варианты путей, которые мы проверим
possible_paths = [
    'db/game.db',
    'game.db',
    os.path.join('db', 'game.db'),
]

db_path = None
for p in possible_paths:
    if os.path.exists(p):
        db_path = p
        break

if not db_path:
    print("❌ Файл базы данных не найден ни в одном из проверенных мест.")
    print("Проверь, что:")
    print("  1. Папка db существует")
    print("  2. Файл game.db существует")
    print("  3. Ты запускаешь скрипт из папки проекта (C:\\HeroPath)")
    exit(1)

print(f"✅ База найдена: {os.path.abspath(db_path)}")

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(players)")
    columns = cursor.fetchall()

    print("\nСписок колонок таблицы players:")
    for col in columns:
        # col[1] — имя колонки
        print("-", col[1])

    has_is_admin = any(col[1] == 'is_admin' for col in columns)
    if has_is_admin:
        print("\n✅ Колонка is_admin ЕСТЬ.")
    else:
        print("\n❌ Колонка is_admin НЕТ.")

except sqlite3.Error as e:
    print(f"\n❌ Ошибка при работе с БД: {e}")
finally:
    if 'conn' in locals():
        conn.close()
