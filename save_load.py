import json
from pathlib import Path

def get_save_path():
    script_dir = Path(__file__).resolve().parent
    return script_dir / "save.json"

SAVE_FILE = get_save_path()

def save_hero(hero):
    safe_inventory = [dict(item) for item in hero.get("inventory", [])]

    hero_equipment = hero.get("equipment", {})
    safe_equipment = {
        "weapon": dict(hero_equipment["weapon"]) if hero_equipment.get("weapon") else None,
        "armor": dict(hero_equipment["armor"]) if hero_equipment.get("armor") else None
    }

    data_to_save = {
        "name": hero["name"],
        "class": hero["class"],
        "level": hero["level"],
        "exp": hero["exp"],
        "next_level_exp": hero["next_level_exp"],

        "stats": {
            "attack": hero["attack"],
            "defense": hero["defense"],
            "crit_chance": hero["crit_chance"],
            "crit_mult": hero["crit_mult"],
            "max_hp": hero["max_hp"],
            "current_hp": hero["current_hp"]
        },

        # ЕДИНАЯ ВАЛЮТА: просто число
        "aden": int(hero.get("aden", 0)),

        "inventory": safe_inventory,
        "equipment": safe_equipment,

        "base_stats": {
             "base_attack": hero.get("base_attack", 10),
             "base_defense": hero.get("base_defense", 5),
             "base_max_hp": hero.get("base_max_hp", 100)
        }
    }

    try:
        with open(SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
        print(f"✅ Игра сохранена: {SAVE_FILE}")
        return True
    except Exception as e:
        print(f"❌ Ошибка сохранения: {e}")
        return False


def load_hero():
    if not SAVE_FILE.exists():
        print("❌ Файл сохранения не найден.")
        return None

    try:
        with open(SAVE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"❌ Файл сохранения повреждён: {e}")
        return None

    stats = data["stats"]
    base_stats = data.get("base_stats", {})

    hero = {
        "name": data["name"],
        "class": data["class"],
        "level": data["level"],
        "exp": data["exp"],
        "next_level_exp": data["next_level_exp"],
        "attack": stats["attack"],
        "defense": stats["defense"],
        "crit_chance": stats["crit_chance"],
        "crit_mult": stats["crit_mult"],
        "max_hp": stats["max_hp"],
        "current_hp": stats["current_hp"],

        "aden": int(data.get("aden", 0)),

        "inventory": [],
        "equipment": {"weapon": None, "armor": None},
        "base_attack": base_stats.get("base_attack", 10),
        "base_defense": base_stats.get("base_defense", 5),
        "base_max_hp": base_stats.get("base_max_hp", 100),
    }

    for item_data in data.get("inventory", []):
        hero["inventory"].append(dict(item_data))

    eq_data = data.get("equipment", {})
    if eq_data.get("weapon"):
        hero["equipment"]["weapon"] = dict(eq_data["weapon"])
    if eq_data.get("armor"):
        hero["equipment"]["armor"] = dict(eq_data["armor"])

    print("✅ Герой загружен.")
    return hero
