import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLASSES_FILE = os.path.join(BASE_DIR, "classes.json")

# Загружаем class_stats из JSON, чтобы можно было импортировать в server.py
try:
    with open(CLASSES_FILE, "r", encoding="utf-8") as f:
        class_stats = json.load(f)
except FileNotFoundError:
    # Если JSON нет (например, при первом запуске), ставим заглушку, чтобы сервер хотя бы стартовал
    class_stats = {}
    print(f"[WARNING] classes.json не найден: {CLASSES_FILE}")
except json.JSONDecodeError as e:
    class_stats = {}
    print(f"[ERROR] Ошибка в classes.json: {e}")


def get_class_stats(cls_name):
    if not cls_name:
        return None
    # Приводим к виду, как в JSON (с большой буквы), чтобы работало "воин", "ВОИН" и т.п.
    key = cls_name.strip().capitalize()
    return class_stats.get(key)
