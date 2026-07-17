# equipment.py

# База предметов: используем bonus_atk / bonus_def, чтобы везде было одинаково
EQUIPMENT_ITEMS = [
    {"id": 1, "name": "Ржавый меч", "type": "weapon", "bonus_atk": 5, "bonus_def": 0, "price": 100},
    {"id": 2, "name": "Стальной клинок", "type": "weapon", "bonus_atk": 12, "bonus_def": 0, "price": 250},
    {"id": 3, "name": "Лук новичка", "type": "weapon", "bonus_atk": 8, "bonus_def": 0, "price": 180},
    {"id": 4, "name": "Деревянный щит", "type": "armor", "bonus_atk": 0, "bonus_def": 6, "price": 150},
    {"id": 5, "name": "Тяжёлый стальной щит", "type": "armor", "bonus_atk": 0, "bonus_def": 14, "price": 320},
    {"id": 6, "name": "Кожаная броня", "type": "armor", "bonus_atk": 0, "bonus_def": 8, "price": 200},
    {"id": 7, "name": "Кольчуга", "type": "armor", "bonus_atk": 0, "bonus_def": 16, "price": 400},
]

# Для быстрого поиска по ID
EQUIPMENT_BY_ID = {item["id"]: item for item in EQUIPMENT_ITEMS}

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
    return EQUIPMENT_BY_ID.get(item_id)


def apply_equipment(player):
    """
    Считает итоговые статы с учётом экипировки.
    Работает с объектами предметов в слотах (а не с ID).
    """
    base_hp = player.get("base_hp", 100)
    base_attack = player.get("base_attack", 10)
    base_defense = player.get("base_defense", 5)
    level = player.get("level", 1)

    # Базовые статы с прогрессией по уровню
    max_hp = int(base_hp * (1 + 0.15 * (level - 1)))
    attack = int(base_attack * (1 + 0.12 * (level - 1)))
    defense = int(base_defense * (1 + 0.10 * (level - 1)))

    equipment = player.get("equipment", {})

    # Учитываем оружие
    weapon = equipment.get("weapon")
    if weapon:
        attack += weapon.get("bonus_atk", 0)
        defense += weapon.get("bonus_def", 0)  # иногда оружие даёт и защиту

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


def equip_item(player, item):
    """
    Надевает предмет (объект словаря) в нужный слот.
    Обновляет статы игрока сразу после экипировки.
    Возвращает True/False.
    """
    ensure_equipment_slots(player)

    item_type = item.get("type")
    if item_type == "weapon":
        slot = "weapon"
        old = player["equipment"].get("weapon")
        if old:
            player["attack"] -= old.get("bonus_atk", 0)
            player["defense"] -= old.get("bonus_def", 0)
        player["equipment"]["weapon"] = item
        player["attack"] += item.get("bonus_atk", 0)
        player["defense"] += item.get("bonus_def", 0)
        return True

    elif item_type == "armor":
        armor_type = item.get("armor_type")
        # Проверка классов (можно расширить)
        allowed_classes = ARMOR_CLASSES.get(armor_type, [])
        if player["class"] not in allowed_classes and allowed_classes:
            return False  # нельзя надеть

        slot = "armor"
        old = player["equipment"].get("armor")
        if old:
            player["defense"] -= old.get("bonus_def", 0)
            player["attack"] -= old.get("bonus_atk", 0)
        player["equipment"]["armor"] = item
        player["defense"] += item.get("bonus_def", 0)
        player["attack"] += item.get("bonus_atk", 0)
        return True

    return False


def ensure_equipment_slots(player):
    if "equipment" not in player:
        player["equipment"] = {}
    if "weapon" not in player["equipment"]:
        player["equipment"]["weapon"] = None
    if "armor" not in player["equipment"]:
        player["equipment"]["armor"] = None
