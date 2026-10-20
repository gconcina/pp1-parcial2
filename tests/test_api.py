"""API tests for the Lúmen store backend.

The suite exercises the JSON contract served by ``routes.py`` against a real
SQLite database (in-memory, shared connection) seeded with the original
catalog.
"""

import re
import sys
from pathlib import Path

import pytest
from sqlalchemy.pool import StaticPool

# Make the project root importable when pytest is invoked from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ORDER_NUMBER_RE = re.compile(r"^LUM-\d{5}$")


@pytest.fixture()
def app():
    """Application bound to an in-memory SQLite database seeded with the catalog."""
    from app import create_app
    from models import db
    from seed import seed_database

    application = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "SQLALCHEMY_ENGINE_OPTIONS": {"poolclass": StaticPool},
        }
    )

    with application.app_context():
        db.create_all()
        seed_database()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    """Flask test client bound to the seeded application."""
    return app.test_client()


def _product_stock(app, product_id):
    """Read the persisted stock of a product from the database."""
    from models import db, Product

    with app.app_context():
        product = db.session.get(Product, product_id)
        assert product is not None
        return product.stock


def _order_count(app):
    """Count persisted orders."""
    from models import db, Order

    with app.app_context():
        return db.session.scalar(db.select(db.func.count(Order.id)))


# --------------------------------------------------------------------------
# GET /api/products
# --------------------------------------------------------------------------

def test_list_products_returns_full_catalog(client):
    response = client.get("/api/products")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 8
    assert len(payload["products"]) == 8

    first = payload["products"][0]
    assert first["title"] == "Cuaderno Profesional Punteado A5"
    assert first["price"] == 18.5
    assert first["category"] == "cuadernos"
    assert first["category_label"] == "Cuadernos y Agendas"
    assert first["stock"] == 45
    assert first["image"].startswith("https://")


