import requests
import os
import traceback
from hero import CLASS_TEMPLATES, level_up, MAX_LEVEL
from cities import CITIES, LOCATIONS, get_location_info, get_city_by_loc_id, CITY_LOCATIONS_MAP
from battle import run_battle
from shop import shop_menu
from mobs import get_mob_for_location
from augment import blacksmith_menu
from equipment import EQUIPMENT_ITEMS, ARMOR_CLASSES, apply_equipment

BASE_URL = "http://127.0.0.1:5000"

def ensure_equipment_slots(hero):
    if "equipment" not in hero:
        hero["equipment"] = {}
    if "weapon" not in hero["equipment"]:
        hero["equipment"]["weapon"] = None
    if "armor" not in hero["equipment"]:
        hero["equipment"]["armor"] = None

def ensure_inventory(hero):
    if "inventory" not in hero:
        hero["inventory"] = []

def is_valid_hero(hero):
    """Проверяет, что герой минимально пригоден для игры."""
    if not hero:
        return False, "Герой не создан (None)."
    required_fields = ["name", "class", "level", "current_hp", "max_hp", "attack", "defense", "exp", "next_level_exp"]
    missing = [f for f in required_fields if f not in hero]
    if missing:
        return False, f"В данных героя не хватает полей: {missing}"
    return True, "OK"

def choose_class():
    classes = list(CLASS_TEMPLATES.keys())
    print("\n=== ВЫБОР КЛАССА ===")
    for i, c in enumerate(classes, 1):
        desc = CLASS_TEMPLATES[c].get("description", "Нет описания")
        print(f"[{i}] {c} — {desc}")
    print("[0] Выход из игры")

    while True:
        try:
            choice = input("Твой выбор (номер класса): ").strip()
            if choice == "0":
                return None
            if not choice.isdigit():
                print("Только цифры.")
                continue
            idx = int(choice)
            if 1 <= idx <= len(classes):
                return classes[idx - 1]
            print("Такого класса нет.")
        except Exception:
            print("Ошибка ввода. Попробуй снова.")

def register_on_server(name, cls, password):
    payload = {"name": name, "cls": cls, "password": password}
    try:
        resp = requests.post(f"{BASE_URL}/register", json=payload, timeout=5)
        data = resp.json()
        if data.get("success"):
            hero = data.get("hero")
            ok, msg = is_valid_hero(hero)
            if ok:
                print("✅ Регистрация успешна!")
                return hero
            else:
                print(f"⚠️ Сервер вернул героя, но он неполный: {msg}")
                return None
        else:
            print(f"❌ Ошибка регистрации: {data.get('message', 'Неизвестная ошибка')}")
            return None
    except Exception as e:
        print(f"💥 Ошибка соединения с сервером: {e}")
        return None

def login_on_server(name, password):
    payload = {"name": name, "password": password}
    try:
        resp = requests.post(f"{BASE_URL}/login", json=payload, timeout=5)
        data = resp.json()
        if data.get("success"):
            hero = data.get("hero")
            ok, msg = is_valid_hero(hero)
            if ok:
                print("✅ Успешный вход!")
                return hero
            else:
                print(f"⚠️ Данные героя неполные: {msg}. Возможно, сохранение повреждено.")
                return None
        else:
            print(f"❌ Ошибка входа: {data.get('message', 'Неизвестная ошибка')}")
            return None
    except Exception as e:
        print(f"💥 Ошибка соединения с сервером: {e}")
        return None

