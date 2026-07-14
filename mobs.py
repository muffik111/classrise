import random

# База мобов: у каждого есть loot_item_id и loot_chance (от 0 до 1)
MOBS = {
    1: {
        "name": "Гоблин",
        "hp": 40,
        "attack": 8,
        "defense": 3,
        "exp": 25,
        "loot_item_id": 1,          # ID предмета, который может выпасть
        "loot_chance": 1.0          # 100% шанс выпадения
    },
    2: {
        "name": "Волк",
        "hp": 55,
        "attack": 10,
        "defense": 4,
        "exp": 35,
        "loot_item_id": 9,
        "loot_chance": 0.5          # 50% шанс
    },
    3: {
        "name": "Скелет",
        "hp": 70,
        "attack": 12,
        "defense": 6,
        "exp": 50,
        "loot_item_id": 10,
        "loot_chance": 0.4          # 40% шанс
    }
}

def roll_loot(mob_id):
    """Проверяет шанс и возвращает ID предмета, если выпал, иначе None"""
    mob = MOBS.get(mob_id)
    if not mob:
        return None
    
    chance = mob.get("loot_chance", 0)
    item_id = mob.get("loot_item_id")
    
    if random.random() < chance and item_id is not None:
        return item_id
    return None
