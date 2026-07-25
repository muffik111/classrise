# cities.py

CITIES = [
    "Аэрдмор", "Вулкхаран", "Келдрион", "Торнхей", "Зеркалис",
    "Фейрстоун", "Морнвейл", "Дракенхолд", "Сильверград", "Венторн",
    "Каэрнвуд", "Ориндейл", "Гримфолл", "Валдримар", "Эшкорф"
]

def get_city_mob_module(city_name: str) -> str:
    """
    Возвращает полное имя модуля для мобов города.
    Пример: 'Аэрдмор' -> 'mobs.mob_aerdmor'
    """
    normalized = city_name.lower().replace(" ", "_")
    return f"mobs.mob_{normalized}"

def is_valid_city(city_name: str) -> bool:
    return city_name in CITIES
