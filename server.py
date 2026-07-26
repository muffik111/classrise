import os
import logging
import random
import time
import importlib
from functools import wraps

import sqlite3
from flask import Flask, request, jsonify, session, render_template, url_for, redirect
from werkzeug.security import generate_password_hash, check_password_hash

# --- Импорт внешних модулей ---
try:
    from cities import CITIES, is_valid_city, get_city_mob_module
    from items import ITEMS_DB, get_item_by_id
except ImportError as e:
    print(f"[CRITICAL] Не удалось импортировать модули cities/items. Ошибка: {e}")
    print("[HINT] Создай файлы cities.py и items.py в корне проекта и закоммить их в Git.")
    exit(1)

# ==========================================
# НАСТРОЙКА ЛОГГЕРА
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
# ПУТИ К БД
# ==========================================
data_dir = os.getenv('DATA_DIR', '/data')
if not os.path.exists(data_dir):
    data_dir = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.getenv('DATABASE_PATH', os.path.join(data_dir, 'game.db'))
logger.info(f"[INFO] База данных будет использоваться по пути: {DB_PATH}")

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
# РАБОТА С БД
# ==========================================
def get_db():
    conn = sqlite3.connect('classrise.db')
    conn.row_factory = sqlite3.Row  # это критично!
    return conn

def init_db_if_needed():
    # Если файл БД уже есть и таблица characters существует — выходим
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='characters';")
            if cur.fetchone():
                conn.close()
                return
            conn.close()
        except Exception as e:
            logger.error(f"[INIT] Ошибка проверки таблиц: {e}")

    logger.info("[INIT] Создаём БД и таблицы...")
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
        location TEXT DEFAULT 'Аэрдмор',
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

    # Попытка добавить колонку is_admin, если её нет (игнорируем ошибку, если колонка уже есть)
    try:
        cur.execute("ALTER TABLE accounts ADD COLUMN is_admin INTEGER DEFAULT 0")
        logger.info("[MIGRATION] Добавлена колонка is_admin")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()
    logger.info("[INIT] Таблицы успешно созданы.")


