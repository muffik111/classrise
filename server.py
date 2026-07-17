import os
import json
import random
import sqlite3
from flask import Flask, request, send_from_directory, jsonify

app = Flask(__name__)
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

def migrate_players_table():
    conn = get_db()
    cursor = conn.cursor()

    columns = [
        "exp", "current_loc_id", "inventory_json", "equipment_json"
    ]
    for col in columns:
        try:
            cursor.execute(f"ALTER TABLE players ADD COLUMN {col} INTEGER")
        except sqlite3.OperationalError:
            # Колонка уже есть — ок
            pass

    # Для JSON колонок лучше явно задать дефолт, если они NULL
    cursor.execute("UPDATE players SET inventory_json = '[]' WHERE inventory_json IS NULL")
    cursor.execute("UPDATE players SET equipment_json = '{}' WHERE equipment_json IS NULL OR equipment_json = ''")

    conn.commit()
    conn.close()



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

# --- НАСТРОЙКИ БД ---
DB_PATH = '/data/game.db'  # Amvera: persistent storage

def get_db():
    """Возвращает соединение с SQLite. Создаёт таблицу players, если её нет."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
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
            equipment_json TEXT DEFAULT '{"weapon": null, "armor": null}'
        )
    ''')
    conn.commit()
    return conn

def init_db():
    get_db()

init_db()  # Инициализация при старте


# Предметы (база по ID)
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
    """Считает итоговые атаку и защиту с учётом экипировки."""
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
    if not name:
        return jsonify({'error': 'Имя обязательно'}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM players WHERE name = ?", (name,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({'error': 'Игрок не найден'}), 404

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


@app.route('/status', methods=['POST'])
def status():
    data = request.get_json() or {}
    player_name = (data.get('player_id') or '').strip()
    if not player_name:
        return jsonify({"error": "Имя игрока обязательно"}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM players WHERE name = ?", (player_name,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({'error': 'Игрок не найден.'}), 404

    try:
        inventory = json.loads(row['inventory_json'])
    except Exception:
        inventory = []

    hero = {
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

    attack, defense = calc_stats(hero)

    resp = {
        'name': hero['name'],
        'class': hero['class'],
        'level': hero['level'],
        'exp': hero['exp'],
        'next_level_exp': hero['next_level_exp'],
        'aden': hero['aden'],
        'current_hp': hero['current_hp'],
        'max_hp': hero['max_hp'],
        'attack': attack,
        'defense': defense,
        'inventory': hero['inventory'],
        'equipment': hero['equipment'],
    }
    return jsonify(resp)


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

    logging.info(f"[DEBUG] PARSED DATA: {data}")

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
    if not password:
        return jsonify({"error": "Пароль обязателен"}), 400

    normalized_cls = cls.capitalize() if len(cls) > 0 else cls
    class_stats = {
        'Воин': {'attack': 110, 'defense': 15, 'crit_chance': 0.10, 'crit_mult': 1.5},
        'Лучник': {'attack': 95, 'defense': 8, 'crit_chance': 0.20, 'crit_mult': 2.0},
        'Танк': {'attack': 80, 'defense': 25, 'crit_chance': 0.05, 'crit_mult': 1.3},
        'Друид': {'attack': 70, 'defense': 12, 'crit_chance': 0.12, 'crit_mult': 1.6},
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

    # ✅ Теперь сохраняем inventory_json и equipment_json явно
    cur.execute('''
        INSERT INTO players (name, class, attack, defense, max_hp, current_hp, inventory_json, equipment_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        name,
        normalized_cls,
        stats['attack'],
        stats['defense'],
        100,
        100,
        '[]',
        '{"weapon": null, "armor": null}'
    ))
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


@app.route('/fight', methods=['POST'])
def fight():
    data = request.get_json() or {}
    player_name = (data.get('player_id') or '').strip()
    if not player_name:
        return jsonify({"success": False, "message": "Имя игрока обязательно"}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM players WHERE name = ?", (player_name,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return jsonify({'success': False, 'message': 'Игрок не найден.'}), 404

    try:
        inventory = json.loads(row['inventory_json'])
    except Exception:
        inventory = []
    try:
        equipment = json.loads(row['equipment_json'])
    except Exception:
        equipment = {"weapon": None, "armor": None}

    h = {
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
        "equipment": equipment,
    }

    if h['current_hp'] <= 0:
        h['current_hp'] = max(0, h['max_hp'] // 2)
        cur.execute("UPDATE players SET current_hp = ? WHERE name = ?", (h['current_hp'], h['name']))
        conn.commit()
        conn.close()
        return jsonify({
            'success': False,
            'message': 'Ты был мёртв, но воскрес с половиной здоровья. Попробуй снова.'
        })

    attack, defense = calc_stats(h)

    mob_hp = random.randint(80, 120)
    mob_attack = random.randint(12, 22)
    mob_defense = random.randint(4, 8)

    log = []
    log.append(f'⚔️ Ты выходишь на бой против монстра (HP: {mob_hp}, ATK: {mob_attack}, DEF: {mob_defense})')

    round_num = 1
    while mob_hp > 0 and h['current_hp'] > 0:
        log.append(f'\n--- Раунд {round_num} ---')

        dmg_to_mob = max(1, int((attack - mob_defense) * random.uniform(0.8, 1.2)))
        mob_hp -= dmg_to_mob
        log.append(f'Ты наносишь {dmg_to_mob} урона. У монстра осталось {max(0, mob_hp)} HP.')

        if mob_hp <= 0:
            break

        dmg_to_player = max(1, int((mob_attack - defense) * random.uniform(0.8, 1.2)))
        h['current_hp'] -= dmg_to_player
        log.append(f'Монстр бьёт тебя на {dmg_to_player} урона. У тебя осталось {max(0, h["current_hp"])} HP.')

        round_num += 1

    reward_aden = random.randint(50, 150)
    loot_chance = random.random()
    loot_item_id = None
    if loot_chance > 0.6:
        loot_item_id = random.choice(list(ITEMS_DB.keys()))
        h['inventory'].append(loot_item_id)
        log.append(f'🎒 С монстра выпал предмет с ID {loot_item_id}! Добавлен в инвентарь.')

    h['aden'] += reward_aden
    log.append(f'💰 Ты получил {reward_aden} Аденов.')

    exp_gain = random.randint(30, 70)
    h['exp'] += exp_gain
    log.append(f'✨ Ты получил {exp_gain} EXP.')

    level_up = False
    while h['exp'] >= h['next_level_exp']:
        h['level'] += 1
        h['exp'] -= h['next_level_exp']
        h['next_level_exp'] = int(h['next_level_exp'] * 1.4)
        h['max_hp'] += 20
        h['current_hp'] = h['max_hp']
        level_up = True

    cur.execute('''
        UPDATE players
        SET level = ?,
            exp = ?,
            next_level_exp = ?,
            adenas = ?,
            max_hp = ?,
            current_hp = ?
        WHERE name = ?
    ''', (
        h['level'],
        h['exp'],
        h['next_level_exp'],
        h['aden'],
        h['max_hp'],
        h['current_hp'],
        h['name']
    ))
    conn.commit()

    message = '\n'.join(log)
    if h['current_hp'] <= 0:
        message += '\n💀 Ты погиб в бою… Но будешь воскрешён при следующем запросе статуса.'

    return jsonify({
        'success': True,
        'message': message,
        'player_id': player_name,
    })

@app.route('/api/augment', methods=['POST'])
def api_augment():
    data = request.get_json(silent=True) or {}
    player_id = (data.get('player_id') or '').strip()
    location = data.get('location')
    index = data.get('index')
    slot = data.get('slot')

    if not player_id or not location:
        return jsonify({"error": "Недостаточно данных"}), 400

    from augment import load_player, perform_augment

    hero = load_player(player_id)
    if not hero:
        return jsonify({"error": "Игрок не найден"}), 404

    key = index if location == 'inventory' else slot
    success, message, partial = perform_augment(hero, location, key)

    response_data = {
        "success": success,
        "message": message,
        **partial,
    }
    return jsonify(response_data), 200

@app.route('/api/battle', methods=['POST'])
def api_battle():
    data = request.get_json(silent=True) or {}
    player_id = (data.get('player_id') or '').strip()
    mob_id = data.get('mob_id')

    if not player_id or not mob_id:
        return jsonify({"error": "Недостаточно данных"}), 400

    from augment import load_player, save_player
    from battle import run_battle

    hero = load_player(player_id)
    if not hero:
        return jsonify({"error": "Игрок не найден"}), 404

    result = run_battle(hero, mob_id)

    # Сохраняем изменения (EXP, уровень, HP, инвентарь, статы)
    save_player(hero)

    response_data = {
        "success": result["success"],
        "won": result["won"],
        "rounds": result["rounds"],
        "player": result["player_updated"],
        "message": result.get("message", ""),
    }
    return jsonify(response_data), 200

@app.route('/api/move', methods=['POST'])
def api_move():
    data = request.get_json(silent=True) or {}
    player_id = (data.get('player_id') or '').strip()
    loc_id = data.get('loc_id')

    if not player_id or loc_id is None:
        return jsonify({"error": "Недостаточно данных"}), 400

    from augment import load_player, save_player
    import cities

    hero = load_player(player_id)
    if not hero:
        return jsonify({"error": "Игрок не найден"}), 404

    # Проверка доступности локации
    if not cities.is_location_accessible(hero["level"], loc_id):
        return jsonify({
            "success": False,
            "message": "❌ Эта локация слишком сложна для вашего уровня. Повысьте уровень или выберите другую."
        }), 403

    # Сохраняем текущую локацию у игрока (добавь колонку current_loc_id в players)
    hero["current_loc_id"] = loc_id
    save_player(hero)

    loc_info = cities.get_location_info(loc_id)
    city_info = next((c for c in cities.CITIES if c["id"] == loc_info["city_id"]), None)

    return jsonify({
        "success": True,
        "message": f"✅ Вы переместились в локацию: {loc_info['name']}",
        "location": loc_info,
        "city": city_info,
        "player": {
            "current_loc_id": loc_id,
            "level": hero["level"],
        },
    }), 200

@app.route('/api/start_battle', methods=['POST'])
def api_start_battle():
    data = request.get_json(silent=True) or {}
    player_id = (data.get('player_id') or '').strip()

    if not player_id:
        return jsonify({"error": "Недостаточно данных"}), 400

    from augment import load_player, save_player
    from battle import run_battle
    import cities
    from mobs import MOBS

    hero = load_player(player_id)
    if not hero:
        return jsonify({"error": "Игрок не найден"}), 404

    loc_id = hero.get("current_loc_id")
    if not loc_id:
        return jsonify({"error": "Сначала переместитесь в локацию через /api/move"}), 400

    mob_id = cities.get_mob_id_for_location(loc_id, hero["level"])
    if not mob_id:
        return jsonify({"error": "В этой локации нет подходящих мобов"}), 500

    result = run_battle(hero, mob_id)
    save_player(hero)

    return jsonify({
        "success": result["success"],
        "won": result["won"],
        "rounds": result["rounds"],
        "mob": MOBS.get(mob_id),
        "player": result["player_updated"],
    }), 200


@app.route('/equip', methods=['POST'])
def equip():
    data = request.get_json() or {}
    player_name = (data.get('player_id') or '').strip()
    item_id = data.get('item_id')
    slot = data.get('slot')

    if not player_name or not item_id or not slot:
        return jsonify({'success': False, 'message': 'Не хватает параметров: player_id, item_id, slot'}), 400

    if slot not in ('weapon', 'armor'):
        return jsonify({'success': False, 'message': 'Неверный слот экипировки. Допустимо: weapon, armor'}), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM players WHERE name = ?", (player_name,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'message': 'Игрок не найден.'}), 404

    try:
        inventory = json.loads(row['inventory_json'])
    except Exception:
        inventory = []

    try:
        equipment = json.loads(row['equipment_json'])
    except Exception:
        equipment = {"weapon": None, "armor": None}

    # Проверка: предмет есть в инвентаре?
    if item_id not in inventory:
        conn.close()
        return jsonify({
            'success': False,
            'message': f'Предмета с ID {item_id} нет в инвентаре. Сначала получи его в бою.'
        }), 400

    # Проверка: предмет существует в базе предметов
    if item_id not in ITEMS_DB:
        conn.close()
        return jsonify({'success': False, 'message': 'Предмет с таким ID не существует.'}), 400

    # Экипировка: убираем из инвентаря, ставим в слот
    inventory.remove(item_id)
    equipment[slot] = item_id

    # Сохраняем обратно в БД
    cur.execute('''
        UPDATE players
        SET inventory_json = ?, equipment_json = ?
        WHERE name = ?
    ''', (json.dumps(inventory), json.dumps(equipment), player_name))
    conn.commit()
    conn.close()

    item_name = ITEMS_DB[item_id]['name']
    return jsonify({
        'success': True,
        'message': f'{item_name} успешно надет в слот "{slot}".',
    })


@app.route('/admin/players', methods=['GET'])
def admin_players():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, class, level, adenas, exp, next_level_exp,
               max_hp, current_hp, attack, defense
        FROM players
    """)
    rows = cur.fetchall()
    conn.close()

    players = []
    for r in rows:
        players.append({
            "id": r["id"],
            "name": r["name"],
            "class": r["class"],
            "level": r["level"],
            "aden": r["adenas"],
            "exp": r["exp"],
            "next_level_exp": r["next_level_exp"],
            "max_hp": r["max_hp"],
            "current_hp": r["current_hp"],
            "attack": r["attack"],
            "defense": r["defense"],
        })
    return jsonify(players)
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


# ВАЖНО: этот дублирующийся /status удалён — он перекрывал настоящий статус игрока.
# Теперь работает только POST /status, который возвращает полные данные героя.

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
