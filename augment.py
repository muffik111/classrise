# augment.py
import random
from equipment import AUGMENT_DATA

def get_current_augment_level(item):
    return item.get("augment_level", 0)

def can_augment(item):
    """Можно ли аугментировать этот предмет (макс. уровень +10)"""
    lvl = get_current_augment_level(item)
    return lvl < 10

def get_augment_cost_and_chance(item_type, current_level):
    if current_level >= 10:
        return 0, 0.0
    data_list = AUGMENT_DATA.get(item_type)
    if not data_list or current_level >= len(data_list):
        return 0, 0.0
    entry = data_list[current_level + 1]  # следующий уровень
    return entry["cost_aden"], entry["chance"]

def perform_augment(hero, item, target_level=None):
    """
    Пытается аугментировать предмет.
    target_level = None означает +1 к текущему.
    Возвращает (success: bool, message: str)
    """
    if item is None:
        return False, "❌ Нет предмета для аугментации."

    if not can_augment(item):
        return False, f"❌ Предмет уже на максимальном уровне аугментации (+10)."

    current_lvl = get_current_augment_level(item)
    next_lvl = target_level if target_level is not None else current_lvl + 1
    if next_lvl > 10 or next_lvl <= current_lvl:
        return False, "❌ Недопустимый уровень аугментации."

    cost, chance = get_augment_cost_and_chance(item["type"], current_lvl)
    # Для упрощения делаем только +1 за раз. Если хочешь +N — можно добавить цикл.
    if next_lvl != current_lvl + 1:
        return False, "❌ Сейчас поддерживается только повышение на +1 за раз."

    if hero["aden"] < cost:
        return False, f"❌ Недостаточно аден. Нужно {cost}, у тебя {hero['aden']}."

    roll = random.random()
    if roll <= chance:
        # Успех
        item["augment_level"] = next_lvl
        bonus_key = "bonus_atk" if item["type"] == "weapon" else "bonus_def"
        base_bonus = item.get(bonus_key, 0)
        new_bonus = base_bonus + next_lvl * 5  # +5 за каждый уровень аугмента
        item[bonus_key] = new_bonus
        hero["aden"] -= cost
        return True, f"✅ Аугментация успешна! Теперь предмет +{next_lvl} (+{new_bonus} к стате)."
    else:
        # Провал
        hero["aden"] -= cost  # деньги тратятся всегда
        return False, f"❌ Аугментация не удалась! Ты потерял {cost} аден."

def blacksmith_menu(hero):
    """Меню Кузнеца: выбор предмета из инвентаря/экипировки, попытка аугментации"""
    print("\n🔨 КУЗНЕЦ: Аугментация предметов")
    
    # Собираем все доступные предметы для аугментации: инвентарь + экипировка
    candidates = []
    
    # Из инвентаря
    for item in hero["inventory"]:
        if can_augment(item):
            candidates.append(("inventory", item))
    
    # Из экипировки
    eq = hero["equipment"]
    for slot in ["weapon", "armor"]:
        item = eq.get(slot)
        if item and can_augment(item):
            candidates.append(("equipment", item))

    if not candidates:
        print("😕 У тебя нет предметов, которые можно аугментировать (или все уже +10).")
        input("Нажми Enter, чтобы вернуться… ")
        return

    print("Доступные предметы для аугментации:")
    for idx, (loc, item) in enumerate(candidates, 1):
        lvl = get_current_augment_level(item)
        cost, chance = get_augment_cost_and_chance(item["type"], lvl)
        bonus_key = "bonus_atk" if item["type"] == "weapon" else "bonus_def"
        bonus = item.get(bonus_key, 0)
        loc_name = "🎒 Инвентарь" if loc == "inventory" else "🛡 Экипировка"
        print(f"[{idx}] {loc_name} — {item['name']} (+{lvl}) | Стоимость: {cost} | Шанс: {chance:.0%}")

    print("[0] Вернуться к Кузнецу / выйти")

    while True:
        try:
            choice = input("Выбери предмет для аугментации: ").strip()
            if choice == "0":
                return
            if not choice.isdigit():
                continue
            idx = int(choice)
            if 1 <= idx <= len(candidates):
                loc, item = candidates[idx - 1]
                break
            else:
                print("Нет такого предмета.")
        except Exception:
            print("Ошибка ввода.")

    # Подтверждение
    lvl = get_current_augment_level(item)
    cost, chance = get_augment_cost_and_chance(item["type"], lvl)
    confirm = input(f"Аугментировать {item['name']} с +{lvl} до +{lvl+1}? Стоимость: {cost}, шанс успеха: {chance:.0%}. (y/n): ").strip().lower()
    if confirm != "y":
        print("Аугментация отменена.")
        return

    success, msg = perform_augment(hero, item)
    print(msg)

    if success:
        # Если предмет был в экипировке — статы уже должны пересчитываться в equip_item или при загрузке
        # Для оружия/брони лучше пересчитать статы героя сразу
        recalc_stats(hero)

    input("Нажми Enter, чтобы продолжить… ")

def recalc_stats(hero):
    """Пересчитывает атаку/защиту героя на основе экипировки и уровней аугмента"""
    base_atk = hero["base_stats"]["base_attack"]
    base_def = hero["base_stats"]["base_defense"]
    
    w = hero["equipment"].get("weapon")
    a = hero["equipment"].get("armor")
    
    bonus_atk = 0
    if w:
        bonus_atk += w.get("bonus_atk", 0)
    
    bonus_def = 0
    if a:
        bonus_def += a.get("bonus_def", 0)
    
    hero["attack"] = base_atk + bonus_atk
    hero["defense"] = base_def + bonus_def
