import os
import json
import random
import logging
from datetime import datetime
from functools import wraps
import time
import sqlite3
from flask import Flask, request, send_from_directory, jsonify, session, g

# Импорты твоего проекта
from db import get_db
from items import ITEMS_DB, calc_stats
from classes import get_class_stats
# from cities import is_location_accessible, get_location_info  # раскомментируй, если есть

DATA_DIR = '/data'
DB_FILE = os.path.join(DATA_DIR, 'game.db')
os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CHAT_MESSAGES = []          # список сообщений в памяти
MAX_CHAT_HISTORY = 100      # сколько хранить
# На Amvera обязательно задай переменную окружения SECRET_KEY
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod-on-amvera')


# -----------------------------------------------------------------------------
# Миграции БД (чат + нормализация игроков)
# -----------------------------------------------------------------------------
def migrate_db():
    logger.info("Запуск миграций БД...")
    conn = get_db()
    cur = conn.cursor()

    # Добавляем колонку is_admin, если нет
    try:
        cur.execute("PRAGMA table_info(players)")
        cols = [c[1] for c in cur.fetchall()]
        if 'is_admin' not in cols:
            cur.execute("ALTER TABLE players ADD COLUMN is_admin INTEGER DEFAULT 0")
            logger.info("Миграция: добавлена колонка is_admin в players")
    except Exception as e:
        logger.error(f"Ошибка миграции is_admin: {e}")

    # Создаём таблицу чата, если нет
    try:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name TEXT NOT NULL,
                message TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'chat',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        logger.info("Миграция: таблица chat_messages готова")
    except Exception as e:
        logger.error(f"Ошибка создания chat_messages: {e}")

    conn.commit()
    conn.close()
    logger.info("Миграции завершены.")


migrate_db()  # запускаем один раз при старте приложения


# -----------------------------------------------------------------------------
# Сессии и декораторы безопасности
# -----------------------------------------------------------------------------
@app.before_request
def load_user():
    g.user = None
    if 'user_id' in session:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, name, is_admin FROM players WHERE id = ?", (session['user_id'],))
        row = cur.fetchone()
        conn.close()
        if row:
            g.user = {'id': row[0], 'name': row[1], 'is_admin': bool(row[2])}


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not g.user:
            return jsonify({'error': 'Требуется авторизация'}), 401
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not g.user or not g.user['is_admin']:
            return jsonify({'error': 'Нет прав администратора'}), 403
        return f(*args, **kwargs)
    return decorated


# -----------------------------------------------------------------------------
# Эндпоинты: логин, регистрация, статус
# -----------------------------------------------------------------------------
@app.route('/')
def root():
    return send_from_directory('templates', 'login.html')


@app.route('/game.html')
def game_page():
    if not g.user:
        return send_from_directory('templates', 'login.html')
    return send_from_directory('templates', 'game.html')


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    password = (data.get('password') or '').strip()  # если у тебя есть bcrypt — используй его здесь

    if not name:
        return jsonify({'error': 'Имя обязательно'}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM players WHERE name = ?", (name,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({'error': 'Игрок не найден'}), 404

    # Если есть bcrypt: сравнивай хеши. Сейчас просто принимаем любой пароль для теста.
    # if not bcrypt.checkpw(password.encode(), row['password_hash']):
    #     return jsonify({'error': 'Неверный пароль'}), 401

    session['user_id'] = row['id']
    session.permanent = True

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
    }
    try:
        inventory = json.loads(row['inventory_json'] or '[]')
    except:
        inventory = []
    try:
        equipment = json.loads(row['equipment_json'] or '{}')
    except:
        equipment = {"weapon": None, "armor": None}

    player['inventory'] = inventory
    player['equipment'] = equipment

    attack, defense = calc_stats(player)
    player['attack_final'] = attack
    player['defense_final'] = defense

    return jsonify(player), 200


