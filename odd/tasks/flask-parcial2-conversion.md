# Feature: Conversión a Flask + SQLite (parcial2)

## Objective

Convertir la aplicación estática de catálogo "Lúmen" (un solo `tpn3.html` + `css/tpn3.css`) en una
aplicación Flask con persistencia SQLite vía SQLAlchemy, conservando íntegramente la UI y el
comportamiento de catálogo, filtros, carrito y checkout. Todos los archivos del proyecto se renombran
de `tpn3` a `parcial2`.

## Problem

El proyecto es una página estática: el catálogo vive en un array JS dentro del HTML, el stock se
"persiste" en `localStorage` (y se borra en cada carga, línea 275 del HTML original), y el checkout es
puramente cosmético — no hay backend, ni datos compartidos, ni estado real de pedidos.

## Why

- El parcial pide una aplicación web con servidor: la lógica de negocio (stock, validación de pedidos,
  totales) debe estar en el servidor y ser verificable con tests.
- SQLite + SQLAlchemy da persistencia real sin infraestructura externa, apta para una entrega académica.
- El renombrado `tpn3` → `parcial2` alinea los archivos con la nomenclatura del parcial.

## Scope

**Incluido**
- Estructura Flask estándar: `app.py`, `templates/`, `static/`, `instance/`.
- Modelos SQLAlchemy: `Product`, `Order`, `OrderItem`.
- Seed del catálogo original (8 productos, 4 categorías) en la base.
- API JSON: listado de productos con filtros server-side, categorías, checkout de pedidos.
- Template Jinja que replica la UI original + JS que consume la API.
- Suite de tests pytest sobre la API.
- README con instrucciones de ejecución.

**Fuera de alcance (no autorizado)**
- Autenticación de usuarios, pasarela de pago, mailing, despliegue.
- Modelado de review, multi-tenant, i18n.
- Cambios visuales al diseño original (se preserva pixel a pixel el CSS).

## Constraints

- Comportamiento observable idéntico al original: mismos productos, precios, categorías, textos,
  íconos y estructura visual.
- El stock pasa a ser autoridad del servidor; el `localStorage` queda solo para el carrito en el navegador.
- Taxa IVA 21% (constante del dominio, no configurable por request).
- Sin dependencias de red en runtime: las imágenes siguen siendo URLs remotas del original.
- Idioma de los artefactos: inglés en código/comentarios, español en los textos de UI ya existentes.

## Authorized edit surface

```
app.py
models.py
routes.py
seed.py
requirements.txt
README.md
.gitignore
templates/base.html
templates/parcial2.html
static/css/parcial2.css
static/js/parcial2.js
tests/test_api.py
tpn3.html            (eliminado)
css/tpn3.css        (eliminado)
```

## Delivery strategy

`single-branch` — el trabajo se developing y se entrega **directamente sobre `main`**, con commits
por work unit. El repositorio es público y no usa pull requests: el remoto es
`https://github.com/gconcina/pp1-parcial2.git` y `main` es la rama por defecto.

Decisión del usuario (2026-10-22): descartar el flujo de rama feature + PR y trabajar sobre `main`.
Los commits por work unit se conservan igual, así que el historial sigue siendo revisable commit a
commit; lo que cambia es que no hay una etapa de revisión previa al merge.

El remoto sí estaba configurado al momento de subir; la entrega local de esta feature se сдела
primero sobre `feature/flask-parcial2` y se fast-forwardeó a `main` al publicar.

Forecast de líneas authored: ~1150 (movimiento mecánico de HTML/CSS + backend, JS, tests y docs).
Presupuesto por work unit: se mantém la heurística de ~400 líneas por task como guía de planificación
únicamente; el movimiento de archivos existente no se cuenta como lógica nueva.

## Tasks

### T1 — Scaffold Flask + modelos + seed
- [x] `requirements.txt` con Flask, Flask-SQLAlchemy, SQLAlchemy, pytest
- [x] `models.py`: `Product`, `Order`, `OrderItem` + `to_dict()`
- [x] `app.py`: factory `create_app()`, config, `instance/` + SQLite en `instance/parcial2.db`,
      PRAGMA `foreign_keys=ON`, CLI `flask init-db` y `flask seed`
- [x] `seed.py`: los 8 productos originales con sus URLs de imagen
- [x] `.gitignore` (`.venv/`, `instance/`, `__pycache__/`)

### T2 — API JSON + tests
- [x] `GET /api/products` con filtros `q`, `category`, `min_price`, `max_price` (server-side)
- [x] `GET /api/categories`
- [x] `POST /api/checkout` con validación de stock, creación de pedido y descuento de stock
- [x] `GET /api/orders/<order_number>`
- [x] `tests/test_api.py`: RED antes de implementar, luego GREEN

