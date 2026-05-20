from app import app
from models import db, User

with app.app_context():
    users = User.query.all()
    print(f"Total users: {len(users)}")
    for u in users:
        print(f"ID: {u.id}, Email: {u.email}, Role: {u.role}")
