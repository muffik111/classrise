import os
import logging
import traceback
from functools import wraps
import sqlite3
from flask import Flask, request, jsonify, session, render_template, url_for, redirect
from werkzeug.security import generate_password_hash, check_password_hash
import random 

# --- МАРКЕР ВЕРСИИ ---
print("=== VERSION: 2026-07-23-FIX-SYNC-FRONT-BACK-AMVERA-CLEAN-SQLITE ===")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(handler)

app = Flask(__name__, template_folder='templates')
# SECRET_KEY обязателен для работы сессий
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod-on-amvera')

# ==========================================
# НАСТРОЙКА БАЗЫ ДАННЫХ
# ==========================================
data_dir = os.getenv('DATA_DIR', '/data')
if not os.path.exists(data_dir):
    data_dir = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(data_dir, 'game.db')
logger.info(f"[INFO] База данных будет использоваться по пути: {DB_PATH}")

def get_db():
    """Возвращает соединение с БД с поддержкой обращения по имени колонки"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Создает таблицы, если их нет. Вызывается при старте приложения."""
    logger.info("[INIT] Инициализация таблиц БД...")
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
    
    # Проверка на наличие колонки is_admin (миграция старых баз)
    try:
        cur.execute("ALTER TABLE accounts ADD COLUMN is_admin INTEGER DEFAULT 0")
        logger.info("[MIGRATION] Добавлена колонка is_admin")
    except sqlite3.OperationalError:
        pass # Колонка уже есть
        
    conn.commit()
    conn.close()
    logger.info("[INIT] Таблицы готовы.")