### T3 — Frontend Jinja + JS contra la API
- [x] `templates/base.html` + `templates/parcial2.html` (UI original replicada, categorías vía Jinja)
- [x] `static/css/parcial2.css` (contenido original intacto)
- [x] `static/js/parcial2.js`: render desde `/api/products`, filtros por fetch, carrito, checkout
- [x] Carrito persistido en `localStorage` bajo clave `parcial2_cart`

### T4 — Documentación y verificación final
- [x] `README.md` con estructura, instalación, ejecución y contrato de la API
- [x] Suite completa en verde + arranque real del servidor verificado

## Acceptance criteria

1. `python -m pytest` pasa completo.
2. `flask --app app init-db && flask --app app seed && flask --app app run` sirve la tienda en `/`.
3. El catálogo muestra los 8 productos originales con sus precios e imágenes.
4. Búsqueda, filtro por categoría y rango de precio filtran server-side vía la API.
5. Agregar al carrito descuenta stock disponible según el servidor; el botón se bloquea al agotarse.
6. "Finalizar Compra" crea un pedido persistido, descuenta stock y muestra el número de pedido.
7. Un checkout con stock insuficiente devuelve 409 y no crea pedido ni descuenta stock.
8. Ningún archivo conserva el prefijo `tpn3`.

## Checks

- `python -m pytest -q` (suite completa)
- `flask --app app init-db && flask --app app seed` (creación de DB)
- `curl` contra `/api/products` y `/api/checkout` sobre un servidor real en vivo
- Verificación estructural: `grep -rn "tpn3" .` sin resultados

## Route declaration

| Task | Route | Trigger |
| --- | --- | --- |
| T1 | delegated | 6+ archivos no triviales (`app.py`, `models.py`, `routes.py`, `seed.py`, `requirements.txt`, `.gitignore`) |
| T2 | delegated | mismo writer que T1: `routes.py` + `tests/test_api.py` (2+ archivos no triviales) |
| T3 | delegated | 3 archivos no triviales (`templates/`, `static/js/`) |
| T4 | inline | README + verificación (bash de estado, sin diseño pendiente) |

## Progress

- [x] Decisión de arquitectura tomada: Flask + SQLite (SQLAlchemy), confirmada por el usuario.
- [x] T1 — scaffold, modelos y seed.
- [x] T2 — API JSON + suite de tests (RED observado antes de implementar).
- [x] T3 — templates Jinja + cliente JS contra la API.
- [x] T4 — README + verificación final.

## Verification evidence

- `python -m pytest -q` → `24 passed in 0.54s` (suite completa, base de datos SQLite en memoria).
- RED observado antes de implementar la API: `24 errors in 0.29s` — `ModuleNotFoundError: No module named 'app'`.
- GREEN observado tras implementar: `23 passed, 1 failed` (el fallo restante era
  `TemplateNotFound: parcial2.html`, bloqueado hasta T3) → `24 passed` tras crear el template.
- CLI: `flask --app app init-db` → `Database initialized: sqlite:////.../instance/parcial2.db`;
  `flask --app app seed` → `Seeding complete: 8 inserted, 0 skipped.` (repetido → `0 inserted, 8 skipped`).
- Servidor real en `:5099`: `GET /` → 200; `GET /static/js/parcial2.js` → 200;
  `GET /static/css/parcial2.css` → 200; `GET /api/products` → 200 con 8 productos.
- Verificación E2E del backend: `GET /api/products?q=escuadra` → 1 producto;
  `?category=arte&min_price=10&max_price=40` → solo "Set de Estilógrafos de Calibrado Técnico x4".
- `POST /api/checkout` con `{p1 x2, p4 x1}` → `201`, `subtotal 46.25 / tax 9.71 / total 55.96`,
  orden `LUM-50915`; stock de p1 45→43 y de p4 30→29 (descuento server-side confirmado).
- `POST /api/checkout` con `{p5 x99}` → `409` con `{"error": "...", "product": {"available": 15}}`,
  sin creación de pedido ni descuento de stock.
- `node --check static/js/parcial2.js` → OK.
- Verificación estructural: `grep -rn "tpn3" .` (excluyendo `.git`, `.venv` y la documentación) →
  sin resultados en código, templates y assets. Las únicas menciones restantes son históricas, en
  este documento y en el README, que describen el origen estático (`tpn3.html`, `tpn3_stock`).

## Commits

Todos sobre `main` (fast-forward desde `feature/flask-parcial2`, que se eliminó al decidir trabajar
directo sobre la rama principal).

| Commit | Work unit |
|--------|-----------|
| `3423f53` | `feat(api)`: factory de Flask, modelos SQLAlchemy, seed y API JSON |
| `d018400` | `feat(storefront)`: templates Jinja + cliente JS; se elimina la página estática `tpn3.html` |
| `742ee16` | `test(api)`: suite de 24 tests sobre la API |
| `3dbe761` | `docs`: README y documento de feature |
| `425cc02` | `chore`: se ignora el cache generado del skill-registry |

## Next step

Publicado en `https://github.com/gconcina/pp1-parcial2` (rama `main`, repo público). El flujo de
trabajo es commit directo sobre `main`.
