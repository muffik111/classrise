from flask import Flask, render_template, request, jsonify
from models import db, Player, ChatMessage
from datetime import datetime

app = Flask(__name__)

# Настройка БД: файл database.db создастся автоматически в папке проекта
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Создаем таблицы и тестовые данные при первом запуске
with app.app_context():
    db.create_all()
    # Создаем игрока, если его еще нет
    if not Player.query.filter_by(name='admin').first():
        admin = Player(
            name='admin',
            player_class='archer',
            level=1,
            exp=20,
            max_exp=100,
            adenas=500,
            hp=50,
            max_hp=50,
            atk=5,
            defense=3
        )
        db.session.add(admin)
        # Добавим пару сообщений в чат
        db.session.add(ChatMessage(sender='System', text='Добро пожаловать в мир RPG!', time=datetime.now().strftime('%H:%M')))
        db.session.add(ChatMessage(sender='admin', text='Проверяю статус...', time=datetime.now().strftime('%H:%M')))
        db.session.commit()

@app.route('/game')
def game():
    player = Player.query.filter_by(name='admin').first()
    messages = ChatMessage.query.order_by(ChatMessage.id).all()
    return render_template('game.html', currentPlayer=player, messages=messages)

@app.route('/api/chat', methods=['POST'])
def send_chat():
    data = request.json
    sender = data.get('sender', 'Unknown')
    text = data.get('text', '')
    if not text:
        return jsonify({"error": "Текст сообщения пуст"}), 400

    new_msg = ChatMessage(
        sender=sender,
        text=text,
        time=datetime.now().strftime('%H:%M')
    )
    db.session.add(new_msg)
    db.session.commit()
    return jsonify(new_msg.to_dict())

@app.route('/api/player/update', methods=['POST'])
def update_player():
    # Сюда можно добавить логику повышения уровня, получения аден и т.д.
    player = Player.query.filter_by(name='admin').first()
    if not player:
        return jsonify({"error": "Игрок не найден"}), 404
    
    # Пример: добавим 10 опыта
    player.exp += 10
    if player.exp >= player.max_exp:
        player.level += 1
        player.exp = 0
        player.max_exp = int(player.max_exp * 1.2)
        player.atk += 2
        player.defense += 1
        player.max_hp += 10
        player.hp = player.max_hp
    
    db.session.commit()
    return jsonify(player.to_dict())
