from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Player(db.Model):
    __tablename__ = 'players'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    player_class = db.Column(db.String(50), nullable=False)
    level = db.Column(db.Integer, default=1)
    exp = db.Column(db.Integer, default=0)
    max_exp = db.Column(db.Integer, default=100)
    adenas = db.Column(db.Integer, default=500)
    hp = db.Column(db.Integer, default=50)
    max_hp = db.Column(db.Integer, default=50)
    atk = db.Column(db.Integer, default=5)
    defense = db.Column(db.Integer, default=3)

def to_dict(self):
    return {
        "name": self.name,
        "player_class": self.player_class,      # Лучше явно, чем "class"
        "level": self.level,
        "exp": self.exp,
        "max_exp": self.max_exp,
        "adenas": self.adenas,
        "hp": self.hp,
        "max_hp": self.max_hp,
        "atk": self.atk,
        "defense": self.defense                 # Используй полное имя, а не "def"
    }


class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    id = db.Column(db.Integer, primary_key=True)
    sender = db.Column(db.String(50), nullable=False)
    text = db.Column(db.Text, nullable=False)
    time = db.Column(db.String(20), nullable=False)
