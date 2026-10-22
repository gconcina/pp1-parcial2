# Lúmen — Tienda Flask con catálogo en SQLite

Tienda de papelería técnica en una sola página, reconstruida a partir de un archivo HTML estático
en una aplicación Flask. El catálogo, el stock y los pedidos residen ahora en una base de datos
SQLite, el navegador se comunica con una API JSON y la interfaz es una plantilla Jinja con un
cliente en JavaScript puro.

## Inicio rápido

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

flask --app app init-db     # crea instance/parcial2.db
flask --app app seed        # carga el catálogo de 8 productos
flask --app app run         # http://127.0.0.1:5000
```

Las pruebas se ejecutan con `python -m pytest -q` (24 tests, sin necesidad de levantar el servidor).

## Detalles

| Tema | Decisión |
|------|----------|
| Stack | Flask 3.1 + Flask-SQLAlchemy 3.1 + SQLite. Sin build step, sin bundler, sin npm. |
| Datos | `instance/parcial2.db`, creado con `flask init-db`. Se elimina para empezar de cero. |
| Catálogo | Cargado con `flask seed` desde `seed.py`; el comando es idempotente. |
| Filtrado | En el servidor. El cliente envía `q`, `category`, `min_price`, `max_price` a `/api/products`. |
| Stock | Con autoridad en el servidor. El carrito vive en el navegador (`localStorage["parcial2_cart"]`). |
| Checkout | `POST /api/checkout` valida el stock, crea el pedido y descuenta las unidades en una transacción. |
| Dinero | `Numeric(10,2)` en la base de datos, números JSON en la API, IVA fijo del 21%. |
| Números de pedido | `LUM-` + 5 dígitos, únicos por pedido. |

## Estructura del proyecto

```
app.py                    factory de la aplicación, configuración y comandos CLI
models.py                 modelos SQLAlchemy: Product, Order, OrderItem
routes.py                 página del storefront + blueprint de la API JSON
seed.py                   el catálogo original de 8 productos
templates/base.html       esqueleto de página compartido por el storefront
templates/parcial2.html   markup del storefront
static/css/parcial2.css   hoja de estilos (movida sin cambios desde la página estática)
static/js/parcial2.js     cliente de catálogo, filtros, carrito y checkout
tests/test_api.py         suite de tests de la API
odd/tasks/                documento de feature de esta conversión
```

## API

| Método | Ruta | Propósito |
|--------|------|-----------|
| `GET` | `/` | La página del storefront. |
| `GET` | `/api/products` | Catálogo, opcionalmente filtrado por `q`, `category`, `min_price`, `max_price`. |
| `GET` | `/api/categories` | Categorías distintas como pares `{value, label}`. |
| `POST` | `/api/checkout` | Crea un pedido a partir de `{"items": [{"product_id": 1, "quantity": 2}]}`. |
| `GET` | `/api/orders/<order_number>` | Un pedido puntual, incluido `created_at`. |

```bash
curl "http://127.0.0.1:5000/api/products?category=arte&max_price=40"
curl -X POST http://127.0.0.1:5000/api/checkout \
  -H 'Content-Type: application/json' \
  -d '{"items":[{"product_id":1,"quantity":2}]}'
```

Códigos de estado: `201` pedido creado, `409` sin stock suficiente (no se crea el pedido ni se
descuenta stock), `400` payload mal formado, `404` pedido inexistente.
