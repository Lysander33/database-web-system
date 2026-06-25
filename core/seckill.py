from datetime import datetime

from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import update as sql_update

from core.models import db, Product, Order
from core.redis_client import get_redis
from core.limiter import check_rate_limit

seckill_bp = Blueprint("seckill", __name__)

_LUA_SECKILL = """
local stock_key = KEYS[1]
local users_key = KEYS[2]
local user_id = ARGV[1]

if redis.call('SISMEMBER', users_key, user_id) == 1 then
    return -1
end

local stock = redis.call('GET', stock_key)
if not stock or tonumber(stock) <= 0 then
    return 0
end

local new_stock = redis.call('DECR', stock_key)
if new_stock < 0 then
    redis.call('INCR', stock_key)
    return 0
end

redis.call('SADD', users_key, user_id)
return 1
"""


def stock_key(product_id):
    return f"seckill:stock:{product_id}"


def users_key(product_id):
    return f"seckill:users:{product_id}"


def sync_stock_to_redis(product_id):
    """将商品库存从数据库同步到 Redis，应用启动时及库存变更后调用。"""
    r = get_redis()
    product = db.session.get(Product, product_id)
    if product:
        r.set(stock_key(product_id), product.stock)


def _deduct_stock(product_id):
    """通过 Redis Lua 脚本原子性扣减库存。"""
    r = get_redis()
    result = r.eval(_LUA_SECKILL, 2, stock_key(product_id), users_key(product_id), str(current_user.id))
    return result  # 1=成功, 0=已售罄, -1=已购买过


def _now():
    return datetime.now()


@seckill_bp.route("/")
def index():
    products = Product.query.filter_by(is_active=True, is_deleted=False).order_by(Product.start_time.asc()).all()
    now = _now()
    return render_template("index.html", products=products, now=now)


@seckill_bp.route("/product/<int:product_id>")
def product_detail(product_id):
    product = Product.query.filter_by(id=product_id, is_deleted=False).first_or_404()
    return render_template("product_detail.html", product=product, now=_now())


@seckill_bp.route("/api/seckill", methods=["POST"])
@login_required
def do_seckill():
    allowed, remaining = check_rate_limit(current_user.id)
    if not allowed:
        return jsonify({"success": False, "msg": "请求过于频繁，请稍后再试"}), 429

    data = request.get_json()
    if not data:
        return jsonify({"success": False, "msg": "请求数据无效"}), 400

    product_id = data.get("product_id")
    if not product_id:
        return jsonify({"success": False, "msg": "缺少商品ID"}), 400

    product = Product.query.get(product_id)
    if not product or not product.is_active or product.is_deleted:
        return jsonify({"success": False, "msg": "商品不存在或已下架"}), 400

    now = _now()
    if now < product.start_time:
        return jsonify({"success": False, "msg": "秒杀尚未开始"}), 400
    if now > product.end_time:
        return jsonify({"success": False, "msg": "秒杀已结束"}), 400

    result = _deduct_stock(product_id)
    if result == -1:
        return jsonify({"success": False, "msg": "您已抢购过该商品"}), 400
    if result == 0:
        return jsonify({"success": False, "msg": "已售罄"}), 400

    result = db.session.execute(
        sql_update(Product)
        .where(Product.id == product_id, Product.stock > 0)
        .values(stock=Product.stock - 1)
    )
    if result.rowcount == 0:
        db.session.rollback()
        return jsonify({"success": False, "msg": "抢购失败，请重试"}), 400

    order = Order(user_id=current_user.id, product_id=product_id, status="success")
    db.session.add(order)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "msg": "系统繁忙，请重试"}), 500

    current_app.logger.info("Seckill success: user=%s product=%s order=%s", current_user.id, product_id, order.id)
    return jsonify({"success": True, "msg": "抢购成功！", "order_id": order.id})


@seckill_bp.route("/api/order/<int:order_id>/cancel", methods=["POST"])
@login_required
def cancel_order(order_id):
    order = Order.query.filter_by(id=order_id, user_id=current_user.id).first()
    if not order:
        return jsonify({"success": False, "msg": "订单不存在"}), 404

    if order.status != "success":
        return jsonify({"success": False, "msg": "该订单无法取消"}), 400

    order.status = "cancelled"

    product = Product.query.get(order.product_id)
    if product and not product.is_deleted:
        db.session.execute(
            sql_update(Product)
            .where(Product.id == order.product_id)
            .values(stock=Product.stock + 1)
        )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "msg": "系统繁忙，请重试"}), 500

    try:
        r = get_redis()
        r.incr(stock_key(order.product_id))
        r.srem(users_key(order.product_id), str(current_user.id))
    except Exception:
        pass

    current_app.logger.info("Order cancelled: user=%s order=%s product=%s", current_user.id, order_id, order.product_id)
    return jsonify({"success": True, "msg": "订单已取消"})


@seckill_bp.route("/api/order/<int:order_id>/delete", methods=["POST"])
@login_required
def delete_order(order_id):
    order = Order.query.filter_by(id=order_id, user_id=current_user.id).first()
    if not order:
        return jsonify({"success": False, "msg": "订单不存在"}), 404

    if order.status != "cancelled":
        return jsonify({"success": False, "msg": "只能删除已取消的订单"}), 400

    db.session.delete(order)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"success": False, "msg": "系统繁忙，请重试"}), 500

    current_app.logger.info("Order deleted: user=%s order=%s", current_user.id, order_id)
    return jsonify({"success": True, "msg": "订单已删除"})


@seckill_bp.route("/orders")
@login_required
def my_orders():
    page = request.args.get("page", 1, type=int)
    pagination = (
        Order.query
        .options(db.joinedload(Order.product))
        .filter_by(user_id=current_user.id)
        .order_by(Order.created_at.desc())
        .paginate(page=page, per_page=20, error_out=False)
    )
    return render_template("orders.html", orders=pagination.items, pagination=pagination)