@app.route('/create-hero', methods=['POST'])
@login_required
def create_hero():
    """Создать героя можно только если у тебя ещё нет персонажа.
       Для простоты делаем это по сессии: если у user_id уже есть герой — ошибка.
       В твоём случае можно сделать отдельный эндпоинт /register без сессии.
    """
    data = request.get_json() or {}
    cls = (data.get('class') or data.get('cls') or '').strip().capitalize()
    name = (data.get('name') or '').strip()

    if not cls or not name:
        return jsonify({"error": "Поля 'name' и 'class' обязательны"}), 400

    stats = get_class_stats(cls)
    if not stats:
        allowed = list(class_stats.keys())
        return jsonify({"error": "Недопустимый класс", "allowed": allowed}), 400

    conn = get_db()
    cur = conn.cursor()

    # Проверяем, есть ли уже герой у этого пользователя (по сессии)
    cur.execute("SELECT id FROM players WHERE user_id = ?", (g.user['id'],))  # предполагаем, что ты добавишь user_id в players
    if cur.fetchone():
        conn.close()
        return jsonify({"error": "У вас уже есть персонаж"}), 409

    # Проверяем уникальность ника
    cur.execute("SELECT id FROM players WHERE name = ?", (name,))
    if cur.fetchone():
        conn.close()
        return jsonify({"error": "Ник уже занят"}), 409

    cur.execute('''
        INSERT INTO players (name, class, attack, defense, max_hp, current_hp, inventory_json, equipment_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        name,
        cls,
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
        "class": cls,
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


@app.route('/status', methods=['POST'])
@login_required
def status():
    # В продакшене лучше не передавать player_id, а брать из сессии/g.user
    data = request.get_json() or {}
    player_name = (data.get('player_id') or g.user['name']).strip()

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
    except: inventory = []
    try:
        equipment = json.loads(row['equipment_json'] or '{}')
    except: equipment = {"weapon": None, "armor": None}

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
        "equipment": equipment,
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


# -----------------------------------------------------------------------------
# Чат + Админ‑команды (в стиле Lineage: /give Player1 adena 5000)
# -----------------------------------------------------------------------------
@app.route('/chat/history', methods=['GET'])
@login_required
def chat_history():
    limit = min(int(request.args.get('limit', 50)), 100)
    conn = get_db()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT player_name, message, type, created_at
        FROM chat_messages
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()

    messages = [
        {
            'player': r['player_name'],
            'message': r['message'],
            'type': r['type'],
            'time': r['created_at']
        }
        for r in reversed(rows)
    ]
    return jsonify(messages)


@app.route('/api/chat/send', methods=['POST'])
def api_chat_send():
    data = request.get_json() or {}
    player_id = data.get('player_id')
    message = (data.get('message') or '').strip()

    # Простая валидация
    if not player_id:
        return jsonify({'error': 'player_id обязателен'}), 400
    if not message:
        return jsonify({'error': 'Пустое сообщение'}), 400

    sender_name = f"Игрок #{player_id}"

    # Добавляем сообщение
    CHAT_MESSAGES.append({
        'sender': sender_name,
        'text': message,
        'ts': time.time()
    })

    # Храним только последние N сообщений
    if len(CHAT_MESSAGES) > MAX_CHAT_HISTORY:
        CHAT_MESSAGES[:] = CHAT_MESSAGES[-MAX_CHAT_HISTORY:]

    return jsonify({'status': 'ok'})

@app.route('/api/chat/messages')
def api_chat_messages():
    # Возвращаем последние 50 сообщений
    return jsonify({'messages': CHAT_MESSAGES[-50:]})

def handle_command(admin_name, command_text):
    parts = command_text.split()
    if len(parts) < 2:
        return {'error': 'Неверная команда', 'is_command_result': True}

    cmd = parts[1].lower()

    # Проверка прав (на всякий случай, хотя эндпоинт защищён декоратором)
    if not is_player_admin(admin_name):
        return {'error': 'У вас нет прав администратора', 'is_command_result': True}

    if cmd == 'give':
        return handle_give_command(parts, admin_name)

    return {'error': f'Неизвестная команда: {cmd}', 'is_command_result': True}


def is_player_admin(name):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT is_admin FROM players WHERE name = ?", (name,))
    row = cur.fetchone()
    conn.close()
    return row is not None and row[0] == 1

def handle_give_command(parts, admin_name):
    if len(parts) < 4:
        return {
            'error': 'Формат: /give <target> adena <amount> или /give <target> item <id>',
            'is_command_result': True
        }

    target_name = parts[2]
    mode = parts[3].lower()

    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("SELECT id, adenas, inventory_json FROM players WHERE name = ?", (target_name,))
        row = cur.fetchone()
        if not row:
            return {'error': f'Игрок {target_name} не найден', 'is_command_result': True}

        target_id, current_adenas, inventory_json = row

        if mode == 'adena':
            if len(parts) < 5:
                return {'error': 'Укажите количество аден: /give <target> adena <amount>', 'is_command_result': True}
            try:
                amount = int(parts[4])
                if amount <= 0:
                    return {'error': 'Количество аден должно быть положительным', 'is_command_result': True}
            except ValueError:
                return {'error': 'Некорректное число аден', 'is_command_result': True}

            new_adenas = current_adenas + amount
            cur.execute("UPDATE players SET adenas = ? WHERE id = ?", (new_adenas, target_id))
            conn.commit()
            return {
                'success': True,
                'message': f'{admin_name} выдал игроку {target_name} {amount} аден. Теперь у него {new_adenas} аден.',
                'is_command_result': True
            }

        elif mode == 'item':
            if len(parts) < 5:
                return {'error': 'Укажите ID предмета: /give <target> item <id>', 'is_command_result': True}
            try:
                item_id = int(parts[4])
            except ValueError:
                return {'error': 'ID предмета должен быть числом', 'is_command_result': True}

            if item_id not in ITEMS_DB:
                return {'error': f'Предмет с ID {item_id} не существует', 'is_command_result': True}

            try:
                inventory = json.loads(inventory_json or '[]')
            except Exception:
                inventory = []

            inventory.append(item_id)
            inventory_str = json.dumps(inventory)

            cur.execute("UPDATE players SET inventory_json = ? WHERE id = ?", (inventory_str, target_id))
            conn.commit()

            item_name = ITEMS_DB[item_id]['name']
            return {
                'success': True,
                'message': f'{admin_name} выдал игроку {target_name} предмет "{item_name}" (ID: {item_id})',
                'is_command_result': True
            }
        else:
            return {'error': 'Режим должен быть "adena" или "item"', 'is_command_result': True}

    except Exception as e:
        logger.exception(f"Ошибка в /give: {e}")
        return {'error': 'Внутренняя ошибка при выдаче', 'is_command_result': True}
    finally:
        conn.close()
@app.route('/fight', methods=['POST'])
@login_required
def fight():
    data = request.get_json() or {}
    player_name = (data.get('player_id') or g.user['name']).strip()

    if not player_name:
        return jsonify({'success': False, 'message': 'Имя игрока обязательно'}), 400

    conn = get_db()
    cur = conn.cursor()

    # Получаем игрока
    cur.execute("""
        SELECT id, name, class, level, exp, next_level_exp,
               adenas, attack, defense, max_hp, current_hp,
               inventory_json, equipment_json
        FROM players
        WHERE name = ?
    """, (player_name,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return jsonify({'success': False, 'message': 'Игрок не найден'}), 404

    # Превращаем строку в объекты
    try:
        inventory = json.loads(row['inventory_json'] or '[]')
    except:
        inventory = []
    try:
        equipment = json.loads(row['equipment_json'] or '{}')
    except:
        equipment = {"weapon": None, "armor": None}

    hero = {
        "id": row["id"],
        "name": row["name"],
        "class": row["class"],
        "level": row["level"],
        "exp": row["exp"],
        "next_level_exp": row["next_level_exp"],
        "aden": row["adenas"],
        "attack_base": row["attack"],
        "defense_base": row["defense"],
        "max_hp": row["max_hp"],
        "current_hp": row["current_hp"],
        "inventory": inventory,
        "equipment": equipment,
    }

    # Если мёртв — воскрешаем с половиной HP и не даём начать бой сразу
    if hero['current_hp'] <= 0:
        new_hp = max(1, hero['max_hp'] // 2)
        cur.execute("UPDATE players SET current_hp = ? WHERE id = ?", (new_hp, hero['id']))
        conn.commit()
        conn.close()
        return jsonify({
            'success': False,
            'message': f'Ты был мёртв. Ты воскрес с {new_hp} HP. Попробуй снова.'
        }), 200

    # Считаем финальные статы
    attack, defense = calc_stats(hero)

    # Параметры моба (в будущем можно брать по локации)
    mob_hp = random.randint(80, 120)
    mob_attack = random.randint(12, 22)
    mob_defense = random.randint(4, 8)

    log = []
    log.append(f'⚔️ Ты выходишь на бой против монстра (HP: {mob_hp}, ATK: {mob_attack}, DEF: {mob_defense})')

    round_num = 1
    max_rounds = 30
    while mob_hp > 0 and hero['current_hp'] > 0 and round_num <= max_rounds:
        log.append(f'\n--- Раунд {round_num} ---')

        # Ход игрока
        dmg_to_mob = max(1, int((attack - mob_defense) * random.uniform(0.8, 1.2)))
        mob_hp -= dmg_to_mob
        log.append(f'Ты наносишь {dmg_to_mob} урона. У монстра осталось {max(0, mob_hp)} HP.')

        if mob_hp <= 0:
            break

        # Ход моба
        dmg_to_player = max(1, int((mob_attack - defense) * random.uniform(0.8, 1.2)))
        hero['current_hp'] -= dmg_to_player
        log.append(f'Монстр бьёт тебя на {dmg_to_player} урона. У тебя осталось {max(0, hero["current_hp"])} HP.')

        round_num += 1

    won = mob_hp <= 0 and hero['current_hp'] > 0

    reward_aden = random.randint(50, 150)
    loot_chance = random.random()
    loot_item_id = None
    if loot_chance > 0.6:
        loot_item_id = random.choice(list(ITEMS_DB.keys()))
        hero['inventory'].append(loot_item_id)
        log.append(f'🎒 С монстра выпал предмет с ID {loot_item_id}! Добавлен в инвентарь.')

    hero['aden'] += reward_aden
    log.append(f'💰 Ты получил {reward_aden} Аденов.')

    exp_gain = random.randint(30, 70)
    hero['exp'] += exp_gain
    log.append(f'✨ Ты получил {exp_gain} EXP.')

    level_up = False
    while hero['exp'] >= hero['next_level_exp']:
        hero['level'] += 1
        hero['exp'] -= hero['next_level_exp']
        hero['next_level_exp'] = int(hero['next_level_exp'] * 1.4)
        hero['max_hp'] += 20
        hero['current_hp'] = min(hero['current_hp'], hero['max_hp'])
        level_up = True
        log.append(f'🎉 Уровень повышен! Теперь ты {hero["level"]} уровня!')

    # Сохраняем всё обратно в БД
    inventory_str = json.dumps(hero['inventory'])
    equipment_str = json.dumps(hero['equipment'])

    cur.execute('''
        UPDATE players
        SET level = ?,
            exp = ?,
            next_level_exp = ?,
            adenas = ?,
            max_hp = ?,
            current_hp = ?,
            inventory_json = ?,
            equipment_json = ?
        WHERE id = ?
    ''', (
        hero['level'],
        hero['exp'],
        hero['next_level_exp'],
        hero['aden'],
        hero['max_hp'],
        hero['current_hp'],
        inventory_str,
        equipment_str,
        hero['id']
    ))
    conn.commit()
    conn.close()

    result_message = 'Победа!' if won else 'Ты проиграл.'
    if hero['current_hp'] <= 0:
        result_message = 'Ты погиб в бою…'

    return jsonify({
        'success': won,
        'message': result_message,
        'log': log,
        'player': {
            'name': hero['name'],
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
        },
        'mob': {
            'hp_left': max(0, mob_hp),
            'initial_hp': mob_hp + sum(int(l.split()[3]) for l in log if 'наносишь' in l),  # грубая эвристика для примера
        },
    })
@app.route('/admin/players', methods=['GET'])
@admin_required
def admin_players():
    conn = get_db()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, class, level, adenas, is_admin, created_at
        FROM players
        ORDER BY id
    """)
    rows = cur.fetchall()
    conn.close()

    players = [
        {
            'id': r['id'],
            'name': r['name'],
            'class': r['class'],
            'level': r['level'],
            'adenas': r['adenas'],
            'is_admin': bool(r['is_admin']),
            'created_at': r['created_at'],
        }
        for r in rows
    ]

    return jsonify({
        'success': True,
        'admin': g.user['name'],
        'players': players,
    })
