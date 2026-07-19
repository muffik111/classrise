import os
import json
import logging
from functools import wraps

import sqlite3
from flask import Flask, request, send_from_directory, render_template, jsonify, session, g

# Импорты твоего проекта
from db import get_db, register_player
from items import ITEMS_DB, calc_stats
from classes import get_class_stats, class_stats  # важно: должен быть class_stats

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)
# Если переменная AMVERA есть в окружении — значит, мы в облаке Amvera.
# Там используем папку /data — она сохраняется между перезапусками.
# Локально (на ПК) оставим текущую папку '.'
if "AMVERA" in os.environ:
    DATA_DIR = "/data"
else:
    DATA_DIR = "."

DB_FILE = os.path.join(DATA_DIR, "game.db")
os.makedirs(DATA_DIR, exist_ok=True)

logger.info(f"База данных будет храниться в: {DB_FILE}")

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod-on-amvera')

DB_PATH = 'game.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # чтобы можно было обращаться по именам колонок
    return conn

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript('''
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            class TEXT NOT NULL,
            level INTEGER DEFAULT 1,
            adenas INTEGER DEFAULT 0,
            exp INTEGER DEFAULT 0,
            next_level_exp INTEGER DEFAULT 100,
            current_hp INTEGER DEFAULT 50,
            max_hp INTEGER DEFAULT 50,
            attack INTEGER DEFAULT 5,
            defense INTEGER DEFAULT 3,
            inventory TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id)
        );
    ''')
    conn.commit()
    conn.close()

