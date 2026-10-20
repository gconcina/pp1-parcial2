# Lúmen — Flask store with a SQLite catalog

A single-page catalog store for a technical stationery shop, rebuilt from a static HTML file into a
Flask application. The catalog, the stock and the orders now live in a SQLite database, the browser
talks to a JSON API, and the storefront is a Jinja template with a vanilla-JS client.

## Quick path

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

flask --app app init-db     # create instance/parcial2.db
flask --app app seed        # load the 8-product catalog
flask --app app run         # http://127.0.0.1:5000
```

Run the tests with `python -m pytest -q` (24 tests, no server required).

## Details

| Topic | Decision |
|-------|----------|
| Stack | Flask 3.1 + Flask-SQLAlchemy 3.1 + SQLite. No build step, no bundler, no npm. |
| Data | `instance/parcial2.db`, created by `flask init-db`. Delete it to start from scratch. |
| Catalog | Seeded by `flask seed` from `seed.py`; the command is idempotent. |
| Filtering | Server-side. The client sends `q`, `category`, `min_price`, `max_price` to `/api/products`. |
| Stock | Authoritative on the server. The cart lives in the browser (`localStorage["parcial2_cart"]`). |
| Checkout | `POST /api/checkout` validates stock, creates the order and deducts the stock in one transaction. |
| Money | `Numeric(10,2)` in the database, JSON numbers in the API, IVA fixed at 21%. |
| Order numbers | `LUM-` + 5 digits, unique per order. |

## Project structure

```
app.py                    application factory, config, CLI commands
models.py                 SQLAlchemy models: Product, Order, OrderItem
routes.py                 storefront page + JSON API blueprint
seed.py                   the original 8-product catalog
templates/base.html       page skeleton shared by the storefront
templates/parcial2.html   the storefront markup
static/css/parcial2.css   stylesheet (moved unchanged from the static page)
static/js/parcial2.js     catalog, filters, cart and checkout client
tests/test_api.py         API test suite
odd/tasks/                the feature document for this conversion
```

## API

| Method | Route | Purpose |
|--------|-------|---------|
| `GET` | `/` | The storefront page. |
| `GET` | `/api/products` | Catalog, optionally filtered by `q`, `category`, `min_price`, `max_price`. |
| `GET` | `/api/categories` | Distinct categories as `{value, label}` pairs. |
| `POST` | `/api/checkout` | Creates an order from `{"items": [{"product_id": 1, "quantity": 2}]}`. |
| `GET` | `/api/orders/<order_number>` | A single order, including `created_at`. |

```bash
curl "http://127.0.0.1:5000/api/products?category=arte&max_price=40"
curl -X POST http://127.0.0.1:5000/api/checkout \
  -H 'Content-Type: application/json' \
  -d '{"items":[{"product_id":1,"quantity":2}]}'
```

Status codes: `201` order created, `409` not enough stock (no order, no stock deducted), `400`
malformed payload, `404` unknown order.

## Checklist

- [ ] `flask --app app init-db && flask --app app seed` prints the seeded catalog.
- [ ] `http://127.0.0.1:5000/` renders the store with the 8 original products.
- [ ] Search, category and price filters narrow the grid.
- [ ] Adding to the cart updates the totals, the IVA and the badge counters.
- [ ] "Finalizar Compra" creates the order and shows the real order number.
- [ ] `python -m pytest -q` passes 24 tests.

## What changed from the static page

- The product list, the filters and the stock moved to the server; the client only renders what the API returns.
- The `tpn3_stock` localStorage hack is gone — stock is a database column now.
- The checkout modal has a confirm state: the order is created when the user confirms, and "Cancelar"
  closes the modal without creating anything.
- The product cards are built with `textContent` instead of string interpolation into `innerHTML`.
- The `refreshAll()` filter-reset bug of the original page is not reproduced: the active filter survives
  a cart change.

## Next step

Push the branch and open a pull request when you want the review trail:

```bash
git push -u origin feature/flask-parcial2
```
