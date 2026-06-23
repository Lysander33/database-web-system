import logging
import os
from flask import Flask, render_template
from flask_login import LoginManager
from config import Config
from core.models import db, User, Product
from core.redis_client import init_redis
from core.seckill import sync_stock_to_redis
from core.csrf import generate_csrf_token

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


login_manager = LoginManager()
login_manager.login_view = "auth.login_page"
login_manager.login_message = "请先登录"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)

    try:
        init_redis(app)
    except Exception:
        app.logger.warning("Redis 未启动，秒杀限流和原子库存功能不可用")

    from core.auth import auth_bp
    from core.seckill import seckill_bp
    from core.admin import admin_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(seckill_bp, url_prefix="/")
    app.register_blueprint(admin_bp, url_prefix="/admin")

    @app.context_processor
    def inject_csrf():
        return {"csrf_token": generate_csrf_token}

    @app.context_processor
    def inject_stats():
        try:
            count = Product.query.count()
        except Exception:
            count = 0
        return {"total_product_count": count}

    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("500.html"), 500

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    with app.app_context():
        try:
            products = db.session.query(Product).all()
            for p in products:
                sync_stock_to_redis(p.id)
        except Exception:
            app.logger.warning("Redis 库存同步失败")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=os.getenv("FLASK_DEBUG", "0") == "1")