def show_character_info(hero):
    ensure_equipment_slots(hero)
    ensure_inventory(hero)

    # Сначала пересчитываем статы, чтобы они точно были актуальными
    stats = apply_equipment(hero)
    hero.update(stats)

    eq = hero["equipment"]
    w = eq.get("weapon")
    a = eq.get("armor")

    print("\n" + "=" * 40)
    print(f"🦸 О ПЕРСОНАЖЕ: {hero['name']} [{hero['class']}]")
    print("=" * 40)
    print(f"Уровень: {hero['level']}/{MAX_LEVEL}")
    print(f"HP: {hero['current_hp']}/{hero['max_hp']}")
    print(f"Атака: {hero['attack']}")
    print(f"Защита: {hero['defense']}")
    print(f"Шанс крита: {hero['crit_chance']:.2%}")
    print(f"Множитель крита: x{hero['crit_mult']}")
    print(f"EXP: {hero['exp']}/{hero['next_level_exp']}")

    print("\n🧰 ЭКИПИРОВКА:")
    if w:
        lvl = w.get("augment_level", 0)
        bonus = w.get("bonus_atk", 0)
        print(f"   Оружие: {w['name']} (+{bonus} ATK, +{lvl})")
    else:
        print("   Оружие: нет")

    if a:
        armor_type_name = {
            "heavy": "Тяжёлая",
            "medium": "Средняя",
            "light": "Лёгкая",
            "leather": "Кожаная"
        }.get(a.get("armor_type"), "Неизвестный тип")
        lvl = a.get("augment_level", 0)
        bonus = a.get("bonus_def", 0)
        print(f"   Броня: {a['name']} ({armor_type_name}) (+{bonus} DEF, +{lvl})")
    else:
        print("   Броня: нет")

    print("=" * 40 + "\n")

def add_item_by_id(hero, item_id):
    ensure_inventory(hero)
    for item in EQUIPMENT_ITEMS:
        if item.get("id") == item_id:
            new_item = {k: v for k, v in item.items()}
            hero["inventory"].append(new_item)
            print(f"✅ В инвентарь добавлен: {item['name']}")
            return True
    print(f"❌ Предмет с ID {item_id} не найден!")
    return False

def teleport_menu(current_loc_id):
    current_loc = get_location_info(current_loc_id)
    current_city_id = get_city_by_loc_id(current_loc_id) if current_loc else None

    sorted_cities = sorted(CITIES, key=lambda c: c["city_level"])
    print("\n🌍 ТЕЛЕПОРТ: выбор города (по возрастанию сложности):")
    for idx, city in enumerate(sorted_cities, 1):
        marker = "📍" if city["id"] == current_city_id else "   "
        print(f"{marker}[{idx}] {city['name']} (ур. города: {city['city_level']})")
    print("[0] Отмена телепортации")

    while True:
        try:
            city_choice = input("Выбери город (номер): ").strip()
            if city_choice == "0":
                return current_loc_id
            if not city_choice.isdigit():
                print("Только цифры.")
                continue
            c_idx = int(city_choice)
            if 1 <= c_idx <= len(sorted_cities):
                target_city = sorted_cities[c_idx - 1]
                break
            else:
                print("Такого города нет.")
        except Exception:
            print("Ошибка ввода города. Попробуй снова.")

    target_city_id = target_city["id"]
    loc_ids = CITY_LOCATIONS_MAP.get(target_city_id, [])
    if not loc_ids:
        print("⚠️ В этом городе нет локаций.")
        return current_loc_id

    print(f"\n🗺 Локации в городе «{target_city['name']}»:")
    for idx, lid in enumerate(loc_ids, 1):
        info = LOCATIONS.get(lid)
        if not info:
            continue
        marker = "📍" if lid == current_loc_id else "   "
        print(f"{marker}[{idx}] {info['name']} (ур. базы: {info.get('level_base', 0)})")
    print("[0] Вернуться к выбору города")

    while True:
        try:
            loc_choice = input("Выбери локацию (номер): ").strip()
            if loc_choice == "0":
                return current_loc_id
            if not loc_choice.isdigit():
                print("Только цифры.")
                continue
            l_idx = int(loc_choice)
            if 1 <= l_idx <= len(loc_ids):
                return loc_ids[l_idx - 1]
            else:
                print("Такой локации нет.")
        except Exception:
            print("Ошибка выбора локации. Попробуй снова.")

