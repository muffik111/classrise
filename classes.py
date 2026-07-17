CLASS_STATS = {
    "Воин": {"base_hp": 120, "base_attack": 15, "base_defense": 10},
    "Маг": {"base_hp": 80, "base_attack": 25, "base_defense": 5},
    "Лучник": {"base_hp": 90, "base_attack": 20, "base_defense": 7},
    "Танк": {"base_hp": 140, "base_attack": 12, "base_defense": 15},
    "Друид": {"base_hp": 100, "base_attack": 18, "base_defense": 8},
}

def get_class_stats(cls_name):
    if not cls_name:
        return None
    return CLASS_STATS.get(cls_name.capitalize())