def migrate_db():
    logger.info("Запуск миграций БД...")
    try:
        conn = get_db()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # 1. Создаём таблицу players, если её нет (это решает твою ошибку)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                class TEXT NOT NULL,
                level INTEGER DEFAULT 1,
                adenas INTEGER DEFAULT 0,
                exp INTEGER DEFAULT 0,
                next_level_exp INTEGER DEFAULT 100,
                current_hp INTEGER NOT NULL,
                max_hp INTEGER NOT NULL,
                attack INTEGER NOT NULL,
                defense INTEGER NOT NULL,
                inventory_json TEXT DEFAULT '[]',
                equipment_json TEXT DEFAULT '{"weapon": null, "armor": null}',
                is_admin INTEGER DEFAULT 0
            )
        ''')
        logger.info("Миграция: таблица players готова (создана или проверена)")

        # 2. Если вдруг старая база без is_admin (редкий случай), добавим колонку
        try:
            cur.execute("PRAGMA table_info(players)")
            cols = [c[1] for c in cur.fetchall()]
            if 'is_admin' not in cols:
                cur.execute("ALTER TABLE players ADD COLUMN is_admin INTEGER DEFAULT 0")
                logger.info("Миграция: добавлена колонка is_admin в players")
        except Exception as e:
            logger.warning(f"Не удалось проверить/добавить is_admin: {e}")

        # 3. Создаём chat_messages, если нет
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

        conn.commit()
    except Exception as e:
        logger.critical(f"Критическая ошибка при миграции БД: {e}", exc_info=True)
    finally:
        try:
            conn.close()
        except:
            pass
    logger.info("Миграции завершены.")


# Запускаем миграции при старте, но не даём им уронить воркер
try:
    migrate_db()
except Exception as e:
    logger.critical(f"migrate_db упал с необработанной ошибкой: {e}", exc_info=True)


# -----------------------------------------------------------------------------
# Сессии и декораторы
# -----------------------------------------------------------------------------
@app.before_request
def load_user():
    g.user = None
    if 'user_id' in session:
        conn = get_db()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT id, name, is_admin FROM players WHERE id = ?", (session['user_id'],))
        row = cur.fetchone()
        conn.close()
        if row:
            g.user = {'id': row[0], 'name': row[1], 'is_admin': bool(row[2])}


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'player_id' not in session:
            return jsonify({"error": "Требуется авторизация"}), 401
        return f(*args, **kwargs)
    return decorated_function



def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not g.user or not g.user['is_admin']:
            return jsonify({'error': 'Нет прав администратора'}), 403
        return f(*args, **kwargs)
    return decorated
# -----------------------------------------------------------------------------
# Эндпоинты: главная, логин, регистрация, статус
# -----------------------------------------------------------------------------
@app.route('/')
def index():
    """Главная страница: логин, если не залогинен; иначе — игра."""
    if not g.user:
        # Показываем форму входа
        return render_template('login.html')
    # Показываем игру
    return render_template('game.html')


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()

    if not name:
        return jsonify({'error': 'Имя обязательно'}), 400

    conn = get_db()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT id, name, class, level, adenas, exp, next_level_exp,
               current_hp, max_hp, attack, defense, inventory_json, equipment_json
        FROM players
        WHERE name = ?
    """, (name,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({'error': 'Игрок не найден'}), 404

    session['user_id'] = row['id']

    player = {
        "id": row["id"],
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
    except Exception:
        inventory = []

    try:
        equipment = json.loads(row['equipment_json'] or '{}')
    except Exception:
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
    data = request.get_json() or {}
    cls = (data.get('class') or data.get('cls') or '').strip().capitalize()
    name = (data.get('name') or '').strip()

    if not cls or not name:
        return jsonify({"error": "Поля 'name' и 'class' обязательны"}), 400

    stats = get_class_stats(cls)
    if not stats:
        allowed = list(class_stats.keys())
        return jsonify({"error": "Недопустимый класс", "allowed": allowed}), 400

    # 🔥 Вызываем функцию из db.py — она сама проверит ник и вернёт id
    player_data = register_player(name, cls, stats)

    if player_data is None:
        # register_player вернул None, значит ник занят
        return jsonify({"error": "Ник уже занят"}), 409

    # Теперь в player_data есть поле "id" — чат сможет его использовать
    return jsonify(player_data), 201

@app.route('/status', methods=['POST'])
@login_required
def status():
    data = request.get_json() or {}
    player_id = data.get('player_id')  # <--- берём player_id как число

    if not player_id:
        # Если player_id не передан, можно использовать текущего из сессии (но лучше требовать явно)
        if g.user:
            player_id = g.user['id']
        else:
            return jsonify({"error": "player_id обязателен"}), 400

    conn = get_db()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    # ИЩЕМ ПО ID, а не по имени
    cur.execute('''
        SELECT id, name, class, level, adenas, exp, next_level_exp,
               current_hp, max_hp, attack, defense,
               inventory_json, equipment_json
        FROM players
        WHERE id = ?
    ''', (player_id,))
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
        "id": row["id"],
        "name": row["name"], "class": row["class"], "level": row["level"],
        "aden": row["adenas"], "exp": row["exp"], "next_level_exp": row["next_level_exp"],
        "current_hp": row["current_hp"], "max_hp": row["max_hp"],
        "attack": row["attack"], "defense": row["defense"],
        "inventory": inventory, "equipment": equipment,
    }

    attack, defense = calc_stats(hero)

    resp = {
        'id': hero['id'],
        'name': hero['name'], 'class': hero['class'], 'level': hero['level'],
        'exp': hero['exp'], 'next_level_exp': hero['next_level_exp'],
        'aden': hero['aden'], 'current_hp': hero['current_hp'], 'max_hp': hero['max_hp'],
        'attack': attack, 'defense': defense,
        'inventory': hero['inventory'], 'equipment': hero['equipment'],
    }
    return jsonify(resp)


# -----------------------------------------------------------------------------
# Чат и админ-команды
# -----------------------------------------------------------------------------

def handle_give_command(parts, admin_name):
    if len(parts) < 4:
        return {'error': 'Формат: /give <target> adena <amount> или /give <target> item <id>', 'is_command_result': True}

    target_name = parts[2]
    mode = parts[3].lower()

    conn = get_db()
    conn.row_factory = sqlite3.Row
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
        logger.error(f"Ошибка в handle_give_command: {e}", exc_info=True)
        return {'error': 'Внутренняя ошибка при выдаче', 'is_command_result': True}

    return {'error': 'Неизвестный режим выдачи', 'is_command_result': True}


def handle_admin_command(admin_name, command_text):
    if command_text.startswith('/'):
        command_text = command_text[1:]

    parts = command_text.split()
    if len(parts) == 0:
        return {'error': 'Пустая команда', 'is_command_result': True}

    cmd = parts[0].lower()
    if cmd == 'give':
        return handle_give_command(parts, admin_name)

    return {'error': f'Неизвестная команда: /{cmd}', 'is_command_result': True}


# --- ОТПРАВКА СООБЩЕНИЯ (game.html: sendChat) ---
@app.route('/chat-send', methods=['POST'])
@login_required
def chat_send():
    data = request.get_json() or {}
    text = (data.get('message') or '').strip()
    if not text:
        return jsonify({"error": "Пустое сообщение"}), 400

    player_id = session.get('player_id')
    if not player_id:
        return jsonify({"error": "Нет сессии"}), 401

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO chat_messages (player_id, text)
            VALUES (?, ?)
        ''', (player_id, text))
        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


