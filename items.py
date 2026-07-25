# items.py

ITEMS_DB = {
    1: {"name": "Ржавый меч", "type": "weapon", "attack": 5, "defense": 0, "price": 20},
    2: {"name": "Кожаная броня", "type": "armor", "attack": 0, "defense": 4, "price": 35},
    3: {"name": "Зелья здоровья (малое)", "type": "potion", "heal": 20, "price": 10},
    4: {"name": "Стальной кинжал", "type": "weapon", "attack": 7, "defense": 0, "price": 50},
    5: {"name": "Кольчуга", "type": "armor", "attack": 0, "defense": 7, "price": 80},
    6: {"name": "Зелья маны (малое)", "type": "potion", "mana": 30, "price": 12},
    7: {"name": "Лук новичка", "type": "weapon", "attack": 6, "defense": 0, "price": 45},
    8: {"name": "Плащ странника", "type": "accessory", "attack": 1, "defense": 2, "price": 60},
    9: {"name": "Топор лесоруба", "type": "weapon", "attack": 8, "defense": 0, "price": 70},
    10: {"name": "Щит ополченца", "type": "armor", "attack": 0, "defense": 6, "price": 90},
    # Добавляй новые предметы, увеличивая ID
}

def get_item_by_id(item_id: int):
    return ITEMS_DB.get(item_id)

def get_all_items():
    return ITEMS_DB
