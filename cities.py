# cities.py

CITIES = [
    {"id": 1, "name": "Деревня новичков", "city_level": 1},
    {"id": 2, "name": "Приграничный посёлок", "city_level": 2},
    {"id": 3, "name": "Лесная застава", "city_level": 3},
    {"id": 4, "name": "Старая мельница", "city_level": 4},
    {"id": 5, "name": "Заброшенная шахта", "city_level": 5},
    {"id": 6, "name": "Руины древнего форта", "city_level": 6},
    {"id": 7, "name": "Пограничная крепость", "city_level": 7},
    {"id": 8, "name": "Долина теней", "city_level": 8},
    {"id": 9, "name": "Пещеры кристаллических скал", "city_level": 9},
    {"id": 10, "name": "Старый торговый тракт", "city_level": 10},
    {"id": 11, "name": "Болота проклятых земель", "city_level": 11},
    {"id": 12, "name": "Ущелье каменных стражей", "city_level": 12},
    {"id": 13, "name": "Храм забытых богов", "city_level": 13},
    {"id": 14, "name": "Лагерь наёмников", "city_level": 14},
    {"id": 15, "name": "Разрушенный дворец", "city_level": 15},
    {"id": 16, "name": "Вулканические пустоши", "city_level": 16},
    {"id": 17, "name": "Ледяные катакомбы", "city_level": 17},
    {"id": 18, "name": "Город парящих башен", "city_level": 18},
    {"id": 19, "name": "Башня вечного пламени", "city_level": 19},
    {"id": 20, "name": "Цитадель древних королей", "city_level": 20},
]

LOCATIONS = {}
CITY_LOCATIONS_MAP = {}  # city_id -> [loc_id1, loc_id2, ...]
loc_id = 1

for city in CITIES:
    city_id = city["id"]
    city_name = city["name"]
    city_level = city["city_level"]
    CITY_LOCATIONS_MAP[city_id] = []

    # Вариант с нарастающей сложностью: +0, +1, +2, +3, +4 к уровню города
    for i in range(5):
        loc_level = city_level + i
        LOCATIONS[loc_id] = {
            "name": f"{city_name} — Локация {i+1}",
            "level_base": loc_level,
            "has_shop": (i == 0),          # магазин только в первой локации
            "city_id": city_id,
            "city_name": city_name,
        }
        CITY_LOCATIONS_MAP[city_id].append(loc_id)
        loc_id += 1

def get_location_info(loc_id):
    return LOCATIONS.get(loc_id)

def get_city_by_loc_id(loc_id):
    loc = LOCATIONS.get(loc_id)
    if not loc:
        return None
    return loc["city_id"]

def get_locations_for_city(city_id):
    """Возвращает список ID локаций для города (для телепортации)"""
    return CITY_LOCATIONS_MAP.get(city_id, [])

def get_next_loc_in_city(current_loc_id):
    """
    Для кнопки «Следующая локация»: возвращает ID следующей локации в том же городе.
    Если это последняя локация города — возвращает None.
    """
    loc = LOCATIONS.get(current_loc_id)
    if not loc:
        return None

    city_id = loc["city_id"]
    locs = CITY_LOCATIONS_MAP.get(city_id, [])
    try:
        idx = locs.index(current_loc_id)
        if idx + 1 < len(locs):
            return locs[idx + 1]
    except ValueError:
        pass
    return None

def get_prev_loc_in_city(current_loc_id):
    """Для кнопки «Предыдущая локация»"""
    loc = LOCATIONS.get(current_loc_id)
    if not loc:
        return None

    city_id = loc["city_id"]
    locs = CITY_LOCATIONS_MAP.get(city_id, [])
    try:
        idx = locs.index(current_loc_id)
        if idx - 1 >= 0:
            return locs[idx - 1]
    except ValueError:
        pass
    return None
