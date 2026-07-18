import os
import json
import logging
from functools import wraps

import sqlite3
from flask import Flask, request, send_from_directory, jsonify, session, g

# Импорты твоего проекта
from db import get_db
from items import ITEMS_DB, calc_stats
from classes import get_class_stats, class_stats  # важно: должен быть class_stats

DATA_DIR = '.'  # на Amvera лучше не использовать /data без проверки прав
DB_FILE = os.path.join(DATA_DIR, 'game.db')
os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod-on-amvera')


# -----------------------------------------------------------------------------
# Миграции БД (безопасно, не роняют сервер)
# -----------------------------------------------------------------------------
def migrate_db():
    logger.info("Запуск миграций БД...")
    try:
        conn = get_db()
        cur = conn.cursor()

        # Добавляем is_admin, если нет
        try:
            cur.execute("PRAGMA table_info(players)")
            cols = [c[1] for c in cur.fetchall()]
            if 'is_admin' not in cols:
                cur.execute("ALTER TABLE players ADD COLUMN is_admin INTEGER DEFAULT 0")
                logger.info("Миграция: добавлена колонка is_admin в players")
        except Exception as e:
            logger.error(f"Ошибка миграции is_admin: {e}")

        # Создаём chat_messages, если нет
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
    # password пока игнорируем для теста

    if not name:
        return jsonify({'error': 'Имя обязательно'}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM players WHERE name = ?", (name,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({'error': 'Игрок не найден'}), 404

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

    cur.execute("SELECT id FROM players WHERE user_id = ?", (g.user['id'],))
    if cur.fetchone():
        conn.close()
        return jsonify({"error": "У вас уже есть персонаж"}), 409

    cur.execute("SELECT id FROM players WHERE name = ?", (name,))
    if cur.fetchone():
        conn.close()
        return jsonify({"error": "Ник уже занят"}), 409

    cur.execute('''
        INSERT INTO players (name, class, attack, defense, max_hp, current_hp, inventory_json, equipment_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        name, cls, stats['attack'], stats['defense'], 100, 100, '[]', '{"weapon": null, "armor": null}'
    ))
    conn.commit()
    conn.close()

    player = {
        "name": name, "class": cls, "level": 1, "aden": 0, "exp": 0,
        "next_level_exp": 100, "current_hp": 100, "max_hp": 100,
        "attack": stats['attack'], "defense": stats['defense'],
        "inventory": [], "equipment": {"weapon": None, "armor": None},
    }
    return jsonify(player), 201


@app.route('/status', methods=['POST'])
@login_required
def status():
    data = request.get_json() or {}
    player_name = (data.get('player_id') or g.user.get('name')).strip()

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
        "name": row["name"], "class": row["class"], "level": row["level"],
        "aden": row["adenas"], "exp": row["exp"], "next_level_exp": row["next_level_exp"],
        "current_hp": row["current_hp"], "max_hp": row["max_hp"],
        "attack": row["attack"], "defense": row["defense"],
        "inventory": inventory, "equipment": equipment,
    }

    attack, defense = calc_stats(hero)

    resp = {
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


@app.route('/api/chat/send', methods=['POST'])
@login_required
def api_chat_send():
    data = request.get_json() or {}
    player_id = data.get('player_id')
    message = (data.get('message') or '').strip()

    if not player_id:
        return jsonify({'error': 'player_id обязателен'}), 400
    if not message:
        return jsonify({'error': 'Пустое сообщение'}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT name, is_admin FROM players WHERE id = ?", (player_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({'error': 'Игрок не найден'}), 404

    sender_name = row['name']
    is_admin = bool(row['is_admin'])

    type_ = 'chat'
    response_message = None

    if is_admin and message.startswith('/'):
        type_ = 'command'
        result = handle_admin_command(sender_name, message)
        if result.get('is_command_result'):
            response_message = result.get('success') and result.get('message') or result.get('error')

            conn = get_db()
        cur = conn.cursor()

        if type_ == 'command':
            # Для команд не сохраняем в чат, просто возвращаем результат
            conn.close()
            return jsonify({
                'success': True,
                'message': response_message,
                'is_command': True
            })

        # Обычное сообщение в чат
        try:
            cur.execute('''
                INSERT INTO chat_messages (player_name, message, type)
                VALUES (?, ?, ?)
            ''', (sender_name, message, 'chat'))
            conn.commit()

            resp = {
                'id': cur.lastrowid,
                'player_name': sender_name,
                'message': message,
                'type': 'chat',
                'timestamp': None  # можно добавить CURRENT_TIMESTAMP в БД и брать оттуда
            }
            return jsonify(resp)
        except Exception as e:
            logger.error(f"Ошибка при сохранении сообщения в чат: {e}", exc_info=True)
            return jsonify({'error': 'Не удалось сохранить сообщение'}), 500
        finally:
            try:
                conn.close()
            except:
                pass


@app.route('/api/chat/history', methods=['GET'])
@login_required
def api_chat_history():
    limit = request.args.get('limit', 50, type=int)
    if limit < 1 or limit > 200:
        limit = 50

    conn = get_db()
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


# -----------------------------------------------------------------------------
# Точка входа для WSGI (Amvera / Gunicorn)
# -----------------------------------------------------------------------------
# app уже создан выше. Этот блок нужен только для локального запуска.
if __name__ == '__main__':
    logger.info("Запуск сервера в режиме отладки (local)")
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
