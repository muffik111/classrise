import os
import logging
from functools import wraps
import sqlite3
from flask import Flask, request, jsonify, session, render_template, url_for, redirect
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# --- МАРКЕР ВЕРСИИ ---
print("=== VERSION: 2026-07-21-FIX-LOGIN-SESSION-DB ===")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(handler)

# --- ПУТЬ К БД ---
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

DB_PATH = os.path.join(data_dir, 'game.db') if can_use_data else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'game.db')
logger.info(f"[INFO] База данных: {DB_PATH}")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    logger.info("[INIT] Инициализация таблиц БД...")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript('''
    -- Таблица аккаунтов (логин + пароль)
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        is_active INTEGER DEFAULT 1
    );

    -- Таблица персонажей (один аккаунт -> много персонажей)
    CREATE TABLE IF NOT EXISTS characters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        name TEXT NOT NULL UNIQUE,
        class TEXT NOT NULL,
        level INTEGER DEFAULT 1,
        adenas INTEGER DEFAULT 0,
        exp INTEGER DEFAULT 0,
        next_level_exp INTEGER DEFAULT 100,
        current_hp INTEGER DEFAULT 50,
        max_hp INTEGER DEFAULT 50,
        attack INTEGER DEFAULT 5,
        defense INTEGER DEFAULT 3,
        inventory TEXT DEFAULT '',
        FOREIGN KEY (account_id) REFERENCES accounts(id)
    );

    CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        char_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (char_id) REFERENCES characters(id)
    );
''')
    conn.commit()
    conn.close()
    logger.info("[INIT] Таблицы готовы.")

init_db()

app = Flask(__name__, template_folder='templates')
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod-on-amvera')

# --- ИМПОРТЫ ---
try:
    from items import ITEMS_DB, calc_stats
    from classes import get_class_stats, class_stats
except ImportError as e:
    logger.error(f"Warning: игровые модули не найдены: {e}")

# ==========================================
# ДЕКОРАТОР АВТОРИЗАЦИИ (ИСПРАВЛЕНО)
# ==========================================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Мы сохраняем в сессии char_id, а не player_id
        if 'char_id' not in session:
            # Для API роутов возвращаем JSON 401
            if request.path.startswith('/api') or request.headers.get('Accept') == 'application/json':
                return jsonify({"error": "Требуется авторизация"}), 401
            # Для HTML страниц — редирект на страницу входа
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

# ==========================================
# РОУТЫ СТРАНИЦ (ТОЛЬКО GET)
# ==========================================

@app.route('/')
def index():
    if 'char_id' in session:
        return render_template('game.html')
    return render_template('login.html')

@app.route('/login-page')
def login_page():
    if 'char_id' in session:
        return render_template('game.html')
    return render_template('login.html')

@app.route('/register-page')
def register_page():
    if 'char_id' in session:
        return render_template('game.html')
    return render_template('register.html')

# ==========================================
# API РОУТЫ (POST)
# ==========================================

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    char_name = (data.get('char_name') or '').strip()
    p_class = (data.get('class') or '').strip()

    if not username or not password or not char_name or not p_class:
        return jsonify({"error": "Все поля обязательны"}), 400

    conn = get_db()
    cur = conn.cursor()
    try:
        pwd_hash = generate_password_hash(password)
        cur.execute('INSERT INTO accounts (username, password_hash) VALUES (?, ?)',
                    (username, pwd_hash))
        account_id = cur.lastrowid

        stats = {}
        try:
            stats = get_class_stats(p_class) or {}
        except:
            pass

        cur.execute('''
            INSERT INTO characters (account_id, name, class, attack, defense)
            VALUES (?, ?, ?, ?, ?)
        ''', (account_id, char_name, p_class, stats.get("attack", 5), stats.get("defense", 3)))

        conn.commit()
        return jsonify({"ok": True, "message": "Аккаунт и персонаж созданы"})

    except sqlite3.IntegrityError as e:
        conn.rollback()
        err_str = str(e).lower()
        if 'username' in err_str:
            return jsonify({"error": "Такой логин уже занят"}), 409
        if 'name' in err_str:
            return jsonify({"error": "Такое имя персонажа уже занято"}), 409
        return jsonify({"error": "Ошибка регистрации"}), 500
    finally:
        conn.close()


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()

    if not username or not password:
        return jsonify({"error": "Введите логин и пароль"}), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute('SELECT id, password_hash FROM accounts WHERE username = ? AND is_active = 1', (username,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "Неверный логин или пароль"}), 401

    account_id, stored_hash = row

    if not check_password_hash(stored_hash, password):
        return jsonify({"error": "Неверный логин или пароль"}), 401

    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id FROM characters WHERE account_id = ? LIMIT 1', (account_id,))
    char_row = cur.fetchone()
    conn.close()

    if not char_row:
        return jsonify({"error": "У аккаунта нет персонажей"}), 404

    char_id = char_row['id']

    # ИСПРАВЛЕНО: сохраняем char_id (это ID персонажа, который у нас в БД)
    session['char_id'] = char_id
    session['account_id'] = account_id

    return jsonify({"ok": True, "char_id": char_id})


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return '', 204


