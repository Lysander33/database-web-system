import re
from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from core.models import db, User
from core.csrf import csrf_required
from core.limiter import check_rate_limit

auth_bp = Blueprint("auth", __name__)


def _is_strong_password(pw):
    return len(pw) >= 8 and bool(re.search(r"[a-zA-Z]", pw)) and bool(re.search(r"\d", pw))


def _safe_next_url(raw):
    if raw and (raw.startswith("/") and not raw.startswith("//")):
        return raw
    return None


@auth_bp.route("/login", methods=["GET", "POST"])
@csrf_required
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for("seckill.index"))

    if request.method == "POST":
        allowed, _ = check_rate_limit(f"login:{request.remote_addr}", max_requests=10, window=60)
        if not allowed:
            flash("请求过于频繁，请稍后再试")
            return render_template("login.html")

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            next_page = _safe_next_url(request.args.get("next"))
            return redirect(next_page or url_for("seckill.index"))
        flash("用户名或密码错误")
        current_app.logger.warning("Failed login attempt for username: %s from IP: %s", username, request.remote_addr)

    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
@csrf_required
def register_page():
    if current_user.is_authenticated:
        return redirect(url_for("seckill.index"))

    if request.method == "POST":
        allowed, _ = check_rate_limit(f"register:{request.remote_addr}", max_requests=5, window=300)
        if not allowed:
            flash("请求过于频繁，请5分钟后再试")
            return render_template("register.html")

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("用户名和密码不能为空")
        elif len(username) < 2 or len(username) > 20:
            flash("用户名长度应在2-20个字符之间")
        elif not re.match(r"^[\w一-鿿-]+$", username):
            flash("用户名只能包含字母、数字、下划线和中文")
        elif not _is_strong_password(password):
            flash("密码至少8位，且必须包含字母和数字")
        elif User.query.filter_by(username=username).first():
            flash("用户名已存在")
        else:
            try:
                user = User(
                    username=username,
                    password_hash=generate_password_hash(password),
                )
                db.session.add(user)
                db.session.commit()
                flash("注册成功，请登录")
                return redirect(url_for("auth.login_page"))
            except Exception:
                db.session.rollback()
                flash("注册失败，请重试")

    return render_template("register.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("seckill.index"))
