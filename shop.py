# shop.py
from equipment import EQUIPMENT_ITEMS, ARMOR_CLASSES, WEAPON_CLASSES

AVAILABLE_CLASSES = ["Танк", "Воин", "Лучник", "Друид"]

def get_class_items(target_class):
    """Возвращает список предметов, разрешённых для конкретного класса."""
    result = []
    for item in EQUIPMENT_ITEMS:
        # Пропускаем расходники (Камень Жизни и т. п.)
        if item.get("type") == "consumable":
            continue
        
        allowed = False
        
        # Проверка оружия
        if item["type"] == "weapon":
            for cat, classes in WEAPON_CLASSES.items():
                if item["category"] == cat and target_class in classes:
                    allowed = True
                    break
        
        # Проверка брони
        elif item["type"] == "armor":
            armor_type = item.get("armor_type")
            if armor_type:
                for a_type, classes in ARMOR_CLASSES.items():
                    if armor_type == a_type and target_class in classes:
                        allowed = True
                        break
        
        if allowed:
            result.append(item)
            
    return result


def prepare_shop_list(hero, target_class):
    """
    Возвращает список товаров для отображения.
    Ничего не печатает, ничего не спрашивает.
    """
    all_class_items = get_class_items(target_class)
    
    shop_items = []
    
    for item in all_class_items:
        name = item['name']
        price = item['price']
        min_lvl = item.get('min_level', 1)
        
        # Эффект
        if item['type'] == 'weapon':
            effect = f"+{item.get('bonus_atk', 0)} ATK"
        elif item['type'] == 'armor':
            effect = f"+{item.get('bonus_def', 0)} DEF"
        else:
            effect = "Эффект неизвестен"
        
        # Статус доступности
        status_code = "available"
        status_text = "Можно купить"
        
        if hero['level'] < min_lvl:
            status_code = "level_too_low"
            status_text = f"Слишком низкий уровень (нужно {min_lvl})"
        elif hero['aden'] < price:
            status_code = "not_enough_aden"
            status_text = f"Не хватает аден (нужно {price})"
        
        shop_items.append({
            "id": item["id"],
            "name": name,
            "effect": effect,
            "price": price,
            "min_level": min_lvl,
            "type": item["type"],
            "category": item.get("category"),
            "armor_type": item.get("armor_type"),
            "status_code": status_code,
            "status_text": status_text,
            "can_buy": (status_code == "available"),
        })
    
    return shop_items


def _recalc_stats(hero):
    """Пересчитывает атаку и защиту на основе текущей экипировки."""
    # Сбрасываем бонусы от экипировки, чтобы потом добавить заново
    base_attack = hero.get("base_attack", 0)
    base_defense = hero.get("base_defense", 0)

    # Убираем старые бонусы
    eq = hero.get("equipment", {})
    old_weapon = eq.get("weapon")
    old_armor = eq.get("armor")

    if old_weapon:
        base_attack -= old_weapon.get("bonus_atk", 0)
    if old_armor:
        base_defense -= old_armor.get("bonus_def", 0)

    # Добавляем новые бонусы
    new_weapon = eq.get("weapon")
    new_armor = eq.get("armor")

    if new_weapon:
        base_attack += new_weapon.get("bonus_atk", 0)
    if new_armor:
        base_defense += new_armor.get("bonus_def", 0)

    hero["attack"] = base_attack
    hero["defense"] = base_defense


def buy_item(hero, item_id):
    """
    Пытается купить предмет по ID.
    Обновляет статы героя после экипировки.
    Возвращает словарь с результатом и сообщением.
    Не использует input/print.
    """
    # Ищем предмет по ID
    item = None
    for it in EQUIPMENT_ITEMS:
        if it["id"] == item_id:
            item = it
            break
    
    if not item:
        return {
            "success": False,
            "message": "Предмет не найден.",
            "reason": "not_found",
        }
    
    price = item['price']
    min_lvl = item.get('min_level', 1)
    
    # Проверки
    if hero['level'] < min_lvl:
        return {
            "success": False,
            "message": f"Твой уровень ({hero['level']}) слишком низок. Нужно {min_lvl}.",
            "reason": "level_too_low",
        }
    
    if hero['aden'] < price:
        return {
            "success": False,
            "message": f"Недостаточно аден. Нужно {price}, у тебя {hero['aden']}.",
            "reason": "not_enough_aden",
        }
    
    # Покупка
    hero['aden'] -= price
    
    slot = None
    if item['type'] == 'weapon':
        slot = 'weapon'
    elif item['type'] == 'armor':
        slot = 'armor'
    
    old_item = None
    if slot:
        old_item = hero['equipment'].get(slot)
        hero['equipment'][slot] = item
    else:
        hero['inventory'].append(item)
    
    # ВАЖНО: пересчитываем статы после смены экипировки
    _recalc_stats(hero)
    
    message_parts = [f"Ты купил: {item['name']}"]
    if old_item:
        message_parts.append(f"Сменил экипировку: {old_item['name']} → {item['name']}")
    
    return {
        "success": True,
        "message": ". ".join(message_parts),
        "item": item,
        "old_item": old_item,
        "aden_left": hero['aden'],
        "hero_stats_updated": True,
    }