def equip_item(hero, item):
    ensure_equipment_slots(hero)
    ensure_inventory(hero)

    if item is None:
        return False

    item_type = item.get("type")
    armor_type = item.get("armor_type")

    if item_type == "armor" and armor_type:
        allowed_classes = ARMOR_CLASSES.get(armor_type, [])
        if hero["class"] not in allowed_classes:
            print(f"❌ Ты не можешь надеть эту броню! {item['name']} доступна только классам: {', '.join(allowed_classes)}")
            return False

    slot = None
    if item_type == "weapon":
        slot = "weapon"
    elif item_type == "armor":
        slot = "armor"

    if not slot:
        print("❌ Нельзя экипировать такой тип предмета.")
        return False

    old_item = hero["equipment"].get(slot)
    hero["equipment"][slot] = item

    if old_item:
        hero["inventory"].append(old_item)

    print(f"🎮 Экипировано: {item['name']}")
    return True

def inventory_menu(hero):
    ensure_inventory(hero)
    inv = hero.get("inventory", [])
    if not inv:
        print("🎒 Твой инвентарь пуст.")
        input("Нажми Enter, чтобы вернуться… ")
        return

    print("\n🎒 ИНВЕНТАРЬ:")
    for idx, item in enumerate(inv, 1):
        lvl = item.get("augment_level", 0)
        bonus = item.get('bonus_atk') or item.get('bonus_def') or 0
        item_id = item.get('id', 'N/A')
        typ = item.get('type', 'unknown').upper()
        print(f"[{idx}] [{item_id}] {typ}: {item['name']} (+{bonus}, +{lvl})")

    print("[0] Выйти из инвентаря")

    while True:
        try:
            choice = input("Что сделать? (номер предмета для экипировки или 0): ").strip()
            if choice == "0":
                break
            if not choice.isdigit():
                continue

            idx = int(choice)
            if 1 <= idx <= len(inv):
                item = inv[idx - 1]
                if equip_item(hero, item):
                    del hero["inventory"][idx - 1]
                    stats = apply_equipment(hero)
                    hero.update(stats)
                    print("📊 Статы обновлены с учётом новой экипировки.")
            else:
                print("Нет такого предмета.")
        except Exception as e:
            print(f"Ошибка в инвентаре: {e}")
            break

