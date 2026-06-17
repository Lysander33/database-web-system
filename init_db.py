from app import create_app
from core.models import db, User, Product
from werkzeug.security import generate_password_hash
from datetime import datetime, timezone, timedelta


def init():
    app = create_app()
    with app.app_context():
        db.create_all()

        if not User.query.filter_by(username="admin").first():
            db.session.add(User(
                username="admin",
                password_hash=generate_password_hash("admin123"),
                is_admin=True,
            ))

        if not User.query.filter_by(username="user1").first():
            db.session.add(User(
                username="user1",
                password_hash=generate_password_hash("123456"),
            ))

        if not Product.query.first():
            now = datetime.now(timezone.utc)
            db.session.add(Product(
                name="iPhone 15 Pro 秒杀",
                description="限时秒杀，先到先得！",
                price=0.01,
                stock=10,
                start_time=now - timedelta(minutes=1),
                end_time=now + timedelta(hours=24),
            ))

        db.session.commit()
        print("Database initialized with default users and demo product.")


if __name__ == "__main__":
    init()