# --- ИСТОРИЯ ЧАТА (game.html: loadChatMessages) ---
@app.route('/chat-history')
@login_required
def chat_history():
    limit = request.args.get('limit', 30, type=int)
    if limit > 100:
        limit = 100

    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        SELECT cm.id, p.name AS player_name, cm.text, cm.created_at
        FROM chat_messages cm
        JOIN players p ON cm.player_id = p.id
        ORDER BY cm.id DESC
        LIMIT ?
    ''', (limit,))
    rows = cur.fetchall()
    conn.close()

    messages = []
    for r in rows:
        messages.append({
            "id": r["id"],
            "player_name": r["player_name"],
            "text": r["text"],
            "created_at": r["created_at"]
        })

    # возвращаем в прямом порядке (старые → новые), как удобнее для чата
    messages.reverse()
    return jsonify(messages)

# --- РОУТ СТАТУСА (для game.html) ---
@app.route('/player-status')
@login_required
def player_status():
    player_id = session.get('player_id')
    if not player_id:
        return jsonify({"error": "Нет сессии"}), 401

    conn = get_db()
    cur = conn.cursor()
    # Важно: выбирай ровно те поля, которые ожидает game.html
    cur.execute('''
        SELECT id, name, class, level, adenas, exp, next_level_exp,
               current_hp, max_hp, attack, defense, inventory
        FROM players WHERE id = ?
    ''', (player_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "Игрок не найден"}), 404

    data = dict(row)
    # inventory в БД может быть строкой через запятую — превращаем в список
    inv_str = data.get('inventory') or ''
    data['inventory'] = [x.strip() for x in inv_str.split(',') if x.strip()]

    # Добавим проценты для полоски HP
    max_hp = data.get('max_hp', 1)
    current_hp = max(0, data.get('current_hp', 0))
    data['hp_percent'] = int(current_hp / max_hp * 100)

    return jsonify(data)

import random

@app.route('/fight', methods=['POST'])
@login_required
def fight():
    player_id = session.get('player_id')
    if not player_id:
        return jsonify({"error": "Нет сессии"}), 401

    conn = get_db()
    cur = conn.cursor()

    # Получаем игрока
    cur.execute('SELECT * FROM players WHERE id = ?', (player_id,))
    p = cur.fetchone()
    if not p:
        conn.close()
        return jsonify({"error": "Игрок не найден"}), 404
    player = dict(p)

    # Простой моб (можно позже вынести в отдельную таблицу mobs)
    mob_hp = 50
    mob_attack = 8

    # Если у игрока уже есть данные о мобе в сессии — можно брать оттуда, пока делаем просто
    # Наносим урон мобу
    damage_done = max(1, player['attack'] + random.randint(-2, 2))
    mob_hp -= damage_done

    # Моб бьёт в ответ
    damage_received = max(1, mob_attack + random.randint(-1, 1))
    new_hp = player['current_hp'] - damage_received

    is_mob_dead = mob_hp <= 0
    if is_mob_dead:
        # Даём опыт и адены
        exp_gain = 20
        aden_gain = 15
        new_exp = player['exp'] + exp_gain
        new_aden = player['adenas'] + aden_gain
    else:
        exp_gain = aden_gain = 0
        new_exp = player['exp']
        new_aden = player['adenas']

    # Сохраняем изменения игрока
    cur.execute('''
        UPDATE players
        SET current_hp = ?, exp = ?, adenas = ?
        WHERE id = ?
    ''', (new_hp, new_exp, new_aden, player_id))

    conn.commit()
    conn.close()

    result = {
        "damage_done": damage_done,
        "damage_received": damage_received,
        "player_hp": new_hp,
        "mob_hp": mob_hp,
        "is_mob_dead": is_mob_dead,
        "exp_gained": exp_gain,
        "aden_gained": aden_gain,
    }
    return jsonify(result)


@app.route('/api/chat/history', methods=['GET'])
@login_required
def api_chat_history():
    limit = request.args.get('limit', 50, type=int)
    if limit < 1 or limit > 200:
        limit = 50

    conn = get_db()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    # ORDER BY id DESC — самые свежие сверху
    cur.execute('''
        SELECT id, player_name, message, type, created_at
        FROM chat_messages
        ORDER BY id DESC
        LIMIT ?
    ''', (limit,))
    rows = cur.fetchall()
    conn.close()

    history = []
    for r in rows:
        history.append({
            'id': r['id'],
            'player_name': r['player_name'],
            'message': r['message'],
            'type': r['type'],
            'created_at': r['created_at']
        })

    # Разворачиваем, чтобы было от старых к новым (как в чате)
    history.reverse()
    return jsonify(history)