import os
import sqlite3
import json
import logging

logger = logging.getLogger(__name__)

def get_db(db_path=None):
    """
    Возвращает соединение с БД.
    Если db_path не передан, определяет путь автоматически (для Amvera и локально).
    timeout=10 критически важен для SQLite при работе через Gunicorn (Amvera).
    """
    if db_path is None:
        if "AMVERA" in os.environ:
            data_dir = "/data"
        else:
            data_dir = "."
        db_path = os.path.join(data_dir, "game.db")

    # Создаём папку, если её нет (на Amvera /data может не существовать при первом запуске)
    data_dir = os.path.dirname(db_path)
    if data_dir and data_dir != ".":
        os.makedirs(data_dir, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def create_table():
    """
    Создаёт таблицу players, если её нет.
    Эта функция нужна только для ручного теста.
    В основном сценарии миграции делаются в server.py (migrate_db).
    """
    logger.info("Создание таблицы players (ручная функция)...")
    conn = get_db()
    cursor = conn.cursor()
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
    conn.close()
    logger.info("Таблица players готова.")


def register_player(name, cls, base_stats):
    """
    Регистрирует игрока по НИКУ.
    Не требует user_id.
    Возвращает данные игрока со своим id или None, если ник занят.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()

        # Проверка: занят ли ник
        cursor.execute("SELECT id FROM players WHERE name = ?", (name,))
        if cursor.fetchone():
            return None  # Ник занят

        base_attack = base_stats.get("base_attack", 10)
        base_defense = base_stats.get("base_defense", 5)
        max_hp = 100
        current_hp = max_hp

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

        # 🔥 Получаем ID только что созданного игрока
        player_id = cursor.lastrowid

        return {
            "id": player_id,              # <-- Обязательно для чата!
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
        logger.error(f"DB Error in register_player: {e}", exc_info=True)
        return None