def main():
    hero = None
    print("=== ОТЛАДКА: hero сейчас равен:", hero)

    # Цикл входа/регистрации
    while hero is None:
        print("\n=== ДОБРО ПОЖАЛОВАТЬ В ИГРУ ===")
        print("[1] Регистрация нового героя")
        print("[2] Вход существующего героя")
        print("[0] Выход")
        choice = input("Выбор: ").strip()

        if choice == "1":
            name = input("Придумай имя героя: ").strip()
            if not name:
                print("Имя не может быть пустым.")
                continue
            cls = choose_class()
            if not cls:
                continue
            password = input("Придумай пароль (запомни его!): ").strip()
            if not password:
                print("Пароль не может быть пустым.")
                continue
            hero = register_on_server(name, cls, password)

        elif choice == "2":
            name = input("Введи имя героя: ").strip()
            password = input("Введи пароль: ").strip()
            hero = login_on_server(name, password)

        elif choice == "0":
            print("👋 До встречи!")
            return
        else:
            print("Неверный выбор. Попробуй 1, 2 или 0.")

        # Если сервер вернул героя, но он невалидный — сбрасываем и просим заново
        if hero:
            ok, msg = is_valid_hero(hero)
            if not ok:
                print(f"⚠️ Герой невалиден: {msg}. Попробуй создать заново.")
                hero = None

    # После входа — обязательно пересчитываем статы
    current_loc_id = hero.get("location_id", 1)
    ensure_equipment_slots(hero)
    stats = apply_equipment(hero)
    hero.update(stats)
    print("✅ Статы героя пересчитаны после входа.")

    try:
        while True:
            loc = get_location_info(current_loc_id)
            loc_name = loc.get("name", "Неизвестная локация") if loc else "Неизвестная локация"
            loc_level = loc.get("level_base", 0) if loc else 0
            is_city_zone = loc.get("has_shop", False) if loc else False

            print(f"\n📍 Ты находишься: {loc_name} (уровень сложности локации: {loc_level})")

            menu_items = []
            menu_items.append(("1", "Телепортироваться в другую локацию"))

            if not is_city_zone:
                menu_items.append(("2", "Сразиться с мобом"))

            if is_city_zone:
                next_num = str(len(menu_items) + 1)
                menu_items.append((next_num, "Посетить магазин"))
                next_num = str(len(menu_items) + 1)
                menu_items.append((next_num, "Поговорить с Кузнецом (аугментация)"))

            next_num = str(len(menu_items) + 1)
            menu_items.append((next_num, "Открыть инвентарь и экипировать предметы"))

            next_num = str(len(menu_items) + 1)
            menu_items.append((next_num, "Показать статы персонажа"))

            next_num = str(len(menu_items) + 1)
            menu_items.append((next_num, "Сохранить игру (экспорт в JSON)"))

            menu_items.append(("0", "Выйти из игры"))

            for num, text in menu_items:
                print(f"[{num}] {text}")

            raw_input = input("Твой выбор: ").strip()

            # --- АДМИН-КОМАНДЫ ---
            if raw_input.startswith("/give "):
                if not hero.get("is_admin", False):
                    print("🔒 У тебя нет прав для использования админ-команд.")
                    continue
                parts = raw_input.split()
                if len(parts) != 2:
                    print("❌ Формат: /give <ID> (например: /give 2)")
                    continue
                try:
                    item_id = int(parts[1])
                    add_item_by_id(hero, item_id)
                except ValueError:
                    print("❌ ID должен быть числом.")
                continue

            elif raw_input == "/inv":
                inv = hero.get("inventory", [])
                if not inv:
                    print("🎒 Инвентарь пуст.")
                else:
                    print("\n🎒 ИНВЕНТАРЬ:")
                    for i, item in enumerate(inv, 1):
                        lvl = item.get("augment_level", 0)
                        bonus = item.get('bonus_atk') or item.get('bonus_def') or 0
                        item_id = item.get('id', 'N/A')
                        typ = item.get('type', 'unknown').upper()
                        print(f"[{i}] [{item_id}] {typ}: {item['name']} (+{bonus}, +{lvl})")
                continue

            # --- ОБЫЧНЫЕ КОМАНДЫ МЕНЮ ---
            try:
                choice = int(raw_input)
            except ValueError:
                print("❌ Вводи только цифры или админ-команды.")
                continue

            if choice == 0:
                print("👋 До встречи!")
                break

            elif choice == 1:
                current_loc_id = teleport_menu(current_loc_id)

            elif choice == 2 and not is_city_zone:
                mob = get_mob_for_location(current_loc_id)
                if mob:
                    run_battle(hero, mob)
                    # После боя пересчитываем статы (на случай бонусов/штрафов)
                    stats = apply_equipment(hero)
                    hero.update(stats)
                else:
                    print("⚠️ В этой локации нет мобов.")

            elif is_city_zone and choice == 3:
                shop_menu(hero, current_loc_id)
                stats = apply_equipment(hero)
                hero.update(stats)

            elif is_city_zone and choice == 4:
                blacksmith_menu(hero, current_loc_id)
                stats = apply_equipment(hero)
                hero.update(stats)

            elif choice == 5:
                inventory_menu(hero)

            elif choice == 6:
                show_character_info(hero)

            elif choice == 7:
                # Сохранение героя на сервер
                try:
                    resp = requests.post(f"{BASE_URL}/save", json=hero, timeout=5)
                    data = resp.json()
                    if data.get("success"):
                        print("✅ Игра сохранена на сервере.")
                    else:
                        msg = data.get("message", "Неизвестная ошибка сохранения")
                        print(f"❌ Ошибка сохранения: {msg}")
                except Exception as e:
                    print(f"💥 Ошибка соединения при сохранении: {e}")

            else:
                print("❌ Неверный номер пункта меню.")

    except KeyboardInterrupt:
        print("\n👋 Игра прервана пользователем.")
    except Exception as e:
        traceback.print_exc()
        print(f"\n💥 Критическая ошибка игры: {e}")
        print("Проверь, что сервер запущен и все файлы (equipment.py, battle.py и т.д.) корректны.")


if __name__ == "__main__":
