# battle.py
import random
from mobs import MOBS, roll_loot
from equipment import EQUIPMENT_ITEMS

def check_level_up(player):
    """
    Повышает уровень только по EXP.
    НЕ меняет attack/defense напрямую — это делает recalc_stats.
    Меняет: level, exp, max_hp, current_hp (если нужно).
    """
    if "level" not in player:
        player["level"] = 1
    if "exp" not in player:
        player["exp"] = 0

    base_hp = player.get("base_hp", 100)

    while True:
        required_exp = 100 * player["level"]
        if player["exp"] < required_exp:
            break

        # Повышаем уровень
        player["level"] += 1
        player["exp"] -= required_exp

        lvl = player["level"]
        # Только HP растёт с уровнем
        player["max_hp"] = int(base_hp * (1 + 0.15 * (lvl - 1)))

        # Если текущее HP больше нового максимума — обрезаем
        if player.get("current_hp", 0) > player["max_hp"]:
            player["current_hp"] = player["max_hp"]

    return player


def run_battle(player, mob_id):
    """
    Возвращает JSON-структуру боя: раунды, кто победил, лут, изменения игрока.
    Никаких print, никаких циклов «пока не умрёт» в смысле ожидания.
    """
    mob = MOBS.get(mob_id)
    if not mob:
        return {
            "success": False,
            "message": f"Моб {mob_id} не существует в базе",
            "won": False,
        }

    p_hp = player["current_hp"]
    m_hp = mob["hp"]

    rounds = []
    round_num = 1

    # Начальный лог
    rounds.append({
        "round": 0,
        "text": f"🗡️ Бой начался: {player.get('name', 'Герой')} vs {mob['name']} (HP: {p_hp} vs {m_hp})",
        "player_hp": p_hp,
        "mob_hp": m_hp,
    })

    max_rounds = 100  # защита от бесконечного цикла
    won = False

    while p_hp > 0 and m_hp > 0 and round_num <= max_rounds:
        # Ход игрока
        dmg = max(1, player["attack"] - mob["defense"])
        m_hp -= dmg
        rounds.append({
            "round": round_num,
            "text": f"Раунд {round_num}: Вы нанесли {dmg} урона",
            "player_hp": p_hp,
            "mob_hp": max(0, m_hp),
        })

        if m_hp <= 0:
            won = True
            player["exp"] += mob["exp"]
            player = check_level_up(player)
            # Статы пересчитаем после боя, чтобы бонусы от экипировки/аугмента применились

            loot_id = roll_loot(mob_id)
            if loot_id:
                player["inventory"].append(loot_id)
                item_name = EQUIPMENT_ITEMS.get(loot_id, {}).get("name", "Неизвестный предмет")
                rounds.append({
                    "round": round_num,
                    "text": f"🎉 С моба выпал: {item_name}!",
                    "player_hp": p_hp,
                    "mob_hp": 0,
                })
            else:
                rounds.append({
                    "round": round_num,
                    "text": "⚠️ С моба ничего не выпало.",
                    "player_hp": p_hp,
                    "mob_hp": 0,
                })
            break

        # Ход моба
        dmg_mob = max(1, mob["attack"] - player["defense"])
        p_hp -= dmg_mob
        rounds.append({
            "round": round_num,
            "text": f"Раунд {round_num}: Моб нанёс {dmg_mob} урона",
            "player_hp": max(0, p_hp),
            "mob_hp": m_hp,
        })

        if p_hp <= 0:
            rounds.append({
                "round": round_num,
                "text": "💀 Вы погибли!",
                "player_hp": 0,
                "mob_hp": m_hp,
            })
            break

        round_num += 1

    player["current_hp"] = max(0, p_hp)

    # ПОСЛЕ боя пересчитываем итоговые статы (чтобы учесть аугментацию и экипировку)
    from augment import recalc_stats
    recalc_stats(player)

    return {
        "success": True,
        "won": won,
        "rounds": rounds,
        "final_player_hp": player["current_hp"],
        "exp_gained": mob["exp"] if won else 0,
        "loot": loot_id if won and loot_id else None,
        "player_updated": {
            "level": player["level"],
            "exp": player["exp"],
            "aden": player.get("aden", 0),
            "attack": player["attack"],
            "defense": player["defense"],
            "max_hp": player["max_hp"],
            "current_hp": player["current_hp"],
        },
    }
