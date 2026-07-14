import os
import json
import random
import sqlite3
import bcrypt
from flask import Flask, request, send_from_directory, jsonify

app = Flask(__name__)

DB_PATH = '/data/game.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Добавляем колонку password_hash, если её нет
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            class TEXT NOT NULL,
            level INTEGER DEFAULT 1,
            adenas INTEGER DEFAULT 0,
            exp INTEGER DEFAULT 0,
            next_level_exp INTEGER DEFAULT 100,
            max_hp INTEGER DEFAULT 100,
            current_hp INTEGER DEFAULT 100,
            attack INTEGER DEFAULT 0,
            defense INTEGER DEFAULT 0,
            inventory_json TEXT DEFAULT '[]',
            equipment_json TEXT DEFAULT '{"weapon": null, "armor": null}',
            password_hash TEXT
        )
    ''')
    conn.commit()
    return conn

def init_db():
    get_db()

init_db()

ITEMS_DB = {
    1: {"id": 1, "name": "Ржавый меч", "type": "weapon", "bonus_attack": 5, "bonus_defense": 0, "price": 100},
    2: {"id": 2, "name": "Стальной клинок", "type": "weapon", "bonus_attack": 12, "bonus_defense": 0, "price": 250},
    3: {"id": 3, "name": "Лук новичка", "type": "weapon", "bonus_attack": 8, "bonus_defense": 0, "price": 180},
    4: {"id": 4, "name": "Деревянный щит", "type": "armor", "bonus_attack": 0, "bonus_defense": 6, "price": 150},
    5: {"id": 5, "name": "Тяжёлый стальной щит", "type": "armor", "bonus_attack": 0, "bonus_defense": 14, "price": 320},
    6: {"id": 6, "name": "Кожаная броня", "type": "armor", "bonus_attack": 0, "bonus_defense": 8, "price": 200},
    7: {"id": 7, "name": "Кольчуга", "type": "armor", "bonus_attack": 0, "bonus_defense": 16, "price": 400},
}

def calc_stats(hero):
    bonus_atk = 0
    bonus_def = 0

    try:
        equipment = json.loads(hero['equipment_json'])
    except Exception:
        equipment = {"weapon": None, "armor": None}

    if equipment.get('weapon') and equipment['weapon'] in ITEMS_DB:
        item = ITEMS_DB[equipment['weapon']]
        bonus_atk += item['bonus_attack']
        bonus_def += item['bonus_defense']

    if equipment.get('armor') and equipment['armor'] in ITEMS_DB:
        item = ITEMS_DB[equipment['armor']]
        bonus_atk += item['bonus_attack']
        bonus_def += item['bonus_defense']

    final_attack = hero['attack'] + bonus_atk
    final_defense = hero['defense'] + bonus_def
    return final_attack, final_defense

@app.route('/')
def root():
    return send_from_directory('templates', 'login.html')

@app.route('/game.html')
def game_page():
    return send_from_directory('templates', 'game.html')

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    password = (data.get('password') or '').strip()

    if not name or not password:
        return jsonify({'error': 'Имя и пароль обязательны'}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM players WHERE name = ?", (name,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({'error': 'Игрок не найден'}), 404

    stored_hash = row['password_hash']
    if not stored_hash:
        # Если у старых игроков нет хеша — считаем вход неверным
        return jsonify({'error': 'Неверный логин или пароль'}), 401

    # Проверка пароля
    if not bcrypt.checkpw(password.encode('utf-8'), stored_hash):
        return jsonify({'error': 'Неверный логин или пароль'}), 401

    try:
        inventory = json.loads(row['inventory_json'])
    except Exception:
        inventory = []

    player = {
        "name": row["name"],
        "class": row["class"],
        "level": row["level"],
        "aden": row["adenas"],
        "exp": row["exp"],
        "next_level_exp": row["next_level_exp"],
        "current_hp": row["current_hp"],
        "max_hp": row["max_hp"],
        "attack": row["attack"],
        "defense": row["defense"],
        "inventory": inventory,
        "equipment": json.loads(row["equipment_json"]) if row["equipment_json"] else {"weapon": None, "armor": None},
    }
    return jsonify(player), 200

@app.route('/create-hero', methods=['POST'])
def create_hero():
    import logging
    logging.basicConfig(level=logging.INFO)

    raw_body = request.get_data(as_text=True)
    logging.info(f"[DEBUG] RAW BODY: {raw_body}")

    data = {}
    try:
        if raw_body:
            data = json.loads(raw_body)
    except json.JSONDecodeError as e:
        logging.error(f"[DEBUG] JSON Parse Error: {e}")
        return jsonify({"error": "Неверный формат JSON"}), 400

    name = (data.get('name') or '').strip()
    cls = (data.get('class') or data.get('cls') or '').strip()
    password = (data.get('password') or '').strip()

    logging.info(f"[DEBUG] Name='{name}', Class='{cls}', Password len={len(password)}")

    if not name:
        return jsonify({"error": "Поле 'name' обязательно"}), 400
    if not cls:
        return jsonify({
            "error": "Поле 'class' обязательно. Доступные: Воин, Лучник, Танк, Друид"
        }), 400
    if not password or len(password) < 4:
        return jsonify({"error": "Пароль обязателен и должен быть не короче 4 символов"}), 400

    normalized_cls = cls.capitalize() if len(cls) > 0 else cls
    class_stats = {
        'Воин': {'attack': 110, 'defense': 15},
        'Лучник': {'attack': 95, 'defense': 8},
        'Танк': {'attack': 80, 'defense': 25},
        'Друид': {'attack': 70, 'defense': 12},
    }
    stats = class_stats.get(cls) or class_stats.get(normalized_cls)
    if not stats:
        return jsonify({
            "error": "Недопустимый класс",
            "allowed": list(class_stats.keys())
        }), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT id FROM players WHERE name = ?", (name,))
    if cur.fetchone():
        conn.close()
        return jsonify({"error": "Ник уже занят"}), 409

    # Хешируем пароль
    salt = bcrypt.gensalt(rounds=12)
    password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)

    cur.execute('''
        INSERT INTO players (name, class, attack, defense, max_hp, current_hp, password_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (name, normalized_cls, stats['attack'], stats['defense'], 100, 100, password_hash))
    conn.commit()
    conn.close()

    player = {
        "name": name,
        "class": normalized_cls,
        "level": 1,
        "aden": 0,
        "exp": 0,
        "next_level_exp": 100,
        "current_hp": 100,
        "max_hp": 100,
        "attack": stats['attack'],
        "defense": stats['defense'],
        "inventory": [],
        "equipment": {"weapon": None, "armor": None},
    }
    return jsonify(player), 201

# Дальше идут те же `/status`, `/fight`, `/equip`, `/admin/players` из прошлого ответа — их можно просто вставить после этого блока
