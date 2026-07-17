# augment.py
import random
import json  # ОБЯЗАТЕЛЬНО: без этого будет NameError
from equipment import AUGMENT_DATA
import sqlite3
from server import DB_PATH


def get_current_augment_level(item):
    return item.get("augment_level", 0)


def can_augment(item):
    lvl = get_current_augment_level(item)
    return lvl < 10


def get_augment_cost_and_chance(item_type, current_level):
    if current_level >= 10:
        return 0, 0.0
    data_list = AUGMENT_DATA.get(item_type)
    if not data_list or current_level >= len(data_list):
        return 0, 0.0
    entry = data_list[current_level + 1]
    return entry["cost_aden"], entry["chance"]


def recalc_stats(hero):
    """Пересчитывает атаку/защиту героя на основе экипировки и уровней аугмента"""
    base_atk = hero["base_stats"]["base_attack"]
    base_def = hero["base_stats"]["base_defense"]

    w = hero["equipment"].get("weapon")
    a = hero["equipment"].get("armor")

    bonus_atk = w.get("bonus_atk", 0) if w else 0
    bonus_def = a.get("bonus_def", 0) if a else 0

    hero["attack"] = base_atk + bonus_atk
    hero["defense"] = base_def + bonus_def


def load_player(name):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM players WHERE name = ?", (name,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    inventory = []
    try:
        inventory = json.loads(row["inventory_json"])
    except Exception:
        inventory = []

    equipment = {}
    try:
        equipment = json.loads(row["equipment_json"]) or {"weapon": None, "armor": None}
    except Exception:
        equipment = {"weapon": None, "armor": None}

    # ВАЖНО: базовые статы считаем по уровню (чтобы не было накрутки бонусов)
    base_stats = {
        "base_attack": 10 + row["level"] * 2,
        "base_defense": 5 + row["level"] * 1,
    }

    hero = {
        "name": row["name"],
        "aden": row["adenas"],
        "inventory": inventory,
        "equipment": equipment,
        "base_stats": base_stats,
        # Статы будут пересчитаны сразу после загрузки
        "attack": 0,
        "defense": 0,
        "current_hp": row["current_hp"],
        "max_hp": row["max_hp"],
    }

    # Сразу пересчитываем итоговые статы, чтобы не было 0
    recalc_stats(hero)
    return hero


def save_player(hero):
    """Сохраняет героя в БД (адены, инвентарь, экипировка, статы)"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    inv_json = json.dumps(hero["inventory"])
    eq_json = json.dumps(hero["equipment"])

    cur.execute(
        """UPDATE players SET
           adenas = ?,
           inventory_json = ?,
           equipment_json = ?,
           attack = ?,
           defense = ?,
           current_hp = ?,
           max_hp = ?
           WHERE name = ?""",
        (
            hero["aden"],
            inv_json,
            eq_json,
            hero["attack"],
            hero["defense"],
            hero["current_hp"],
            hero["max_hp"],
            hero["name"],
        )
    )
    conn.commit()
    conn.close()


def perform_augment(hero, item_location, item_key_or_index):
    """
    item_location: 'inventory' или 'equipment'
    item_key_or_index: для inventory — индекс в списке, для equipment — 'weapon' или 'armor'
    Возвращает (success, message, updated_hero_partial)
    """
    # Находим предмет
    item = None
    if item_location == "inventory":
        if not (0 <= item_key_or_index < len(hero["inventory"])):
            return False, "❌ Неверный индекс предмета в инвентаре.", None
        item = hero["inventory"][item_key_or_index]
    elif item_location == "equipment":
        if item_key_or_index not in ["weapon", "armor"]:
            return False, "❌ Недопустимый слот экипировки.", None
        item = hero["equipment"].get(item_key_or_index)
    else:
        return False, "❌ Неизвестное расположение предмета.", None

    if not item:
        return False, "❌ Предмет не найден.", None

    if not can_augment(item):
        return False, f"❌ Предмет уже на максимальном уровне аугментации (+10).", None

    current_lvl = get_current_augment_level(item)
    next_lvl = current_lvl + 1
    cost, chance = get_augment_cost_and_chance(item["type"], current_lvl)

    if hero["aden"] < cost:
        return False, f"❌ Недостаточно аден. Нужно {cost}, у тебя {hero['aden']}.", None

    roll = random.random()
    success = roll <= chance

    # Деньги списываются всегда
    hero["aden"] -= cost

    if success:
        item["augment_level"] = next_lvl
        bonus_key = "bonus_atk" if item["type"] == "weapon" else "bonus_def"
        base_bonus = item.get(bonus_key, 0)
        new_bonus = base_bonus + next_lvl * 5
        item[bonus_key] = new_bonus

        # Если предмет в экипировке — пересчитываем статы
        recalc_stats(hero)

        msg = f"✅ Аугментация успешна! Теперь предмет +{next_lvl} (+{new_bonus} к стате)."
    else:
        msg = f"❌ Аугментация не удалась! Ты потерял {cost} аден."

    # Сохраняем игрока в БД
    save_player(hero)

    # Возвращаем только то, что фронтенду нужно для обновления UI
    updated_partial = {
        "aden": hero["aden"],
        "inventory": hero["inventory"],
        "equipment": hero["equipment"],
        "attack": hero["attack"],
        "defense": hero["defense"],
        "item": item,
    }
    return success, msg, updated_partial
