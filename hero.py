import hashlib

CLASS_TEMPLATES = {
    "Воин": {
        "base_hp": 120,
        "base_attack": 55,
        "base_defense": 15,
        "crit_chance": 0.10,
        "crit_mult": 1.8
    },
    "Лучник": {
        "base_hp": 90,
        "base_attack": 260,
        "base_defense": 8,
        "crit_chance": 0.25,
        "crit_mult": 2.0
    },
    "Танк": {
        "base_hp": 140,
        "base_attack": 48,
        "base_defense": 22,
        "crit_chance": 0.05,
        "crit_mult": 1.5
    },
    "Друид": {
        "base_hp": 100,
        "base_attack": 42,
        "base_defense": 12,
        "crit_chance": 0.15,
        "crit_mult": 1.7
    }
}

MAX_LEVEL = 100


def hash_password(password: str) -> str:
    """Простой хеш пароля (для примера; в продакшене используй bcrypt/argon2)"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def create_hero_with_password(name, cls, password):
    if cls not in CLASS_TEMPLATES:
        raise ValueError(f"Неизвестный класс: {cls}")

    base = CLASS_TEMPLATES[cls]

    player = {
        "name": name,
        "class": cls,
        "level": 1,
        "exp": 0,
        "next_level_exp": 100,
        "aden": 1000,
        # Статы сразу берём из шаблона
        "base_hp": base["base_hp"],
        "base_attack": base["base_attack"],
        "base_defense": base["base_defense"],
        # Текущие статы = базовые
        "max_hp": base["base_hp"],
        "attack": base["base_attack"],
        "defense": base["base_defense"],
        "current_hp": base["base_hp"],
        "crit_chance": base["crit_chance"],
        "crit_mult": base["crit_mult"],
        "inventory": [],
        "equipment": {"weapon": None, "armor": None},
        "location_id": 1,
        "password_hash": hash_password(password),
        # Флаг админа можно добавить здесь, если нужно для тестов
        "is_admin": False,
    }
    return player


def level_up(player):
    """Повышает уровень и увеличивает статы"""
    if player["level"] >= MAX_LEVEL:
        print("✅ Максимальный уровень достигнут!")
        return player

    player["level"] += 1
    base = CLASS_TEMPLATES[player["class"]]
    lvl = player["level"]

    # Рост характеристик на уровень (коэффициенты можно подкрутить)
    player["max_hp"] = int(base["base_hp"] * (1 + 0.15 * (lvl - 1)))
    player["attack"] = int(base["base_attack"] * (1 + 0.12 * (lvl - 1)))
    player["defense"] = int(base["base_defense"] * (1 + 0.10 * (lvl - 1)))

    # Восстанавливаем HP после левелапа
    player["current_hp"] = player["max_hp"]

    # Увеличиваем порог следующего уровня
    player["next_level_exp"] = player.get("next_level_exp", 100) + 50

    print(f"🎉 Уровень повышен: {player['level']}")
    return player
