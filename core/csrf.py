import secrets
from functools import wraps
from flask import session, request, abort


def generate_csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


def csrf_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            token = request.form.get("_csrf_token")
            if not token or not secrets.compare_digest(token, session.get("_csrf_token", "")):
                abort(400, description="CSRF 验证失败")
        return f(*args, **kwargs)
    return decorated
