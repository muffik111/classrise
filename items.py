# items.py

# База предметов (теперь это ITEMS_DB, чтобы работало с импортом from items import ITEMS_DB)
ITEMS_DB = [
    {"id": 1, "name": "Ржавый меч", "type": "weapon", "bonus_atk": 5, "bonus_def": 0, "price": 100},
    {"id": 2, "name": "Стальной клинок", "type": "weapon", "bonus_atk": 12, "bonus_def": 0, "price": 250},
    {"id": 3, "name": "Лук новичка", "type": "weapon", "bonus_atk": 8, "bonus_def": 0, "price": 180},
    {"id": 4, "name": "Деревянный щит", "type": "armor", "bonus_atk": 0, "bonus_def": 6, "price": 150},
    {"id": 5, "name": "Тяжёлый стальной щит", "type": "armor", "bonus_atk": 0, "bonus_def": 14, "price": 320},
    {"id": 6, "name": "Кожаная броня", "type": "armor", "bonus_atk": 0, "bonus_def": 8, "price": 200},
    {"id": 7, "name": "Кольчуга", "type": "armor", "bonus_atk": 0, "bonus_def": 16, "price": 400},
]

# Словарь для быстрого поиска по ID (как было в equipment.py)
ITEMS_BY_ID = {item["id"]: item for item in ITEMS_DB}

# Ограничения по классам (можно расширять)
ARMOR_CLASSES = {
    "light": ["Лучник", "Друид"],
    "medium": ["Воин", "Друид"],
    "heavy": ["Танк", "Воин"],
}

WEAPON_CLASSES = {
    "sword": ["Воин", "Танк"],
    "bow": ["Лучник"],
    "staff": ["Друид"],
}

def get_item_by_id(item_id):
    """Быстрый поиск предмета по ID"""
    return ITEMS_BY_ID.get(item_id)

def ensure_equipment_slots(player):
    """Гарантирует наличие слотов экипировки в словаре игрока"""
    if "equipment" not in player:
        player["equipment"] = {}
    if "weapon" not in player["equipment"]:
        player["equipment"]["weapon"] = None
    if "armor" not in player["equipment"]:
        player["equipment"]["armor"] = None

def apply_equipment(player):
    """
    Считает итоговые статы с учётом экипировки.
    Возвращает словарь с max_hp, current_hp, attack, defense.
    """
    # Базовые статы (если их нет в игроке, берем дефолтные)
    base_hp = player.get("base_hp", 100)
    base_attack = player.get("base_attack", 10)
    base_defense = player.get("base_defense", 5)
    level = player.get("level", 1)

    # Прогрессия статов от уровня (как в твоем коде)
    max_hp = int(base_hp * (1 + 0.15 * (level - 1)))
    attack = int(base_attack * (1 + 0.12 * (level - 1)))
    defense = int(base_defense * (1 + 0.10 * (level - 1)))

    ensure_equipment_slots(player)
    equipment = player["equipment"]

    # Учитываем оружие
    weapon = equipment.get("weapon")
    if weapon:
        attack += weapon.get("bonus_atk", 0)
        defense += weapon.get("bonus_def", 0)

    # Учитываем броню
    armor = equipment.get("armor")
    if armor:
        attack += armor.get("bonus_atk", 0)
        defense += armor.get("bonus_def", 0)

    current_hp = player.get("current_hp", max_hp)
    if current_hp > max_hp:
        current_hp = max_hp

    return {
        "max_hp": max_hp,
        "current_hp": current_hp,
        "attack": attack,
        "defense": defense,
    }

def calc_stats(hero):
    """
    Функция-обертка для совместимости с server.py.
    server.py ожидает именно calc_stats(hero).
    """
    stats = apply_equipment(hero)
    return stats["attack"], stats["defense"]

def equip_item(player, item_id):
    """
    Надевает предмет по ID.
    Обновляет статы игрока сразу после экипировки.
    Возвращает True/False.
    """
    item = get_item_by_id(item_id)
    if not item:
        return False

    ensure_equipment_slots(player)

    item_type = item.get("type")
    
    # Логика надевания оружия
    if item_type == "weapon":
        old_weapon = player["equipment"].get("weapon")
        if old_weapon:
            # Снимаем бонусы старого оружия (если они были добавлены вручную где-то еще)
            pass 
        
        player["equipment"]["weapon"] = item
        # Примечание: В server.py статы пересчитываются через calc_stats при каждом бою/запросе,
        # поэтому здесь мы просто сохраняем ID в инвентарь/экипировку, а не меняем атаку напрямую.
        return True

    # Логика надевания брони (с проверкой классов)
    elif item_type == "armor":
        # В твоей базе нет поля armor_type, поэтому упрощаем проверку или убираем её,
        # если ты не добавил это поле в ITEMS_DB. Пока сделаем универсально.
        
        old_armor = player["equipment"].get("armor")
        
        player["equipment"]["armor"] = item
        return True

    return False