def get_mobs_for_city(city_name: str):
    module_name = get_city_mob_module(city_name)
    try:
        module = importlib.import_module(module_name)
        mobs = getattr(module, "MOBS", [])
        return mobs
    except ImportError as e:
        logger.warning(f"[ERROR] Не удалось загрузить мобов для города '{city_name}': {e}")
        return []
    except Exception as e:
        logger.error(f"[ERROR] Ошибка при получении мобов для города '{city_name}': {e}")
        return []


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
    init_db_if_needed()
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

        # ИСПРАВЛЕНИЕ: берем из кортежа
        cur.execute('SELECT COUNT(*) FROM accounts')
        account_count = cur.fetchone()
        is_admin = 1 if account_count == 0 else 0

        cur.execute(
            'INSERT INTO accounts (username, password_hash, is_admin) VALUES (?, ?, ?)',
            (username, pwd_hash, is_admin)
        )
        account_id = cur.lastrowid

        base_stats = {
            "warrior": {"attack": 8, "defense": 6},
            "archer": {"attack": 10, "defense": 4},
            "mage": {"attack": 12, "defense": 3},
            "knight": {"attack": 7, "defense": 8},
            "rogue": {"attack": 9, "defense": 5}
        }
        stats = base_stats.get(p_class.lower(), {"attack": 5, "defense": 3})

        cur.execute('''
            INSERT INTO characters (account_id, name, class, attack, defense, location)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (account_id, char_name, p_class, stats["attack"], stats["defense"], 'Аэрдмор'))

        conn.commit()
        return jsonify({"ok": True, "message": "Аккаунт и персонаж созданы", "is_admin": bool(is_admin)})

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
    try:
        cur.execute('SELECT id, password_hash, is_admin FROM accounts WHERE username = ? AND is_active = 1', (username,))
        row = cur.fetchone()

        if not row:
            return jsonify({"error": "Неверный логин или пароль"}), 401

        account_id, stored_hash, is_admin = row
        if not check_password_hash(stored_hash, password):
            return jsonify({"error": "Неверный логин или пароль"}), 401

        # Ищем персонажа этого аккаунта
        cur.execute('SELECT id FROM characters WHERE account_id = ? LIMIT 1', (account_id,))
        char_row = cur.fetchone()

        if not char_row:
            return jsonify({"error": "У аккаунта нет персонажей"}), 404

        char_id = char_row['id']
        session['char_id'] = char_id
        session['account_id'] = account_id
        if is_admin:
            session['is_admin'] = True

        return jsonify({"ok": True, "char_id": char_id})
    except Exception as e:
        logger.error(f"[LOGIN] Ошибка: {e}")
        return jsonify({"error": "Ошибка сервера"}), 500
    finally:
        conn.close()

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    session.clear()
    return '', 204

# ==========================================
# БОЕВАЯ МЕХАНИКА
# ==========================================
@app.route('/api/fight/start', methods=['POST'])
@login_required
def start_fight():
    char_id = session.get('char_id')
    if not char_id:
        return jsonify({"error": "Нет активного персонажа"}), 401

    conn = get_db()
    if not conn:
        return jsonify({"error": "Ошибка БД"}), 500

    cur = conn.cursor()
    cur.execute("SELECT location FROM characters WHERE id = ?", (char_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "Персонаж не найден"}), 404

    city_name = row["location"]
    mobs = get_mobs_for_city(city_name)

    if not mobs:
        enemy = {"name": "Обычный моб", "hp": 50, "attack": 8, "defense": 2, "adenas": 10, "exp": 20}
    else:
        enemy = random.choice(mobs)

    session["fight_state"] = {
        "enemy": enemy,
        "enemy_hp": enemy["hp"],
        "started_at": time.time()
    }

    return jsonify({
        "ok": True,
        "message": f"Вы вступили в бой с {enemy['name']}!",
        "enemy": {
            "name": enemy["name"],
            "hp": enemy["hp"],
            "max_hp": enemy["hp"]
        }
    })


@app.route('/fight-action', methods=['POST'])
@login_required
def fight_action():
    init_db_if_needed()
    char_id = session.get('char_id')
    if not char_id:
        return jsonify({"error": "Нет активной сессии персонажа"}), 401

    conn = get_db()
    if conn is None:
        return jsonify({'error': 'Ошибка сервера: нет соединения с БД'}), 500

    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM characters WHERE id = ?', (char_id,))
        char = cursor.fetchone()
        if not char:
            return jsonify({'error': 'Персонаж не найден'}), 404

        current_location = char['location']
        mob_data = get_mobs_for_city(current_location)

        if not mob_data:
            mob_data = [
                {"id": 1, "name": "Обычный моб", "hp": 50, "attack": 12, "defense": 2, "adenas": 15, "exp": 25}
            ]
            logger.warning(f"Нет файла мобов для города {current_location}, используются дефолтные мобы.")

        mob = random.choice(mob_data)

        current_hp = max(0, char['current_hp'])
        max_hp = max(1, char['max_hp'])
        attack = max(1, char['attack'])
        defense = max(0, char['defense'])
        adenas = max(0, char['adenas'])
        exp = max(0, char['exp'])
        location = char['location']
        char_name = char['name']
        char_class = char['class']
        level = char.get('level', 1)
        next_level_exp = char.get('next_level_exp', 100)

        inv_str = char['inventory'] or ''
        inventory_list = [x.strip() for x in inv_str.split(',') if x.strip()]

        log_messages = []
        is_victory = False
        is_dead = False

        # Ход игрока
        player_dmg = max(1, int(attack * (0.8 + random.random() * 0.4)) - mob["defense"])
        mob["hp"] -= player_dmg
        log_messages.append(f"⚔️ Вы нанесли {mob['name']} {player_dmg} урона. У моба осталось {mob['hp']} HP.")

        if mob["hp"] <= 0:
            is_victory = True
            adenas += mob["adenas"]
            exp += mob["exp"]
            log_messages.append(f"🎉 Победа! Получено: {mob['adenas']} аден, {mob['exp']} EXP.")
        else:
            # Ход моба
            mob_dmg = max(1, int(mob["attack"] * (0.8 + random.random() * 0.4)) - defense)
            current_hp = max(0, current_hp - mob_dmg)
            log_messages.append(f"👹 {mob['name']} нанёс вам {mob_dmg} урона. У вас осталось {current_hp} HP.")

            if current_hp <= 0:
                is_dead = True
                penalty = int(adenas * 0.05)
                if penalty > 0:
                    adenas -= penalty
                    log_messages.append(f"💀 Вы погибли! Потеряно {penalty} аден.")
                else:
                    log_messages.append("💀 Вы погибли!")
                current_hp = max_hp
                location = 'Аэрдмор'
                log_messages.append("🏙 Вы были телепортированы в Аэрдмор и воскресли.")

        cursor.execute('''
            UPDATE characters
            SET current_hp = ?, adenas = ?, exp = ?, location = ?
            WHERE id = ?
        ''', (current_hp, adenas, exp, location, char_id))
        conn.commit()

        response_data = {
            'success': True,
            'log': '\n'.join(log_messages),
            'is_victory': is_victory,
            'is_dead': is_dead,
            'player': {
                'id': char_id,
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
                'hp_percent': int((current_hp / max_hp) * 100),
                'location': location,
                'inventory': inventory_list
            },
            'mob': mob
        }
        return jsonify(response_data), 200

    except sqlite3.Error as e:
        conn.rollback()
        logger.error(f"[FIGHT] Критическая ошибка БД: {e}")
        return jsonify({'success': False, 'error': 'Ошибка базы данных', 'log': 'Произошла ошибка сервера.'}), 500
    finally:
        if conn:
            conn.close()

# ==========================================
# ГЛАВНЫЙ ЭНДПОИНТ ДЛЯ ФРОНТЕНДА
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
        'location': data.get('location', 'Аэрдмор'),
        'inventory': data['inventory'],
        'cities': CITIES
    }
    return jsonify(response_data)

# ==========================================
# ЧАТ
# ==========================================

@app.route('/api/chat/new', methods=['GET'])
@login_required
def chat_new():
    init_db_if_needed()
    last_id = request.args.get('last_id', 0, type=int)

    conn = get_db()
    if conn is None:
        return jsonify({'error': 'Ошибка сервера: не удалось открыть БД'}), 500

    cur = conn.cursor()
    # Получаем только новые сообщения после last_id
    cur.execute('''
        SELECT cm.id, c.name AS player_name, cm.text, cm.created_at
        FROM chat_messages cm
        JOIN characters c ON cm.char_id = c.id
        WHERE cm.id > ?
        ORDER BY cm.id ASC
        LIMIT 50
    ''', (last_id,))
    rows = cur.fetchall()
    conn.close()

    messages = []
    for r in rows:
        messages.append({
            "id": r["id"],
            "sender": r["player_name"],
            "text": r["text"],
            "is_system": False,
            "time": r["created_at"]
        })

    # Фронтенд ожидает объект с ключом messages
    return jsonify({"messages": messages})
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

    if not is_valid_city(target_city):
        return jsonify({"error": "Недопустимый город. Выберите из списка."}), 403

    try:
        conn = get_db()
        if conn is None:
            return jsonify({'error': 'Ошибка сервера: не удалось открыть БД'}), 500

        cur = conn.cursor()
        cur.execute('UPDATE characters SET location = ? WHERE id = ?', (target_city, char_id))
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
            SET level = ?, exp = ?, next_level_exp = ?
            WHERE id = ?
        ''', (level, new_exp, next_level_exp, char_id))
        conn.commit()
        conn.close()

        msg = f"Поздравляем! Вы повысили уровень {level_up_count} раз. Теперь ваш уровень: {level}."
        if level_up_count == 0:
            msg = f"Получено {exp_add} EXP. До следующего уровня осталось {next_level_exp - new_exp} EXP."

        return jsonify({
            "ok": True,
            "message": msg,
            "level": level,
            "exp": new_exp,
            "next_level_exp": next_level_exp
        })
    except Exception as e:
        logger.error(f"Levelup error: {e}")
        return jsonify({"error": str(e)}), 500


