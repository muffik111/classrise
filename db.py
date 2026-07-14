import sqlite3
import os
import json

DATA_DIR = '/data'
DB_FILE = os.path.join(DATA_DIR, 'game.db')

# Создаём директорию, если её нет (Amvera обычно делает это через volumes, но страховка не помешает)
os.makedirs(DATA_DIR, exist_ok=True)

def get_db():
    """Возвращает соединение с БД. Создаёт таблицу players, если её нет."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # Чтобы обращаться к колонкам по имени
    
    cursor = conn.cursor()
    # Создаём таблицу, если нет
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            class TEXT NOT NULL,
            level INTEGER DEFAULT 1,
            adenas INTEGER DEFAULT 0,
            stats_json TEXT,
            inventory_json TEXT,
            equipment_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    return conn

def create_table():
    # Просто вызываем get_db(), чтобы таблица точно была
    get_db()

def register_player(name, cls, stats):
    """Регистрирует игрока. Возвращает данные игрока или None, если ник занят."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Проверяем, есть ли такой ник
        cursor.execute("SELECT * FROM players WHERE name = ?", (name,))
        if cursor.fetchone():
            return None  # Ник занят
        
        # Вставляем игрока
        stats_str = json.dumps(stats) if isinstance(stats, dict) else str(stats)
        cursor.execute('''
            INSERT INTO players (name, class, stats_json)
            VALUES (?, ?, ?)
        ''', (name, cls, stats_str))
        
        conn.commit()
        
        # Возвращаем данные нового игрока (упрощённо)
        return {
            "name": name,
            "class": cls,
            "level": 1,
            "aden": 0,
            "inventory": [],
            "equipment": {"weapon": None, "armor": None},
            "current_hp": 100,
            "max_hp": 100,
            "attack": stats.get("attack", 0),
            "defense": stats.get("defense", 0)
        }
    except Exception as e:
        print(f"DB Error: {e}")
        return None
