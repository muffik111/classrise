import random
from equipment import EQUIPMENT_ITEMS

def get_item_by_id(item_id):
    """Находит предмет по ID и возвращает его копию."""
    for item in EQUIPMENT_ITEMS:
        if item.get("id") == item_id:
            return item.copy()
    return None

def roll_loot(mob):
    """Выдаёт лут согласно правилам из loot_table.
    
    ВАЖНО: Эта функция НЕ должна делать print().
    Она только возвращает список предметов — Vue сам решит, как и когда их показать.
    """
    loot_key = mob.get("loot_key")
    if not loot_key:
        return []

    try:
        from loot_table import MOB_LOOT_RULES
    except ImportError:
        # Если loot_table ещё нет — просто не даём лут, игра не должна падать
        return []

    rules = MOB_LOOT_RULES.get(loot_key, [])
    dropped_items = []

    for loot_table, chance in rules:
        if random.random() < chance:
            items_pool = []
            for item_id, drop_chance in loot_table.items():
                count = int(drop_chance * 1000)
                if count > 0:
                    items_pool.extend([item_id] * count)

            if items_pool:
                chosen_id = random.choice(items_pool)
                item = get_item_by_id(chosen_id)
                if item:
                    dropped_items.append(item)

    return dropped_items
