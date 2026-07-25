import os
import logging
import traceback
from functools import wraps
import sqlite3
from flask import Flask, request, jsonify, session, render_template, url_for, redirect
from werkzeug.security import generate_password_hash, check_password_hash
import random

# --- МАРКЕР ВЕРСИИ ---
print("=== VERSION: 2026-07-26-FIX-ORDER-LOGIN_REQUIRED-AMVERA-SAFE-DB-INIT ===")

# ==========================================
# НАСТРОЙКА ЛОГГЕРА (ОДИН РАЗ)
# ==========================================
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(handler)

app = Flask(__name__, template_folder='templates')
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod-on-amvera')

# ==========================================
# ПУТИ К БД (AMVERA SAFE)
# ==========================================
data_dir = os.getenv('DATA_DIR', '/data')
if not os.path.exists(data_dir):
    data_dir = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.getenv('DATABASE_PATH', os.path.join(data_dir, 'game.db'))
logger.info(f"[INFO] База данных будет использоваться по пути: {DB_PATH}")

# ==========================================
# ДЕКОРАТОР АВТОРИЗАЦИИ (ОБЯЗАТЕЛЬНО ВЫШЕ ВСЕХ РОУТОВ)
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
# РАБОТА С БД
# ==========================================
def get_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.OperationalError as e:
        logger.error(f"[DB] Не удалось открыть БД по пути {DB_PATH}: {e}")
        return None

def init_db_if_needed():
    """Ленивая инициализация: создаём БД только если файла нет."""
    if os.path.exists(DB_PATH):
        logger.info("[INIT] Файл БД найден, пропускаем создание таблиц.")
        return

    logger.info("[INIT] Создаём БД и таблицы (файл не найден)...")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

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

    # Миграция: добавляем is_admin, если нет
    try:
        cur.execute("ALTER TABLE accounts ADD COLUMN is_admin INTEGER DEFAULT 0")
        logger.info("[MIGRATION] Добавлена колонка is_admin")
    except sqlite3.OperationalError:
        pass  # Колонка уже есть

    conn.commit()
    conn.close()
    logger.info("[INIT] Таблицы успешно созданы.")

# ВАЖНО: НЕ вызываем init_db() сразу при импорте!
# Инициализацию делаем лениво: при первом запросе или явно через отдельный эндпоинт.

# ==========================================
# ИГРОВАЯ ЛОГИКА
# ==========================================
def get_class_stats(cls_name):
    base_stats = {
        "warrior": {"attack": 8, "defense": 6},
        "archer": {"attack": 10, "defense": 4},
        "mage": {"attack": 12, "defense": 3},
        "knight": {"attack": 7, "defense": 8},
        "rogue": {"attack": 9, "defense": 5}
    }
    clean_name = cls_name.lower().strip() if cls_name else ""
    return base_stats.get(clean_name, {"attack": 5, "defense": 3})

try:
    from items import ITEMS_DB, calc_stats
    from classes import get_class_stats as external_get_class_stats
