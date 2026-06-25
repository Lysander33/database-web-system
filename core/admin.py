from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_required, current_user
from functools import wraps

from core.models import db, Product, Order
from core.seckill import sync_stock_to_redis, stock_key, users_key
from core.redis_client import get_redis
from core.csrf import csrf_required

admin_bp = Blueprint("admin", __name__)


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
    product_count = Product.query.filter_by(is_deleted=False).count()
    order_count = Order.query.count()
    return render_template("admin/index.html", product_count=product_count, order_count=order_count)


@admin_bp.route("/products", methods=["GET", "POST"])
@admin_required
@csrf_required
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
                price_val = float(price)
                stock_val = int(stock)
                start_val = datetime.fromisoformat(start_time)
                end_val = datetime.fromisoformat(end_time)

                if price_val <= 0 or stock_val <= 0:
                    flash("价格和库存必须大于0")
                elif end_val <= start_val:
                    flash("结束时间必须晚于开始时间")
                else:
                    product = Product(
                        name=name,
                        price=price_val,
                        stock=stock_val,
                        start_time=start_val,
                        end_time=end_val,
                        description=description,
                    )
                    db.session.add(product)
                    try:
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
                        flash("创建失败，请重试")
                        return redirect(url_for("admin.manage_products"))
                    try:
                        sync_stock_to_redis(product.id)
                    except Exception:
                        pass
                    flash(f"商品「{name}」已创建")
                    current_app.logger.info("Admin %s created product '%s'", current_user.username, name)
            except ValueError:
                flash("价格、库存或时间格式有误")
        return redirect(url_for("admin.manage_products"))

    page = request.args.get("page", 1, type=int)
    pagination = Product.query.filter_by(is_deleted=False).order_by(Product.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template("admin/products.html", products=pagination.items, pagination=pagination)


@admin_bp.route("/products/<int:product_id>/toggle", methods=["POST"])
@admin_required
@csrf_required
def toggle_product(product_id):
    product = Product.query.get_or_404(product_id)
    product.is_active = not product.is_active
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("操作失败")
        return redirect(url_for("admin.manage_products"))
    flash(f"商品「{product.name}」已{'上架' if product.is_active else '下架'}")
    return redirect(url_for("admin.manage_products"))


@admin_bp.route("/products/<int:product_id>/delete", methods=["POST"])
@admin_required
@csrf_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    product.is_deleted = True
    product.is_active = False
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("删除失败，请重试")
        return redirect(url_for("admin.manage_products"))
    try:
        r = get_redis()
        r.delete(stock_key(product_id), users_key(product_id))
    except Exception:
        pass
    flash(f"商品「{product.name}」已删除")
    current_app.logger.info("Admin %s soft-deleted product '%s'", current_user.username, product.name)
    return redirect(url_for("admin.manage_products"))


@admin_bp.route("/orders")
@admin_required
def list_orders():
    page = request.args.get("page", 1, type=int)
    pagination = (
        Order.query
        .options(db.joinedload(Order.user), db.joinedload(Order.product))
        .order_by(Order.created_at.desc())
        .paginate(page=page, per_page=20, error_out=False)
    )
    return render_template("admin/orders.html", orders=pagination.items, pagination=pagination)
