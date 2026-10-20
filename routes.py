"""HTTP layer: storefront page and JSON API for the Lúmen store."""

import secrets
from decimal import ROUND_HALF_UP, Decimal

from flask import Blueprint, jsonify, render_template, request
from sqlalchemy.exc import IntegrityError

from models import Order, OrderItem, Product, db

#: Fixed IVA rate applied to the order subtotal.
TAX_RATE = Decimal("0.21")
#: Two-decimal money quantum.
CENT = Decimal("0.01")
#: Maximum attempts to find a free order number.
ORDER_NUMBER_ATTEMPTS = 10

main = Blueprint("main", __name__)


def _parse_bound(raw):
    """Return a Decimal bound from a query parameter, or None when unusable."""
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except (ArithmeticError, ValueError):
        return None


def _quantize(value):
    """Round a money amount to two decimals."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _generate_order_number():
    """Return an unused order number in the ``LUM-00000`` format."""
    for _ in range(ORDER_NUMBER_ATTEMPTS):
        candidate = f"LUM-{secrets.randbelow(100000):05d}"
        taken = db.session.scalar(
            db.select(Order.id).where(Order.order_number == candidate)
        )
        if taken is None:
            return candidate
    return None


@main.get("/")
def index():
    """Render the storefront."""
    return render_template("parcial2.html")


@main.get("/api/products")
def list_products():
    """Return the catalog, optionally filtered server-side."""
    statement = db.select(Product)

    search = (request.args.get("q") or "").strip()
    if search:
        pattern = f"%{search}%"
        statement = statement.where(
            db.or_(
                Product.title.ilike(pattern),
                Product.description.ilike(pattern),
            )
        )

    category = (request.args.get("category") or "").strip()
    if category and category.lower() != "all":
        statement = statement.where(Product.category == category)

    min_price = _parse_bound(request.args.get("min_price"))
    if min_price is not None:
        statement = statement.where(Product.price >= min_price)

    max_price = _parse_bound(request.args.get("max_price"))
    if max_price is not None:
        statement = statement.where(Product.price <= max_price)

    statement = statement.order_by(Product.id)
    products = db.session.scalars(statement).all()

    return jsonify(
        {"products": [product.to_dict() for product in products],
         "count": len(products)}
    )


@main.get("/api/categories")
def list_categories():
    """Return the distinct categories present in the catalog."""
    rows = db.session.execute(
        db.select(Product.category, Product.category_label)
        .distinct()
        .order_by(Product.category_label)
    ).all()

    categories = [{"value": row[0], "label": row[1]} for row in rows]
    return jsonify({"categories": categories})


@main.post("/api/checkout")
def checkout():
    """Validate a cart, deduct stock and persist the order."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return jsonify({"error": "'items' must be a non-empty list"}), 400

    quantities = {}
    for raw_line in items:
        if not isinstance(raw_line, dict):
            return jsonify({"error": "Each item must be an object"}), 400

        product_id = raw_line.get("product_id")
        quantity = raw_line.get("quantity")

        if isinstance(product_id, bool) or not isinstance(product_id, int):
            return jsonify({"error": "product_id must be an integer"}), 400
        if isinstance(quantity, bool) or not isinstance(quantity, int):
            return jsonify({"error": "quantity must be an integer"}), 400
        if quantity <= 0:
            return jsonify({"error": "quantity must be greater than zero"}), 400

        quantities[product_id] = quantities.get(product_id, 0) + quantity

    products = {
        product.id: product
        for product in db.session.scalars(
            db.select(Product).where(Product.id.in_(quantities.keys()))
        ).all()
    }

    for product_id, quantity in quantities.items():
        product = products.get(product_id)
        if product is None:
            return jsonify({"error": f"Unknown product_id: {product_id}"}), 400
        if product.stock < quantity:
            return (
                jsonify(
                    {
                        "error": (
                            f'Insufficient stock for "{product.title}". '
                            f"Available: {product.stock}."
                        ),
                        "product": {
                            "id": product.id,
                            "title": product.title,
                            "available": product.stock,
                        },
                    }
                ),
                409,
            )

    order_items = []
    subtotal = Decimal("0.00")
    for product_id, quantity in quantities.items():
        product = products[product_id]
        unit_price = Decimal(str(product.price))
        line_total = _quantize(unit_price * quantity)
        subtotal += line_total
        order_items.append(
            {
                "product": product,
                "quantity": quantity,
                "unit_price": unit_price,
                "line_total": line_total,
            }
        )

    subtotal = _quantize(subtotal)
    tax = _quantize(subtotal * TAX_RATE)
    total = _quantize(subtotal + tax)

    for attempt in range(ORDER_NUMBER_ATTEMPTS):
        order_number = _generate_order_number()
        if order_number is None:
            return jsonify({"error": "Could not allocate an order number"}), 500

        order = Order(
            order_number=order_number,
            subtotal=subtotal,
            tax=tax,
            total=total,
        )
        db.session.add(order)

        for line in order_items:
            product = line["product"]
            product.stock -= line["quantity"]
            db.session.add(
                OrderItem(
                    order=order,
                    product_id=product.id,
                    title=product.title,
                    unit_price=line["unit_price"],
                    quantity=line["quantity"],
                    line_total=line["line_total"],
                )
            )

        try:
            db.session.commit()
        except IntegrityError:
            # Lost the race for the order number: roll back and try again.
            db.session.rollback()
            continue

        return jsonify(order.to_dict()), 201

    db.session.rollback()
    return jsonify({"error": "Could not allocate an order number"}), 500


@main.get("/api/orders/<order_number>")
def get_order(order_number):
    """Return a previously created order."""
    order = db.session.scalar(
        db.select(Order).where(Order.order_number == order_number)
    )
    if order is None:
        return jsonify({"error": "Order not found"}), 404

    return jsonify(order.to_dict(include_created_at=True)), 200