# ==========================================
# ОТЛАДОЧНЫЙ ЭНДПОИНТ (ТОЛЬКО ДЛЯ РАЗРАБОТКИ)
# ==========================================
@app.route('/debug/reset-player', methods=['POST'])
@login_required
def debug_reset_player():
    init_db_if_needed()
    char_id = session.get('char_id')
    if not char_id:
        return jsonify({"error": "Нет персонажа"}), 401

    try:
        conn = get_db()
        if not conn:
            return jsonify({"error": "Ошибка БД"}), 500

        cur = conn.cursor()
        cur.execute('SELECT max_hp FROM characters WHERE id = ?', (char_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "Персонаж не найден"}), 404

        max_hp = row['max_hp']
        cur.execute('''
            UPDATE characters
            SET current_hp = ?, location = ?
            WHERE id = ?
        ''', (max_hp, 'Аэрдмор', char_id))
        conn.commit()
        conn.close()

        return jsonify({
            "ok": True,
            "message": "Игрок сброшен: HP восстановлен, телепорт в Аэрдмор."
        })
    except Exception as e:
        logger.error(f"Debug reset error: {e}")
        return jsonify({"error": str(e)}), 500


# ==========================================
# ЗАПУСК ПРИЛОЖЕНИЯ
# ==========================================
if __name__ == '__main__':
    # Инициализация БД при старте сервера
    init_db_if_needed()

    # ВАЖНО: на Amvera/Docker не создавай файлы автоматически.
    # Эти файлы должны быть в Git. Блок ниже можно удалить в продакшене.
    if not os.path.exists('cities.py'):
        logger.warning("[CHECK] Файл cities.py не найден! Создай его вручную и закоммить в Git.")
    if not os.path.exists('items.py'):
        logger.warning("[CHECK] Файл items.py не найден! Создай его вручную и закоммить в Git.")

    # Запуск Flask
    # debug=False для продакшена
    app.run(host='0.0.0.0', port=5000, debug=False)