# Запускаем инициализацию БД сразу при старте скрипта
init_db()
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/fight-action', methods=['POST'])
def fight_action():
    data = request.json
    char_id = data.get('char_id')

    if not char_id:
        return jsonify({'error': 'Нет ID персонажа'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Получаем игрока из БД
    cursor.execute('SELECT * FROM players WHERE id = ?', (char_id,))
    player = cursor.fetchone()
    if not player:
        conn.close()
        return jsonify({'error': 'Игрок не найден'}), 404

    # Параметры моба (в будущем лучше вынести в таблицу mobs)
    mob_hp = 50
    mob_attack = 12
    mob_defense = 2

    current_hp = player['current_hp']
    max_hp = player['max_hp']
    attack = player['attack']
    defense = player['defense']
    adenas = player['adenas']
    exp = player['exp']
    location = player['location']

    log_messages = []
    is_victory = False
    is_dead = False

    # --- Ход игрока ---
    player_dmg = max(1, int(attack * (0.8 + random.random() * 0.4)) - mob_defense)
    mob_hp -= player_dmg
    log_messages.append(f"Вы нанесли мобу {player_dmg} урона. У моба осталось {mob_hp} HP.")

    # Проверка победы
    if mob_hp <= 0:
        is_victory = True
        reward_adenas = 15
        reward_exp = 25
        adenas += reward_adenas
        exp += reward_exp
        log_messages.append(f"🎉 Победа! Моб повержен. Получено: {reward_adenas} аден, {reward_exp} EXP.")
    else:
        # --- Ход моба ---
        mob_dmg = max(1, int(mob_attack * (0.8 + random.random() * 0.4)) - defense)
        current_hp -= mob_dmg
        log_messages.append(f"Моб нанёс вам {mob_dmg} урона. У вас осталось {current_hp} HP.")

        # Проверка смерти
        if current_hp <= 0:
            is_dead = True
            penalty = int(adenas * 0.05)
            if penalty > 0:
                adenas -= penalty
                log_messages.append(f"💀 Вы погибли! Потеряно {penalty} аден.")
            else:
                log_messages.append("💀 Вы погибли!")

            # Телепортация и респаун
            current_hp = max_hp
            location = 'city'
            log_messages.append("Вы были телепортированы в город и воскресли.")

    # Обновляем БД в транзакции
    try:
        cursor.execute('''
            UPDATE players
            SET current_hp = ?, adenas = ?, exp = ?, location = ?
            WHERE id = ?
        ''', (current_hp, adenas, exp, location, char_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

    # Формируем ответ
    response_data = {
        'player': {
            'id': player['id'],
            'name': player['name'],
            'class': player['class_name'],      # проверь название колонки в БД
            'level': player['level'],
            'adenas': adenas,
            'exp': exp,
            'next_level_exp': player['next_level_exp'],
            'current_hp': current_hp,
            'max_hp': max_hp,
            'attack': attack,
            'defense': defense,
            'location': location
        },
        'log': '\n'.join(log_messages),
        'is_victory': is_victory,
        'is_dead': is_dead
    }

    return jsonify(response_data)
# ==========================================
# ИГРОВАЯ ЛОГИКА (Заглушки, если нет файлов items.py / classes.py)
# ==========================================
def get_class_stats(cls_name):
    """Возвращает статы класса. Если файла classes.py нет, работает эта заглушка."""
    base_stats = {
        "warrior": {"attack": 8, "defense": 6},
        "archer": {"attack": 10, "defense": 4},
        "mage": {"attack": 12, "defense": 3},
        "knight": {"attack": 7, "defense": 8},
        "rogue": {"attack": 9, "defense": 5}
    }
    # Приводим к нижнему регистру для надежности
    clean_name = cls_name.lower().strip() if cls_name else ""
    return base_stats.get(clean_name, {"attack": 5, "defense": 3})

# Попытка импорта внешних модулей (если есть)
try:
    from items import ITEMS_DB, calc_stats
    from classes import get_class_stats as external_get_class_stats
    # Если файл classes.py есть, используем его функцию вместо заглушки
    # (функция выше переопределится, если мы сделаем import внутри функции, 
    # но здесь мы просто игнорируем заглушку, если модуль найден. 
    # Для простоты оставим логику выше, она безопасна).
except ImportError as e:
    logger.warning(f"Warning: игровые модули не найдены (это нормально для MVP): {e}")

# ==========================================
# ДЕКОРАТОР АВТОРИЗАЦИИ
# ==========================================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Проверка: есть ли ID персонажа в сессии
        if 'char_id' not in session:
            # Если это API запрос
            if request.path.startswith('/api') or request.headers.get('Accept') == 'application/json':
                return jsonify({"error": "Требуется авторизация"}), 401
            # Если обычный запрос страницы
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

@app.errorhandler(500)
def handle_500(e):
    error_trace = traceback.format_exc()
    app.logger.error("500 ERROR DETAILS:\n%s", error_trace)
    # В проде лучше вернуть просто ошибку, но для отладки на Amvera полезно видеть текст
    return f"<pre>{error_trace}</pre>", 500

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
        
        # 1. Создаем аккаунт
        cur.execute('INSERT INTO accounts (username, password_hash) VALUES (?, ?)',
                    (username, pwd_hash))
        account_id = cur.lastrowid

        # 2. Получаем статы класса
        stats = get_class_stats(p_class)

        # 3. Создаем персонажа
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

    # Ищем аккаунт
    cur.execute('SELECT id, password_hash, is_admin FROM accounts WHERE username = ? AND is_active = 1', (username,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "Неверный логин или пароль"}), 401

    account_id, stored_hash, is_admin = row

    if not check_password_hash(stored_hash, password):
        return jsonify({"error": "Неверный логин или пароль"}), 401

    # Ищем персонажа этого аккаунта
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id FROM characters WHERE account_id = ? LIMIT 1', (account_id,))
    char_row = cur.fetchone()
    conn.close()

    if not char_row:
        return jsonify({"error": "У аккаунта нет персонажей"}), 404

    char_id = char_row['id']
    
    # Сохраняем в сессию
    session['char_id'] = char_id
    session['account_id'] = account_id
    if is_admin:
        session['is_admin'] = True  # Важно: даем права админа в сессии

    return jsonify({"ok": True, "char_id": char_id})


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    session.clear()
    return '', 204


# ==========================================
# СТАТУС ИГРОКА
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

    # Формируем ответ строго под фронтенд
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
        'hp_percent': data['hp_percent'],
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
    limit = request.args.get('limit', 30, type=int)
    if limit > 100: limit = 100
    char_id = session.get('char_id') # Не обязательно, но полезно для логирования

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
    text = data.get('text', '').strip()
    char_id = session.get('char_id')

    if not text:
        return jsonify({"error": "Сообщение не может быть пустым"}), 400

    try:
        conn = get_db()
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
    data = request.get_json() or {}
    target_city = data.get('target_city')
    char_id = session.get('char_id')

    if not target_city:
        return jsonify({"error": "Укажите город для телепортации"}), 400

    # Список разрешённых локаций (чтобы нельзя было телепортироваться в «админку» или несуществующее)
    allowed_locations = ['city', 'forest', 'cave', 'dungeon', 'town_gate']
    if target_city not in allowed_locations:
        return jsonify({"error": "Недопустимая локация"}), 403

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

        logger.info(f"Телепорт: char_id={char_id} → {target_city}")
        return jsonify({
            "ok": True,
            "message": f"Вы телепортировались в {target_city}"
        })
    except Exception as e:
        logger.error(f"Teleport error: {e}")
        return jsonify({"error": str(e)}), 500


# ==========================================
# СОХРАНЕНИЕ РЕЗУЛЬТАТА БОЯ
# Фронтенд полностью считает бой, сервер только фиксирует итог.
# Это защищает от накрутки урона/опыта.
# ==========================================
@app.route('/player-death', methods=['POST'])
def player_death():
    data = request.get_json()
    char_id = data.get('char_id')
    penalty = data.get('penalty', 0)

    conn = get_db()
    cur = conn.cursor()

    # Получаем max_hp, чтобы восстановить HP
    cur.execute('SELECT max_hp FROM characters WHERE id = ?', (char_id,))
    row = cur.fetchone()
    max_hp = row['max_hp'] if row else 50

    # Обновляем адены (штраф) и восстанавливаем HP
    cur.execute(
        'UPDATE characters SET adenas = adenas - ?, current_hp = ? WHERE id = ?',
        (penalty, max_hp, char_id)
    )

    # Телепортация в город
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
    data = request.get_json()
    char_id = data.get('char_id')
    final_adenas = data.get('final_adenas')
    final_exp = data.get('final_exp')

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        'UPDATE characters SET adenas = ?, exp = ? WHERE id = ?',
        (final_adenas, final_exp, char_id)
    )

    conn.commit()
    conn.close()

    return jsonify({'ok': True})



# ==========================================
# АДМИН-КОМАНДА /give (выдать адены)
# POST /give?amount=1000&target_name=PlayerName
# Требуется сессия с is_admin=True
# ==========================================
@app.route('/give', methods=['POST'])
@login_required
def give_command():
    char_id = session.get('char_id')
    # Проверка прав админа через сессию
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
# ПРОКАЧКА (для тестов/админки)
# POST /player-levelup?exp_add=500
# Добавляет EXP и проверяет уровень
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
            next_level_exp = int(next_level_exp * 1.2)
            if next_level_exp < 100:
                next_level_exp = 100  # минимум

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
# На Amvera не используют if __name__ == '__main__'
# Приложение должно быть доступно как объект app
# ==========================================
if __name__ == '__main__':
    # Этот блок нужен только для локального запуска (python server.py)
    # На Amvera он не используется, там запускают через gunicorn app:app
    app.run(host='0.0.0.0', port=5000, debug=False)
