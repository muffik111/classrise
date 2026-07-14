import requests

BASE = "http://127.0.0.1:5000"

# 1. Сначала создаём героя, чтобы появился player_id
r = requests.post(f"{BASE}/create-hero", json={"name": "ТестГерой", "cls": "Воин"})
data = r.json()
print("Создание героя:", data)

if not data.get("success"):
    print("Не удалось создать героя. Проверь, запущен ли сервер.")
    exit()

player_id = data["player_id"]
print(f"Получен player_id: {player_id}")

# 2. Теперь правильно запрашиваем статус — через POST с player_id в JSON
r = requests.post(f"{BASE}/status", json={"player_id": player_id})
print("Статус героя:", r.json())

# 3. Можно сразу проверить бой
r = requests.post(f"{BASE}/fight", json={"player_id": player_id})
print("Результат боя:", r.json())
