from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from functools import wraps

from core.models import db, Product, Order
from core.seckill import sync_stock_to_redis

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(f):
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            flash("需要管理员权限")
            return redirect(url_for("seckill.index"))
        return f(*args, **kwargs)
    return wrapper


@admin_bp.route("/")
@admin_required
def index():
    product_count = Product.query.count()
    order_count = Order.query.count()
    return render_template("admin/index.html", product_count=product_count, order_count=order_count)


@admin_bp.route("/products", methods=["GET", "POST"])
@admin_required
def manage_products():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        price = request.form.get("price", "").strip()
        stock = request.form.get("stock", "").strip()
        start_time = request.form.get("start_time", "").strip()
        end_time = request.form.get("end_time", "").strip()
        description = request.form.get("description", "").strip()

        if not (name and price and stock and start_time and end_time):
            flash("请填写所有必填字段")
        else:
            try:
                product = Product(
                    name=name,
                    price=float(price),
                    stock=int(stock),
                    start_time=datetime.fromisoformat(start_time),
                    end_time=datetime.fromisoformat(end_time),
                    description=description,
                )
                db.session.add(product)
                db.session.commit()
                sync_stock_to_redis(product.id)
                flash(f"商品「{name}」已创建")
            except ValueError:
                flash("价格、库存或时间格式有误")
        return redirect(url_for("admin.manage_products"))

    products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template("admin/products.html", products=products)


@admin_bp.route("/products/<int:product_id>/toggle", methods=["POST"])
@admin_required
def toggle_product(product_id):
    product = Product.query.get_or_404(product_id)
    product.is_active = not product.is_active
    db.session.commit()
    flash(f"商品「{product.name}」已{'上架' if product.is_active else '下架'}")
    return redirect(url_for("admin.manage_products"))


@admin_bp.route("/orders")
@admin_required
def list_orders():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template("admin/orders.html", orders=orders)
