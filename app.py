from flask import Flask, render_template
from flask_login import LoginManager
from config import Config
from core.models import db, User


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

    from core.auth import auth_bp
    from core.seckill import seckill_bp
    from core.admin import admin_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(seckill_bp, url_prefix="/")
    app.register_blueprint(admin_bp, url_prefix="/admin")

    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html"), 404

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
