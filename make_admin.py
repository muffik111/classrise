# make_admin.py
import sqlite3
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR = '/data'
DB_FILE = os.path.join(DATA_DIR, 'game.db')

# ВПИШИ СЮДА ИМЯ ИГРОКА, которого хочешь сделать админом.
# Важно: имя должно точно совпадать с тем, что хранится в БД (регистр, пробелы).
ADMIN_NAME = 'ТвойНикАдмина'

conn = sqlite3.connect(DB_FILE)
cur = conn.cursor()

try:
    cur.execute("UPDATE players SET is_admin = 1 WHERE name = ?", (ADMIN_NAME,))
    if cur.rowcount == 0:
        logger.warning(f"Игрок '{ADMIN_NAME}' не найден. Сначала зарегистрируй его через игру.")
    else:
        conn.commit()
        logger.info(f"✅ Игрок '{ADMIN_NAME}' теперь админ (is_admin = 1).")
except Exception as e:
    logger.error(f"Ошибка при назначении админа: {e}")
finally:
    conn.close()
