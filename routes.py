"""HTTP layer: storefront page and JSON API for the Lúmen store."""

import secrets
from decimal import ROUND_HALF_UP, Decimal

import re

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


def _find_product(text):
    """Find the product best matching the given free-text message.

    Tries, in order: an exact title substring, then a significant word
    from the title, then a significant word from the description.
    """
    products = db.session.scalars(db.select(Product)).all()
    low = text.lower()
    for product in products:
        if product.title.lower() in low:
            return product
    for product in products:
        for word in product.title.lower().split():
            if len(word) >= 4 and word in low:
                return product
    for product in products:
        for word in product.description.lower().split():
            if len(word) >= 5 and word in low:
                return product
    return None


def _match_any(text, keywords):
    """Return True if any keyword appears in text as a whole word/phrase.

    Uses word boundaries so short keywords such as "hi" or "hay" do not
    match inside unrelated words (e.g. "mochila" contains "hi").
    """
    for keyword in keywords:
        if re.search(r"\b" + re.escape(keyword) + r"\b", text):
            return True
    return False


@main.post("/api/chat")
def chat():
    """Rule-based assistant for the Lúmen storefront.

    Works entirely on the server (no external service), so it keeps
    working on localhost without internet access.
    """
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    if not message:
        return jsonify({
            "reply": "Escribí algo y te ayudo.",
            "suggestions": ["Ver catálogo", "Buscar un artículo", "Ayuda"],
        }), 200

    low = message.lower()

    greeting_keywords = ("hola", "buenos", "buenas", "hey", "hi", "qué tal", "que tal")
    if any(re.search(r"\b" + re.escape(word) + r"\b", low) for word in greeting_keywords):
        return jsonify({
            "reply": "¡Hola! Soy el asistente de Lúmen. Puedo ayudarte a buscar productos, consultar stock y precios, y guiarte en tu compra. ¿En qué te ayudo?",
            "suggestions": ["Ver catálogo", "Buscar un artículo", "Consultar stock"],
        }), 200

    if _match_any(low, ("ayuda", "qué podés", "que podes", "opciones", "qué hacés", "que haces", "qué sabés", "que sabes")):
        return jsonify({
            "reply": "Puedo ayudarte con:\n• Buscar productos por nombre\n• Consultar stock y precios\n• Listar categorías\n• Guiarte en el checkout\n\nProbá escribir \"busco cuaderno\" o \"precio de la mochila\".",
            "suggestions": ["Ver catálogo", "Buscar un artículo", "Consultar stock"],
        }), 200

    if _match_any(low, ("quién sos", "quien sos", "qué sos", "que sos", "tu nombre", "quién eres")):
        return jsonify({
            "reply": "Soy el asistente virtual de Lúmen, la librería y papelería técnica. Estoy acá para ayudarte a encontrar lo que necesitás.",
            "suggestions": ["Ver catálogo", "Buscar un artículo"],
        }), 200

    if _match_any(low, ("categoría", "categoria", "categorías", "categorias", "qué venden", "que venden", "qué tienen", "que tienen", "secciones")):
        categories = db.session.execute(
            db.select(Product.category, Product.category_label).distinct()
        ).all()
        lines = [f"• {label}" for _, label in categories]
        return jsonify({
            "reply": "Tenemos estas categorías:\n" + "\n".join(lines) + "\n\n¿Querés ver productos de alguna?",
            "suggestions": [label for _, label in categories],
        }), 200

    if _match_any(low, ("catálogo", "catalogo", "productos", "listar", "mostrar todo", "ver todo", "qué hay", "que hay")):
        products = db.session.scalars(db.select(Product).order_by(Product.id)).all()
        lines = [f"• {product.title} — ${float(product.price):.2f} ({product.stock} en stock)" for product in products]
        return jsonify({
            "reply": "Nuestro catálogo:\n" + "\n".join(lines),
            "suggestions": ["Buscar un artículo", "Consultar stock"],
        }), 200

    if _match_any(low, ("stock", "disponibilidad", "disponible", "hay stock", "quedan", "agotado")):
        product = _find_product(low)
        if product is not None:
            if product.stock > 0:
                reply = f"\"{product.title}\" tiene {product.stock} unidades disponibles."
            else:
                reply = f"\"{product.title}\" está agotado por el momento."
            return jsonify({"reply": reply, "suggestions": ["Ver precio", "Buscar otro"]}), 200
        products = db.session.scalars(db.select(Product).order_by(Product.id)).all()
        lines = [f"• {product.title}: {product.stock} en stock" for product in products]
        return jsonify({
            "reply": "Stock actual:\n" + "\n".join(lines),
            "suggestions": ["Buscar un artículo"],
        }), 200

    if _match_any(low, ("precio", "cuánto", "cuanto", "cuesta", "vale", "costo", "cuánto sale")):
        product = _find_product(low)
        if product is not None:
            return jsonify({
                "reply": f"\"{product.title}\" cuesta ${float(product.price):.2f}.",
                "suggestions": ["Consultar stock", "Agregar al carrito"],
            }), 200
        products = db.session.scalars(db.select(Product).order_by(Product.id)).all()
        lines = [f"• {product.title}: ${float(product.price):.2f}" for product in products]
        return jsonify({
            "reply": "Precios:\n" + "\n".join(lines),
            "suggestions": ["Buscar un artículo"],
        }), 200

    if _match_any(low, ("busco", "buscar", "tienen", "hay", "necesito", "quiero", "dame")):
        product = _find_product(low)
        if product is not None:
            return jsonify({
                "reply": f"Encontré: \"{product.title}\" — ${float(product.price):.2f}, {product.stock} en stock.\n{product.description}",
                "suggestions": ["Consultar stock", "Ver precio"],
            }), 200
        results = db.session.scalars(
            db.select(Product).where(
                Product.title.ilike(f"%{message}%") | Product.description.ilike(f"%{message}%")
            )
        ).all()
        if results:
            lines = [f"• {product.title} — ${float(product.price):.2f}" for product in results]
            return jsonify({
                "reply": "Encontré estos artículos:\n" + "\n".join(lines),
                "suggestions": ["Ver detalles"],
            }), 200
        return jsonify({
            "reply": f"No encontré artículos relacionados con \"{message}\". Probá con otra palabra o mirá el catálogo completo.",
            "suggestions": ["Ver catálogo", "Ayuda"],
        }), 200

    if _match_any(low, ("comprar", "checkout", "finalizar", "pagar", "compra", "pedido")):
        return jsonify({
            "reply": "Para finalizar tu compra, agregá los productos al carrito con \"Agregar\" y hacé clic en \"Finalizar Compra\" en el carrito lateral. Se genera un número de pedido y se descuenta el stock automáticamente.",
            "suggestions": ["Ver catálogo", "Buscar un artículo"],
        }), 200

    if _match_any(low, ("carrito", "mi carrito", "total")):
        return jsonify({
            "reply": "Tu carrito está en el panel lateral (ícono del carrito, arriba a la derecha). Ahí podés ver los productos, ajustar cantidades y finalizar la compra. El subtotal incluye IVA del 21%.",
            "suggestions": ["Ver catálogo", "Finalizar compra"],
        }), 200

    return jsonify({
        "reply": "No entendí bien. Podés preguntarme por productos, stock, precios o categorías. Escribí \"ayuda\" para ver las opciones.",
        "suggestions": ["Ver catálogo", "Ayuda", "Buscar un artículo"],
    }), 200
