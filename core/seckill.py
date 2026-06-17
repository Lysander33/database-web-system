from datetime import datetime, timezone

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import update as sql_update

from core.models import db, Product, Order

seckill_bp = Blueprint("seckill", __name__)


def _deduct_stock(product_id):
    stmt = (
        sql_update(Product)
        .where(Product.id == product_id, Product.stock > 0)
        .values(stock=Product.stock - 1)
    )
    result = db.session.execute(stmt)
    db.session.commit()
    return result.rowcount == 1


def _now():
    return datetime.now(timezone.utc)


@seckill_bp.route("/")
def index():
    products = Product.query.filter_by(is_active=True).order_by(Product.start_time.asc()).all()
    now = _now()
    return render_template("index.html", products=products, now=now)


@seckill_bp.route("/product/<int:product_id>")
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template("product_detail.html", product=product, now=_now())


@seckill_bp.route("/api/seckill", methods=["POST"])
@login_required
def do_seckill():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "msg": "请求数据无效"}), 400

    product_id = data.get("product_id")
    if not product_id:
        return jsonify({"success": False, "msg": "缺少商品ID"}), 400

    product = Product.query.get(product_id)
    if not product or not product.is_active:
        return jsonify({"success": False, "msg": "商品不存在或已下架"}), 400

    now = _now()
    if now < product.start_time:
        return jsonify({"success": False, "msg": "秒杀尚未开始"}), 400
    if now > product.end_time:
        return jsonify({"success": False, "msg": "秒杀已结束"}), 400

    existing = Order.query.filter_by(user_id=current_user.id, product_id=product_id).first()
    if existing:
        return jsonify({"success": False, "msg": "您已抢购过该商品"}), 400

    if not _deduct_stock(product_id):
        return jsonify({"success": False, "msg": "已售罄"}), 400

    order = Order(user_id=current_user.id, product_id=product_id, status="success")
    db.session.add(order)
    db.session.commit()

    return jsonify({"success": True, "msg": "抢购成功！", "order_id": order.id})


@seckill_bp.route("/orders")
@login_required
def my_orders():
    orders = (
        Order.query
        .filter_by(user_id=current_user.id)
        .order_by(Order.created_at.desc())
        .all()
    )
    return render_template("orders.html", orders=orders)
