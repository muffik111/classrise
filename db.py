import os
import sqlite3
import json
import logging

logger = logging.getLogger(__name__)

def get_db(db_path=None):
    """
    Возвращает соединение с БД.
    Если db_path не передан, определяет путь автоматически (Amvera /data или локально).
    timeout=10 обязателен для Gunicorn + SQLite.
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


def register_player(name, cls, base_stats):
    """
    Регистрирует игрока по НИКУ.
    Возвращает данные игрока со своим id или None, если ник занят.
    Не требует user_id (как ты и просил).
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

        player_id = cursor.lastrowid

        return {
            "id": player_id,
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