def test_list_products_search_filters_by_title_and_description(client):
    response = client.get("/api/products", query_string={"q": "escuadra"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 1
    assert payload["products"][0]["title"] == "Escuadra de Metacrilato Transparente 30cm"


def test_list_products_search_is_case_insensitive(client):
    response = client.get("/api/products", query_string={"q": "MOCHILA"})

    payload = response.get_json()
    assert payload["count"] == 1
    assert payload["products"][0]["category"] == "mochilas"


def test_list_products_filters_by_category(client):
    response = client.get("/api/products", query_string={"category": "arte"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 2
    assert {product["category"] for product in payload["products"]} == {"arte"}
    assert {product["category_label"] for product in payload["products"]} == {
        "Arte y Dibujo Técnico"
    }


def test_list_products_filters_by_inclusive_price_range(client):
    response = client.get(
        "/api/products", query_string={"min_price": 20, "max_price": 40}
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 2
    for product in payload["products"]:
        assert 20 <= product["price"] <= 40
    assert [product["title"] for product in payload["products"]] == [
        "Set de Estilógrafos de Calibrado Técnico x4",
        "Agenda Planificadora Semanal Minimalista",
    ]


def test_list_products_ignores_invalid_price_bounds(client):
    response = client.get(
        "/api/products", query_string={"min_price": "abc", "max_price": ""}
    )

    assert response.status_code == 200
    assert response.get_json()["count"] == 8


def test_list_products_with_category_all_returns_everything(client):
    response = client.get("/api/products", query_string={"category": "all"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 8
    assert len(payload["products"]) == 8


# --------------------------------------------------------------------------
# GET /api/categories
# --------------------------------------------------------------------------

def test_list_categories_returns_slugs_and_labels(client):
    response = client.get("/api/categories")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["categories"] == [
        {"value": "arte", "label": "Arte y Dibujo Técnico"},
        {"value": "cuadernos", "label": "Cuadernos y Agendas"},
        {"value": "escritorio", "label": "Escritorio y Bolígrafos"},
        {"value": "mochilas", "label": "Mochilas y Organizadores"},
    ]


# --------------------------------------------------------------------------
# POST /api/checkout
# --------------------------------------------------------------------------

def test_checkout_creates_order_and_deducts_stock(client, app):
    response = client.post(
        "/api/checkout",
        json={"items": [{"product_id": 1, "quantity": 2}]},
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert ORDER_NUMBER_RE.match(payload["order_number"])
    assert payload["subtotal"] == 37.0
    assert payload["tax"] == 7.77
    assert payload["total"] == 44.77
    assert payload["items"] == [
        {
            "product_id": 1,
            "title": "Cuaderno Profesional Punteado A5",
            "quantity": 2,
            "unit_price": 18.5,
            "line_total": 37.0,
        }
    ]

    assert _product_stock(app, 1) == 43
    assert _order_count(app) == 1


def test_checkout_tax_is_twenty_one_percent_of_subtotal(client):
    response = client.post(
        "/api/checkout",
        json={"items": [{"product_id": 2, "quantity": 3}]},
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["subtotal"] == 104.7
    assert payload["tax"] == round(payload["subtotal"] * 0.21, 2)
    assert payload["total"] == round(payload["subtotal"] + payload["tax"], 2)


def test_checkout_with_insufficient_stock_returns_conflict(client, app):
    response = client.post(
        "/api/checkout",
        json={"items": [{"product_id": 5, "quantity": 99}]},
    )

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["error"]
    assert payload["product"]["id"] == 5
    assert payload["product"]["available"] == 15
    assert payload["product"]["title"] == "Mochila Urbana Porta-Planos y Laptop"

    assert _order_count(app) == 0
    assert _product_stock(app, 5) == 15


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({}, id="missing-items"),
        pytest.param({"items": []}, id="empty-items"),
        pytest.param({"items": "not-a-list"}, id="items-not-a-list"),
        pytest.param({"items": [{"product_id": 1, "quantity": 0}]}, id="zero-quantity"),
        pytest.param({"items": [{"product_id": 1, "quantity": -3}]}, id="negative-quantity"),
        pytest.param({"items": [{"product_id": 1, "quantity": "two"}]}, id="non-integer-quantity"),
        pytest.param({"items": [{"product_id": 1}]}, id="missing-quantity"),
        pytest.param({"items": [{"quantity": 1}]}, id="missing-product-id"),
        pytest.param({"items": [{"product_id": 9999, "quantity": 1}]}, id="unknown-product"),
    ],
)
def test_checkout_with_invalid_payload_returns_bad_request(client, app, body):
    response = client.post("/api/checkout", json=body)

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"]
    assert _order_count(app) == 0


def test_checkout_with_non_json_body_returns_bad_request(client):
    response = client.post(
        "/api/checkout", data="not json at all", content_type="application/json"
    )

    assert response.status_code == 400
    assert response.get_json()["error"]


# --------------------------------------------------------------------------
# GET /api/orders/<order_number>
# --------------------------------------------------------------------------

def test_order_lookup_returns_created_order(client):
    created = client.post(
        "/api/checkout",
        json={"items": [{"product_id": 1, "quantity": 2}]},
    ).get_json()

    response = client.get(f"/api/orders/{created['order_number']}")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["order_number"] == created["order_number"]
    assert payload["subtotal"] == created["subtotal"]
    assert payload["tax"] == created["tax"]
    assert payload["total"] == created["total"]
    assert payload["items"] == created["items"]
    assert payload["created_at"]


def test_order_lookup_with_unknown_order_returns_not_found(client):
    response = client.get("/api/orders/LUM-00000")

    assert response.status_code == 404
    assert response.get_json()["error"] == "Order not found"


# --------------------------------------------------------------------------
# GET /
# --------------------------------------------------------------------------

def test_index_renders_the_storefront(client):
    response = client.get("/")

    assert response.status_code == 200