except ImportError as e:
    logger.warning(f"Warning: игровые модули не найдены (это нормально для MVP): {e}")

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
    init_db_if_needed()  # Ленивая инициализация

    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    char_name = (data.get('char_name') or '').strip()
    p_class = (data.get('class') or '').strip()

    if not username or not password or not char_name or not p_class:
        return jsonify({"error": "Все поля обязательны"}), 400

    conn = get_db()
    if conn is None:
        return jsonify({'error': 'Ошибка сервера: не удалось открыть БД'}), 500

    cur = conn.cursor()
    try:
        pwd_hash = generate_password_hash(password)

        cur.execute('SELECT COUNT(*) FROM accounts')
        account_count = cur.fetchone()[0]
        is_admin = 1 if account_count == 0 else 0

        cur.execute(
            'INSERT INTO accounts (username, password_hash, is_admin) VALUES (?, ?, ?)',
            (username, pwd_hash, is_admin)
        )
        account_id = cur.lastrowid

        stats = get_class_stats(p_class)

        cur.execute('''
            INSERT INTO characters (account_id, name, class, attack, defense, location)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (account_id, char_name, p_class, stats.get("attack", 5), stats.get("defense", 3), 'city'))

        conn.commit()
        return jsonify({
            "ok": True,
            "message": "Аккаунт и персонаж созданы",
            "is_admin": bool(is_admin)
        })

    except sqlite3.IntegrityError as e:
        conn.rollback()
        err_str = str(e).lower()
        if 'username' in err_str:
            return jsonify({"error": "Такой логин уже занят"}), 409
        if 'name' in err_str:
            return jsonify({"error": "Такое имя персонажа уже занято"}), 409
        return jsonify({"error": "Ошибка регистрации"}), 500
    finally:
        if conn:
            conn.close()


@app.route('/login', methods=['POST'])
def login():
    init_db_if_needed()

    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()

    if not username or not password:
        return jsonify({"error": "Введите логин и пароль"}), 400

    conn = get_db()
    if conn is None:
        return jsonify({'error': 'Ошибка сервера: не удалось открыть БД'}), 500

    cur = conn.cursor()
    cur.execute('SELECT id, password_hash, is_admin FROM accounts WHERE username = ? AND is_active = 1', (username,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "Неверный логин или пароль"}), 401

    account_id, stored_hash, is_admin = row

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
    if is_admin:
        session['is_admin'] = True

    return jsonify({"ok": True, "char_id": char_id})


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    session.clear()
    return '', 204

# ==========================================
# БОЕВАЯ МЕХАНИКА
# ==========================================
@app.route('/fight-action', methods=['POST'])
@login_required  # Теперь сработает корректно, потому что login_required объявлен выше
def fight_action():
    init_db_if_needed()

    data = request.get_json(silent=True)
    if not data:
        logger.warning("[FIGHT] Получен запрос без JSON")
        return jsonify({"error": "Требуется JSON в теле запроса"}), 400

    char_id = data.get('char_id')
    if char_id is None:
        logger.warning(f"[FIGHT] Нет char_id в запросе: {data}")
        return jsonify({'error': 'Нет ID персонажа'}), 400

    if not isinstance(char_id, int):
        logger.warning(f"[FIGHT] char_id не число: {char_id}")
        return jsonify({'error': 'char_id должен быть целым числом'}), 400

    if session.get('char_id') != char_id:
        logger.warning(f"[FIGHT] Попытка атаки с чужим ID. Session: {session.get('char_id')}, Request: {char_id}")
        return jsonify({'error': 'Несовпадение ID персонажа в сессии'}), 403

    conn = get_db()
    if conn is None:
        logger.error("[FIGHT] Не удалось получить соединение с БД")
        return jsonify({'error': 'Ошибка сервера: нет соединения с БД'}), 500

    cursor = conn.cursor()

    try:
        cursor.execute('SELECT * FROM characters WHERE id = ?', (char_id,))
        char = cursor.fetchone()
        if not char:
            logger.warning(f"[FIGHT] Персонаж не найден: char_id={char_id}")
            return jsonify({'error': 'Персонаж не найден'}), 404

        current_hp = char['current_hp']
        max_hp = char['max_hp']
        attack = char['attack']
        defense = char['defense']
        adenas = char['adenas']
        exp = char['exp']
        location = char['location']
        char_name = char['name']
        char_class = char['class']
        level = char.get('level', 1)
        next_level_exp = char.get('next_level_exp', 100)

        log_messages = []
        is_victory = False
        is_dead = False

        mob_hp = 50
        mob_attack = 12
        mob_defense = 2

        player_dmg = max(1, int(attack * (0.8 + random.random() * 0.4)) - mob_defense)
        mob_hp -= player_dmg
        log_messages.append(f"Вы нанесли мобу {player_dmg} урона. У моба осталось {mob_hp} HP.")

        if mob_hp <= 0:
            is_victory = True
            reward_adenas = 15
            reward_exp = 25
            adenas += reward_adenas
            exp += reward_exp
            log_messages.append(f"🎉 Победа! Моб повержен. Получено: {reward_adenas} аден, {reward_exp} EXP.")
        else:
            mob_dmg = max(1, int(mob_attack * (0.8 + random.random() * 0.4)) - defense)
            current_hp -= mob_dmg
            log_messages.append(f"Моб нанёс вам {mob_dmg} урона. У вас осталось {current_hp} HP.")

            if current_hp <= 0:
                is_dead = True
                penalty = int(adenas * 0.05)
                if penalty > 0:
                    adenas -= penalty
                    log_messages.append(f"💀 Вы погибли! Потеряно {penalty} аден.")
                else:
                    log_messages.append("💀 Вы погибли!")

                current_hp = max_hp
                location = 'city'
                log_messages.append("Вы были телепортированы в город и воскресли.")

        cursor.execute('''
            UPDATE characters
            SET current_hp = ?, adenas = ?, exp = ?, location = ?
            WHERE id = ?
        ''', (current_hp, adenas, exp, location, char_id))
        conn.commit()

        # ... (код до response_data)

        response_data = {
            'player': {
                'id': char['id'],
                'name': char_name,
                'class': char_class,
                'level': level,
                'adenas': adenas,
                'exp': exp,
                'next_level_exp': next_level_exp,
                'current_hp': current_hp,
                'max_hp': max_hp,
                'attack': attack,
                'defense': defense,
                'hp_percent': int((current_hp / max(1, max_hp)) * 100),
                'location': location,
                # Правильно берём инвентарь из строки из БД и превращаем в список
                'inventory': [x.strip() for x in (char['inventory'] or '').split(',') if x.strip()]
            },
            'log': '\n'.join(log_messages),
            'is_victory': is_victory,
            'is_dead': is_dead
        }

        logger.info(f"[FIGHT] Бой завершён для char_id={char_id}: победа={is_victory}, смерть={is_dead}")
        return jsonify(response_data), 200

    except sqlite3.Error as e:
        conn.rollback()
        logger.error(f"[FIGHT] Ошибка БД: {e}")
        return jsonify({'error': 'Ошибка базы данных', 'details': str(e)}), 500
    finally:
        if conn:
            conn.close()



# ==========================================
# СТАТУС ИГРОКА
# ==========================================
@app.route('/player-status')
@login_required
def player_status():
    init_db_if_needed()

    char_id = session.get('char_id')
    if not char_id:
        return jsonify({"error": "Нет активного персонажа"}), 401

    conn = get_db()
    if conn is None:
        return jsonify({'error': 'Ошибка сервера: не удалось открыть БД'}), 500

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

    response_data = {
        'name': data['name'],
        'class': data['class'],
        'adenas': data.get('adenas', 0),
        'level': data.get('level', 1),
        'exp': data.get('exp', 0),
        'next_level_exp': data.get('next_level_exp', 100),
        'attack': data.get('attack', 5),
        'defense': data.get('defense', 3),
        'current_hp': current_hp,
        'max_hp': max_hp,
        'hp_percent': int((current_hp / max_hp) * 100),
        'location': data.get('location', 'city'),
        'inventory': data['inventory']
    }

    return jsonify(response_data)


# ==========================================
# ЧАТ
# ==========================================
@app.route('/chat-history')
@login_required
def chat_history():
    init_db_if_needed()

    limit = request.args.get('limit', 30, type=int)
    if limit > 100:
        limit = 100
    char_id = session.get('char_id')

    conn = get_db()
    if conn is None:
        return jsonify({'error': 'Ошибка сервера: не удалось открыть БД'}), 500

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
    init_db_if_needed()

    data = request.get_json() or {}
    text = data.get('text', '').strip()
    char_id = session.get('char_id')

    if not text:
        return jsonify({"error": "Сообщение не может быть пустым"}), 400

    try:
        conn = get_db()
        if conn is None:
            return jsonify({'error': 'Ошибка сервера: не удалось открыть БД'}), 500

        cur = conn.cursor()
        cur.execute('SELECT id FROM characters WHERE id = ?', (char_id,))
        if not cur.fetchone():
            conn.close()
            return jsonify({"error": "Персонаж не найден"}), 404

        cur.execute('INSERT INTO chat_messages (char_id, text) VALUES (?, ?)', (char_id, text))
        conn.commit()
        conn.close()

        logger.info(f"Чат: сообщение от char_id={char_id}")
        return jsonify({"ok": True, "message": "Сообщение сохранено"})
    except Exception as e:
        logger.error(f"Ошибка чата: {e}")
        return jsonify({"error": "Ошибка сохранения сообщения"}), 500


# ==========================================
# ТЕЛЕПОРТАЦИЯ
# ==========================================
@app.route('/teleport', methods=['POST'])
@login_required
def teleport():
    init_db_if_needed()

    data = request.get_json() or {}
    target_city = data.get('target_city')
    char_id = session.get('char_id')

    if not target_city:
        return jsonify({"error": "Укажите город для телепортации"}), 400

    allowed_locations = ['city', 'forest', 'cave', 'dungeon', 'town_gate']
    if target_city not in allowed_locations:
        return jsonify({"error": "Недопустимая локация"}), 403

    try:
        conn = get_db()
        if conn is None:
            return jsonify({'error': 'Ошибка сервера: не удалось открыть БД'}), 500

        cur = conn.cursor()
        cur.execute('''
            UPDATE characters
            SET location = ?
            WHERE id = ?
        ''', (target_city, char_id))
        conn.commit()
        conn.close()

        logger.info(f"Телепорт: char_id={char_id} → {target_city}")
        return jsonify({
            "ok": True,
            "message": f"Вы телепортировались в {target_city}"
        })
    except Exception as e:
        logger.error(f"Teleport error: {e}")
        return jsonify({"error": str(e)}), 500


# ==========================================
# СОХРАНЕНИЕ РЕЗУЛЬТАТА БОЯ (СЕРВЕРНАЯ ПРОВЕРКА)
# ==========================================
@app.route('/player-death', methods=['POST'])
def player_death():
    init_db_if_needed()

    data = request.get_json()
    char_id = data.get('char_id')
    penalty = data.get('penalty', 0)

    if char_id is None or not isinstance(char_id, int):
        return jsonify({"error": "Требуется корректный char_id"}), 400

    conn = get_db()
    if conn is None:
        return jsonify({'error': 'Ошибка сервера: не удалось открыть БД'}), 500

    cur = conn.cursor()

    cur.execute('SELECT max_hp FROM characters WHERE id = ?', (char_id,))
    row = cur.fetchone()
    max_hp = row['max_hp'] if row else 50

    cur.execute(
        'UPDATE characters SET adenas = adenas - ?, current_hp = ? WHERE id = ?',
        (penalty, max_hp, char_id)
    )

    cur.execute('UPDATE characters SET location = ? WHERE id = ?', ('city', char_id))

    conn.commit()
    conn.close()

    return jsonify({
        'ok': True,
        'message': 'Вы погибли и возродились в городе.',
        'current_hp': max_hp
    })


@app.route('/fight-result', methods=['POST'])
def fight_result():
    init_db_if_needed()

    data = request.get_json()
    char_id = data.get('char_id')
    final_adenas = data.get('final_adenas')
    final_exp = data.get('final_exp')

    if char_id is None or final_adenas is None or final_exp is None:
        return jsonify({"error": "Требуется char_id, final_adenas, final_exp"}), 400

    conn = get_db()
    if conn is None:
        return jsonify({'error': 'Ошибка сервера: не удалось открыть БД'}), 500

    cur = conn.cursor()
    cur.execute(
        'UPDATE characters SET adenas = ?, exp = ? WHERE id = ?',
        (final_adenas, final_exp, char_id)
    )
    conn.commit()
    conn.close()

    return jsonify({'ok': True})


# ==========================================
# АДМИН-КОМАНДА /give
# ==========================================
@app.route('/give', methods=['POST'])
@login_required
def give_command():
    init_db_if_needed()

    char_id = session.get('char_id')
    if not session.get('is_admin'):
        return jsonify({"error": "Нет прав администратора"}), 403

    amount = request.args.get('amount', type=int)
    target_name = request.args.get('target_name', '').strip()

    if amount is None or amount <= 0 or not target_name:
        return jsonify({
            "error": "Параметры: amount (число > 0) и target_name (имя персонажа)"
        }), 400

    try:
        conn = get_db()
        if conn is None:
            return jsonify({'error': 'Ошибка сервера: не удалось открыть БД'}), 500

        cur = conn.cursor()
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
# ПРОКАЧКА (ДЛЯ АДМИНА/ТЕСТОВ)
# ==========================================
@app.route('/player-levelup', methods=['POST'])
@login_required
def player_levelup():
    init_db_if_needed()

    char_id = session.get('char_id')
    exp_add = request.args.get('exp_add', type=int, default=0)

    if exp_add <= 0:
        return jsonify({"error": "exp_add должен быть > 0"}), 400

    try:
        conn = get_db()
        if conn is None:
            return jsonify({'error': 'Ошибка сервера: не удалось открыть БД'}), 500

        cur = conn.cursor()
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

        while new_exp >= next_level_exp:
            level += 1
            level_up_count += 1
            new_exp -= next_level_exp
            next_level_exp = int(next_level_exp * 1.2)
            if next_level_exp < 100:
                next_level_exp = 100

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


# ==========================================
# ТОЧКА ВХОДА ДЛЯ AMVERA
# ==========================================
if __name__ == '__main__':
    # Только для локальной отладки
    app.run(host='0.0.0.0', port=5000, debug=True)
