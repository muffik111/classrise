import random
from mobs import MOBS, roll_loot
from equipment import EQUIPMENT_ITEMS

def check_level_up(player):
    """Проверяет EXP и повышает уровень, пока хватает опыта."""
    # Если ключей нет — создаём дефолтные значения
    if "level" not in player:
        player["level"] = 1
    if "exp" not in player:
        player["exp"] = 0

    base_hp = player.get("base_hp", 100)
    base_attack = player.get("base_attack", 10)
    base_defense = player.get("base_defense", 5)

    while True:
        required_exp = 100 * player["level"]
        if player["exp"] < required_exp:
            break

        # Повышаем уровень
        player["level"] += 1
        player["exp"] -= required_exp

        # Пересчитываем статы по формуле
        lvl = player["level"]
        player["max_hp"] = int(base_hp * (1 + 0.15 * (lvl - 1)))
        player["attack"] = int(base_attack * (1 + 0.12 * (lvl - 1)))
        player["defense"] = int(base_defense * (1 + 0.10 * (lvl - 1)))

        # Если текущее HP больше нового максимума (например, баффнули и не сняли) — обрезаем
        if player.get("current_hp", 0) > player["max_hp"]:
            player["current_hp"] = player["max_hp"]

    return player

def run_battle(player, mob_id):
    # Диагностика: если моб не найден — сразу сообщаем
    mob = MOBS.get(mob_id)
    if not mob:
        print(f"[DEBUG BATTLE] Моб {mob_id} не найден в MOBS")
        return {"success": False, "message": f"Моб {mob_id} не существует в базе"}

    p_hp = player["current_hp"]
    m_hp = mob["hp"]

    round_num = 1
    log = []

    # Первая строка лога — чтобы точно было видно, что бой стартовал
    log.append(f"🗡️ Бой начался: {player.get('name', 'Герой')} vs {mob['name']} (HP: {p_hp} vs {m_hp})")

    while p_hp > 0 and m_hp > 0:
        # Ход игрока
        dmg = max(1, player["attack"] - mob["defense"])
        m_hp -= dmg
        log.append(f"Раунд {round_num}: Вы нанесли {dmg} урона ({m_hp} HP у моба)")

        if m_hp <= 0:
            player["exp"] += mob["exp"]
            player = check_level_up(player)
            log.append(f"Победа! Вы получили {mob['exp']} EXP.")

            loot_id = roll_loot(mob_id)
            if loot_id:
                player["inventory"].append(loot_id)
                item_name = EQUIPMENT_ITEMS.get(loot_id, {}).get("name", "Неизвестный предмет")
                log.append(f"🎉 С моба выпал: {item_name}!")
            else:
                log.append("⚠️ С моба ничего не выпало (но шанс был 100%)")
            break

        # Ход моба
        dmg_mob = max(1, mob["attack"] - player["defense"])
        p_hp -= dmg_mob
        log.append(f"Раунд {round_num}: Моб нанёс {dmg_mob} урона ({p_hp} HP у вас)")

        if p_hp <= 0:
            log.append("💀 Вы погибли!")
            break

        round_num += 1

    player["current_hp"] = max(0, p_hp)

    # Гарантируем, что message не пустой
    final_message = "\n".join(log)
    if not final_message:
        final_message = "[ОШИБКА: лог боя пуст]"

    return {
        "success": True,
        "message": final_message,
        "won": m_hp <= 0,
        "player_hp": player["current_hp"],
        "mob_name": mob["name"]
    }