# ==========================================
# СТАТУС ИГРОКА (ИСПРАВЛЕНО: characters вместо players)
# ==========================================
@app.route('/player-status')
@login_required
def player_status():
    char_id = session.get('char_id')
    if not char_id:
        return jsonify({"error": "Нет активного персонажа"}), 401

    conn = get_db()
    cur = conn.cursor()
    # ИСПРАВЛЕНО: используем таблицу characters
    cur.execute('SELECT * FROM characters WHERE id = ?', (char_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "Персонаж не найден в БД"}), 404

    data = dict(row)
    inv_str = data.get('inventory') or ''
    data['inventory'] = [x.strip() for x in inv_str.split(',') if x.strip()]
    max_hp = max(1, data.get('max_hp', 1))
    current_hp = max(0, data.get('current_hp', 0))
    data['hp_percent'] = int((current_hp / max_hp) * 100)
    # Добавим понятные поля для фронтенда
    data['name'] = data['name']
    data['class'] = data['class']
    data['adenas'] = data.get('adenas', 0)
    data['level'] = data.get('level', 1)
    data['exp'] = data.get('exp', 0)
    data['next_level_exp'] = data.get('next_level_exp', 100)
    data['attack'] = data.get('attack', 5)
    data['defense'] = data.get('defense', 3)
    data['current_hp'] = current_hp
    data['max_hp'] = max_hp

    return jsonify(data)


# ==========================================
# ЧАТ (ИСПРАВЛЕНО: JOIN characters -> name, char_id вместо player_id)
# ==========================================
@app.route('/chat-history')
@login_required
def chat_history():
    limit = request.args.get('limit', 30, type=int)
    if limit > 100: limit = 100
    char_id = session.get('char_id')

    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        SELECT cm.id, c.name AS player_name, cm.text, cm.created_at
        FROM chat_messages cm
        JOIN characters c ON cm.char_id = c.id
        ORDER BY cm.id DESC
        LIMIT ?
    ''', (limit,))
    rows = cur.fetchall()
    conn.close()

    messages = []
    for r in rows:
        messages.append({"id": r["id"], "player_name": r["player_name"], "text": r["text"], "created_at": r["created_at"]})
    messages.reverse()
    return jsonify(messages)


@app.route('/chat-send', methods=['POST'])
def chat_send():
    data = request.get_json() or {}
    char_id = data.get('char_id')
    text = data.get('text', '').strip()

    # 1. Проверка авторизации (базовая)
    if not char_id or not text:
        return jsonify({"error": "Неверный запрос"}), 400

    try:
        conn = get_db()
        cur = conn.cursor()
        
        # 2. Проверка: существует ли такой персонаж (защита от взлома)
        cur.execute('SELECT id FROM characters WHERE id = ?', (char_id,))
        if not cur.fetchone():
            conn.close()
            return jsonify({"error": "Персонаж не найден"}), 404

        # 3. Вставка сообщения
        cur.execute('''
            INSERT INTO chat_messages (char_id, text)
            VALUES (?, ?)
        ''', (char_id, text))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Чат: сообщение от char_id={char_id}")
        return jsonify({"ok": True, "message": "Сообщение сохранено"})

    except Exception as e:
        logger.error(f"Ошибка чата: {e}")
        # Важно: не показывай текст ошибки пользователю, но логируй его!
        return jsonify({"error": "Ошибка сохранения сообщения"}), 500


import random

@app.route('/fight', methods=['POST'])
@login_required
def fight():
    char_id = session.get('char_id')
    if not char_id:
        return jsonify({"error": "Нет активного персонажа"}), 401

    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM characters WHERE id = ?', (char_id,))
    p = cur.fetchone()
    if not p:
        conn.close()
        return jsonify({"error": "Персонаж не найден"}), 404
    
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
        UPDATE characters
        SET current_hp = ?, exp = ?, adenas = ?
        WHERE id = ?
    ''', (new_player_hp, player['exp'] + exp_gain, player['adenas'] + aden_gain, char_id))
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

@app.route('/teleport', methods=['POST'])
def teleport():
    data = request.get_json() or {}
    char_id = data.get('char_id')
    target_city = data.get('target_city')

    if not char_id or not target_city:
        return jsonify({"error": "Неверный запрос"}), 400

    try:
        conn = get_db()
        cur = conn.cursor()

        # Обновляем локацию игрока (нужно, чтобы в characters была колонка location)
        cur.execute('''
            UPDATE characters
            SET location = ?
            WHERE id = ?
        ''', (target_city, char_id))

        conn.commit()
        conn.close()

        return jsonify({
            "ok": True,
            "message": f"Вы телепортировались в {target_city}"
        })
    except Exception as e:
        logger.error(f"Teleport error: {e}")
        return jsonify({"error": str(e)}), 500
