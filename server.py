import os
import logging
from functools import wraps
import sqlite3
from flask import Flask, request, jsonify, session, render_template, url_for, redirect
from werkzeug.security import generate_password_hash, check_password_hash

# --- МАРКЕР ВЕРСИИ ---
print("=== VERSION: 2026-07-22-FIX-SYNC-FRONT-BACK-AMVERA ===")

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
    logger.info("[INIT] Инициализация таблиц БД и миграций...")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Создаём таблицы, если их нет
    cur.executescript('''
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        is_admin INTEGER DEFAULT 0
    );

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
        location TEXT DEFAULT 'city',
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

    # МИГРАЦИЯ 1: добавляем колонку location в characters, если её нет (для старых БД)
    try:
        cur.execute('ALTER TABLE characters ADD COLUMN location TEXT DEFAULT "city"')
        logger.info("[MIGRATION] Добавлена колонка location в characters")
    except sqlite3.OperationalError:
        # Колонка уже существует — это нормально
        pass

    # МИГРАЦИЯ 2: добавляем колонку is_admin в accounts, если её нет
    try:
        cur.execute('ALTER TABLE accounts ADD COLUMN is_admin INTEGER DEFAULT 0')
        logger.info("[MIGRATION] Добавлена колонка is_admin в accounts")
    except sqlite3.OperationalError:
        # Колонка уже существует — это нормально
        pass

    conn.commit()
    conn.close()
    logger.info("[INIT] Таблицы и миграции готовы.")


init_db()

app = Flask(__name__, template_folder='templates')
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod-on-amvera')

try:
    from items import ITEMS_DB, calc_stats
    from classes import get_class_stats, class_stats
except ImportError as e:
    logger.error(f"Warning: игровые модули не найдены: {e}")

# ==========================================
# ДЕКОРАТОР АВТОРИЗАЦИИ
# ==========================================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'char_id' not in session:
            if request.path.startswith('/api') or request.headers.get('Accept') == 'application/json':
                return jsonify({"error": "Требуется авторизация"}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

# ==========================================
# РОУТЫ СТРАНИЦ
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
# API РЕГИСТРАЦИЯ И ВХОД
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
            INSERT INTO characters (account_id, name, class, attack, defense, location)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (account_id, char_name, p_class, stats.get("attack", 5), stats.get("defense", 3), 'city'))

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
    session['char_id'] = char_id
    session['account_id'] = account_id

    return jsonify({"ok": True, "char_id": char_id})


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    session.clear()
    return '', 204


# ==========================================
# СТАТУС ИГРОКА (полностью совпадает с тем, что ждёт game.html)
# ==========================================
@app.route('/player-status')
@login_required
def player_status():
    char_id = session.get('char_id')
    if not char_id:
        return jsonify({"error": "Нет активного персонажа"}), 401

    conn = get_db()
    cur = conn.cursor()
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

    # Поля строго под фронтенд
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
# ЧАТ
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
@login_required
def chat_send():
    data = request.get_json() or {}
    text = data.get('text', '').strip()
    # char_id берём из сессии, а не из JSON — это защита от подмены
    char_id = session.get('char_id')

    if not text:
        return jsonify({"error": "Сообщение не может быть пустым"}), 400

    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Проверка существования персонажа (на всякий случай)
        cur.execute('SELECT id FROM characters WHERE id = ?', (char_id,))
        if not cur.fetchone():
            conn.close()
            return jsonify({"error": "Персонаж не найден"}), 404

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
        return jsonify({"error": "Ошибка сохранения сообщения"}), 500


# ==========================================
# ТЕЛЕПОРТАЦИЯ (теперь корректно пишет в location)
# ==========================================
@app.route('/teleport', methods=['POST'])
@login_required
def teleport():
    data = request.get_json() or {}
    target_city = data.get('target_city')
    char_id = session.get('char_id')

    if not target_city:
        return jsonify({"error": "Укажите город для телепортации"}), 400

    try:
        conn = get_db()
        cur = conn.cursor()

        # Обновляем локацию игрока
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


# ==========================================
# СОХРАНЕНИЕ РЕЗУЛЬТАТА БОЯ (фронтенд считает урон, сервер только сохраняет)
# ==========================================
@app.route('/fight-result', methods=['POST'])
@login_required
def fight_result():
    """
    Фронтенд полностью считает бой (урон, смерть, лут, опыт).
    Этот эндпоинт только сохраняет финальное состояние персонажа в БД.
    Это предотвращает рассинхрон и читерство.
    """
    data = request.get_json() or {}
    char_id = session.get('char_id')

    final_hp = data.get('final_hp')
    final_adenas = data.get('final_adenas')
    final_exp = data.get('final_exp')
    is_dead = data.get('is_dead', False)

    if final_hp is None or final_adenas is None or final_exp is None:
        return jsonify({"error": "Неверные данные"}), 400

    try:
        conn = get_db()
        cur.execute('''
            UPDATE characters
            SET current_hp = ?, adenas = ?, exp = ?
            WHERE id = ?
        ''', (final_hp, final_adenas, final_exp, char_id))

        # Если персонаж умер — сбрасываем HP в max_hp (телепорт и респ делает фронтенд, тут только данные)
        if is_dead:
            # Получаем max_hp из БД, чтобы не доверять фронту
            cur.execute('SELECT max_hp FROM characters WHERE id = ?', (char_id,))
            row = cur.fetchone()
            max_hp_val = row['max_hp'] if row else 50
            cur.execute('UPDATE characters SET current_hp = ? WHERE id = ?', (max_hp_val, char_id))

        conn.commit()
        conn.close()

        return jsonify({
            "ok": True,
            "message": "Результат боя сохранён",
            "final_hp": final_hp,
            "final_adenas": final_adenas,
            "final_exp": final_exp
        })

    except Exception as e:
        logger.error(f"Fight result error: {e}")
        return jsonify({"error": "Ошибка сохранения результата боя"}), 500


# ==========================================
# АДМИН-КОМАНДА /give (выдать адены)
# Формат: POST /give?amount=1000&target_name=PlayerName
# Требует, чтобы у сессии был флаг is_admin=True (можно задать вручную в БД или через отдельный эндпоинт)
# ==========================================
@app.route('/give', methods=['POST'])
@login_required
def give_command():
    char_id = session.get('char_id')
    # Проверка на админа: можно хранить в сессии is_admin, либо проверять по отдельной колонке в accounts
    if not session.get('is_admin'):
        # Для теста можно временно закомментировать эту проверку, но в проде обязательно нужна
        return jsonify({"error": "Нет прав администратора"}), 403

    amount = request.args.get('amount', type=int)
    target_name = request.args.get('target_name', '').strip()

    if amount is None or amount <= 0 or not target_name:
        return jsonify({"error": "Неверные параметры: amount (число > 0) и target_name (имя персонажа)"}), 400

    try:
        conn = get_db()
        cur = conn.cursor()

        # Ищем персонажа по имени
        cur.execute('SELECT id, adenas FROM characters WHERE name = ?', (target_name,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "Персонаж не найден"}), 404

        target_id = row['id']
        old_adenas = row['adenas']
        new_adenas = old_adenas + amount

        cur.execute('UPDATE characters SET adenas = ? WHERE id = ?', (new_adenas, target_id))
        conn.commit()
        conn.close()

        logger.info(f"ADMIN: выдано {amount} аден персонажу {target_name} (было {old_adenas}, стало {new_adenas})")
        return jsonify({
            "ok": True,
            "target_name": target_name,
            "amount": amount,
            "old_adenas": old_adenas,
            "new_adenas": new_adenas
        })
    except Exception as e:
        logger.error(f"Give command error: {e}")
        return jsonify({"error": "Ошибка выполнения команды /give"}), 500


# ==========================================
# ПРОКАЧКА (для тестов/админки)
# POST /player-levelup?exp_add=500
# Просто добавляет EXP и проверяет уровень (без сложной формулы)
# ==========================================
@app.route('/player-levelup', methods=['POST'])
@login_required
def player_levelup():
    char_id = session.get('char_id')
    exp_add = request.args.get('exp_add', type=int, default=0)

    if exp_add <= 0:
        return jsonify({"error": "exp_add должен быть > 0"}), 400

    try:
        conn = get_db()
        cur = conn.cursor()

        # Получаем текущие данные
        cur.execute('SELECT * FROM characters WHERE id = ?', (char_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "Персонаж не найден"}), 404

        current_exp = row['exp']
        next_level_exp = row['next_level_exp']
        level = row['level']

        new_exp = current_exp + exp_add
        level_up_count = 0

        # Простая логика: пока EXP >= next_level_exp — повышаем уровень
        while new_exp >= next_level_exp:
            level += 1
            level_up_count += 1
            new_exp -= next_level_exp
            # Увеличиваем порог для следующего уровня (например, на 20%)
            next_level_exp = int(next_level_exp * 1.2)
            if next_level_exp < 100:
                next_level_exp = 100  # минимум

        # Обновляем персонажа
        cur.execute('''
            UPDATE characters
            SET exp = ?, level = ?, next_level_exp = ?
            WHERE id = ?
        ''', (new_exp, level, next_level_exp, char_id))

        conn.commit()
        conn.close()

        return jsonify({
            "ok": True,
            "level_ups": level_up_count,
            "new_level": level,
            "remaining_exp": new_exp,
            "next_level_exp": next_level_exp
        })
    except Exception as e:
        logger.error(f"Levelup error: {e}")
        return jsonify({"error": "Ошибка прокачки"}), 500
