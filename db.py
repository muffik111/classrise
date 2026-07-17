# db.py (лучше переименовать из общего файла, чтобы не конфликтовало)
import sqlite3
import os
import json

DATA_DIR = '/data'
DB_FILE = os.path.join(DATA_DIR, 'game.db')

os.makedirs(DATA_DIR, exist_ok=True)

def get_db():
    """Возвращает соединение с БД. Создаёт таблицу players, если её нет."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # Чтобы обращаться к колонкам по имени
    cursor = conn.cursor()

    # Создаём таблицу с нужными колонками и без лишнего stats_json
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            class TEXT NOT NULL,

            level INTEGER DEFAULT 1,
            exp INTEGER DEFAULT 0,

            adenas INTEGER DEFAULT 0,

            attack INTEGER DEFAULT 0,
            defense INTEGER DEFAULT 0,

            current_hp INTEGER DEFAULT 100,
            max_hp INTEGER DEFAULT 100,

            inventory_json TEXT DEFAULT '[]',
            equipment_json TEXT DEFAULT '{"weapon": null, "armor": null}',

            current_loc_id INTEGER,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    return conn


def create_table():
    get_db()


def register_player(name, cls, base_stats):
    """
    Регистрирует игрока.
    base_stats: dict с base_attack, base_defense (или можно считать по классу).
    Возвращает данные игрока или None, если ник занят.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()

        # Проверяем, есть ли такой ник
        cursor.execute("SELECT * FROM players WHERE name = ?", (name,))
        if cursor.fetchone():
            return None  # Ник занят

        # Начальные статы
        base_attack = base_stats.get("base_attack", 10)
        base_defense = base_stats.get("base_defense", 5)
        max_hp = 100
        current_hp = max_hp

        # Инвентарь и экипировка — пустые структуры
        inventory_str = json.dumps([])
        equipment_str = json.dumps({"weapon": None, "armor": None})

        cursor.execute('''
            INSERT INTO players (
                name, class, level, exp, adenas,
                attack, defense, current_hp, max_hp,
                inventory_json, equipment_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            name, cls, 1, 0, 0,
            base_attack, base_defense, current_hp, max_hp,
            inventory_str, equipment_str
        ))

        conn.commit()

        return {
            "name": name,
            "class": cls,
            "level": 1,
            "exp": 0,
            "aden": 0,
            "attack": base_attack,
            "defense": base_defense,
            "current_hp": current_hp,
            "max_hp": max_hp,
            "inventory": [],
            "equipment": {"weapon": None, "armor": None},
        }
    except Exception as e:
        print(f"DB Error: {e}")
        return None
