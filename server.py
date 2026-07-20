import os
import logging
from functools import wraps
import sqlite3
from flask import Flask, request, jsonify, session, g, render_template

# --- ЛОГИРОВАНИЕ ---
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(handler)

# --- ПУТЬ К БД (Amvera /data или локально) ---
data_dir = '/data'
can_use_data = False

if os.path.exists(data_dir):
    try:
        test_file = os.path.join(data_dir, '.amvera_check')
        with open(test_file, 'w') as f:
            f.write('check')
        os.remove(test_file)
        can_use_data = True
    except Exception:
        can_use_data = False

if can_use_data:
    DB_PATH = os.path.join(data_dir, 'game.db')
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DB_PATH = os.path.join(BASE_DIR, 'game.db')

logger.info(f"[INFO] База данных будет использоваться по пути: {DB_PATH}")

# --- ФУНКЦИИ БД ---
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    logger.info("[INIT] Инициализация таблиц базы данных...")
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
    logger.info("[INIT] Таблицы БД проверены/созданы.")

init_db()

# --- СОЗДАНИЕ ПРИЛОЖЕНИЯ ---
app = Flask(__name__, template_folder='templates')
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod-on-amvera')

# --- ИМПОРТЫ ИГР. МОДУЛЕЙ ---
try:
    from items import ITEMS_DB, calc_stats
    from classes import get_class_stats, class_stats
except ImportError as e:
    logger.error(f"Ошибка импорта игровых модулей: {e}")
    # Если файлов нет — сервер запустится, но игровые механики будут падать.
    # Для теста можно временно заглушить, но на Amvera эти файлы должны быть в репозитории.

# --- ДЕКОРАТОР АВТОРИЗАЦИИ ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'player_id' not in session:
            return jsonify({"error": "Требуется авторизация"}), 401
        return f(*args, **kwargs)
    return decorated_function

# --- РОУТЫ ---

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    p_class = (data.get('class') or '').strip()  # именно 'class', как в JSON

    if not name or not p_class:
        return jsonify({"error": "Имя и класс обязательны"}), 400

    conn = get_db()
    cur = conn.cursor()
    try:
        stats = {}
        try:
            stats = get_class_stats(p_class) or {}
        except:
            pass

        cur.execute('''
            INSERT INTO players (name, class, attack, defense)
            VALUES (?, ?, ?, ?)
        ''', (name, p_class, stats.get("attack", 5), stats.get("defense", 3)))
        player_id = cur.lastrowid
        conn.commit()
        session['player_id'] = player_id
        return jsonify({"ok": True, "player_id": player_id, "name": name, "class": p_class})
    except sqlite3.IntegrityError:
        conn.rollback()
        return jsonify({"error": "Игрок с таким именем уже существует"}), 409
    finally:
        conn.close()

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()

    if not name:
        return jsonify({"error": "Введите имя"}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id FROM players WHERE name = ?', (name,))
    row = cur.fetchone()
    conn.close()

    if row:
        session['player_id'] = row['id']
        return jsonify({"ok": True, "player_id": row['id'], "name": name})
    else:
        return jsonify({"error": "Игрок не найден"}), 404

@app.route('/player-status')
@login_required
def player_status():
    player_id = session.get('player_id')
    if not player_id:
        return jsonify({"error": "Нет сессии"}), 401

    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM players WHERE id = ?', (player_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "Игрок не найден в БД"}), 404

    data = dict(row)
    inv_str = data.get('inventory') or ''
    data['inventory'] = [x.strip() for x in inv_str.split(',') if x.strip()]
    max_hp = max(1, data.get('max_hp', 1))
    current_hp = max(0, data.get('current_hp', 0))
    data['hp_percent'] = int((current_hp / max_hp) * 100)
    return jsonify(data)

@app.route('/chat-history')
@login_required
def chat_history():
    limit = request.args.get('limit', 30, type=int)
    if limit > 100:
        limit = 100
    player_id = session.get('player_id')

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
    messages.reverse()
    return jsonify(messages)

@app.route('/chat-send', methods=['POST'])
@login_required
def chat_send():
    data = request.get_json() or {}
    text = (data.get('message') or '').strip()
    if not text:
        return jsonify({"error": "Пустое сообщение"}), 400

    player_id = session.get('player_id')
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute('INSERT INTO chat_messages (player_id, text) VALUES (?, ?)', (player_id, text))
        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        conn.rollback()
        logger.error(f"Ошибка чата: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

import random

@app.route('/fight', methods=['POST'])
@login_required
def fight():
    player_id = session.get('player_id')
    conn = get_db()
    cur = conn.cursor()

    cur.execute('SELECT * FROM players WHERE id = ?', (player_id,))
    p = cur.fetchone()
    if not p:
        conn.close()
        return jsonify({"error": "Игрок не найден"}), 404
    
    player = dict(p)
    mob_hp_start = 50
    mob_attack = 8
    current_mob_hp = session.get('mob_hp')

    if current_mob_hp is None or current_mob_hp <= 0:
        current_mob_hp = mob_hp_start
        session['mob_hp'] = current_mob_hp
        session['fight_started'] = True

    damage_done = max(1, player['attack'] + random.randint(-2, 2))
    new_mob_hp = current_mob_hp - damage_done
    damage_received = max(1, mob_attack + random.randint(-1, 1))
    new_player_hp = player['current_hp'] - damage_received

    is_mob_dead = new_mob_hp <= 0
    exp_gain = aden_gain = 0

    if is_mob_dead:
        exp_gain = 20
        aden_gain = 15
        session.pop('mob_hp', None)
        session.pop('fight_started', None)
    else:
        session['mob_hp'] = new_mob_hp

    cur.execute('''
        UPDATE players
        SET current_hp = ?, exp = ?, adenas = ?
        WHERE id = ?
    ''', (new_player_hp, player['exp'] + exp_gain, player['adenas'] + aden_gain, player_id))
    conn.commit()
    conn.close()

    result = {
        "damage_done": damage_done,
        "damage_received": damage_received,
        "player_hp": new_player_hp,
        "mob_hp": new_mob_hp if not is_mob_dead else 0,
        "is_mob_dead": is_mob_dead,
        "exp_gained": exp_gain,
        "aden_gained": aden_gain
    }
    return jsonify(result)

@app.route('/')
def index():
    return render_template('game.html')

@app.route('/login-page')
def login_page():
    # Если уже залогинен — сразу в игру
    if 'player_id' in session:
        return render_template('game.html')
    return render_template('login.html')

@app.route('/register-page')
def register_page():
    # Если уже залогинен — сразу в игру
    if 'player_id' in session:
        return render_template('game.html')
    return render_template('register.html')


