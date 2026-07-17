# make_admin.py
import sqlite3
import os
import logging
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- УМНОЕ ОПРЕДЕЛЕНИЕ ПУТИ К БАЗЕ ---
# Если есть папка /data (это Linux/Amvera) -> берем оттуда.
# Иначе (Windows/Mac) -> берем из текущей папки проекта.
if os.path.exists('/data'):
    DATA_DIR = '/data'
else:
    DATA_DIR = '.'  # '.' означает "текущая папка", где лежит этот скрипт

DB_FILE = os.path.join(DATA_DIR, 'game.db')

# ВПИШИ СЮДА ИМЯ ИГРОКА, которого хочешь сделать админом.
# ВАЖНО: Имя должно совпадать ТОЧНО (регистр букв важен!).
# Если при регистрации ты делал .capitalize(), то пиши 'Admin', а не 'admin'.
ADMIN_NAME = 'admin' 

logger.info(f"Пытаюсь открыть базу данных: {os.path.abspath(DB_FILE)}")

# Проверка: существует ли файл вообще?
if not os.path.isfile(DB_FILE):
    logger.error("❌ Файл базы данных не найден!")
    logger.error(f"Путь, по которому я ищу: {os.path.abspath(DB_FILE)}")
    logger.error("")
    logger.error("Что делать:")
    logger.error("1. Запусти свою игру (server.py) хотя бы один раз, чтобы создалась база.")
    logger.error("2. Проверь, что в папке C:\\HeroPath есть файл game.db")
    sys.exit(1)

conn = sqlite3.connect(DB_FILE)
cur = conn.cursor()

try:
    # Сначала выводим ВСЕХ игроков, чтобы ты увидел, как они записаны в базе
    cur.execute("SELECT id, name, is_admin FROM players")
    players = cur.fetchall()
    
    logger.info(f"✅ В базе найдено игроков: {len(players)}")
    logger.info("Список игроков (проверь точное написание имени):")
    for p in players:
        marker = " [АДМИН]" if p[2] == 1 else ""
        logger.info(f"   id={p[0]}, name='{p[1]}'{marker}")

    # Теперь пробуем назначить админа
    cur.execute("UPDATE players SET is_admin = 1 WHERE name = ?", (ADMIN_NAME,))

    if cur.rowcount == 0:
        logger.warning(f"⚠️ Игрок '{ADMIN_NAME}' не найден в базе!")
        logger.warning("Посмотри список выше. Возможно, имя отличается регистром (Admin vs admin).")
        logger.warning("Измени переменную ADMIN_NAME в коде на точное имя из списка.")
    else:
        conn.commit()
        logger.info(f"🎉 УСПЕХ! Игрок '{ADMIN_NAME}' теперь админ (is_admin = 1).")

except Exception as e:
    logger.error(f"💥 Произошла ошибка: {e}")
finally:
    conn.close()
