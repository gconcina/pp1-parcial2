"""Seed data for the Lúmen catalog.

The eight products below are the original catalog of the static page, kept
verbatim (copy and remote image URLs) so the converted app shows the same
storefront.
"""

from decimal import Decimal

from models import Product, db

PRODUCTS = [
    {
        "sku": "p1",
        "title": "Cuaderno Profesional Punteado A5",
        "category": "cuadernos",
        "category_label": "Cuadernos y Agendas",
        "price": Decimal("18.50"),
        "stock": 45,
        "description": (
            "Tapa dura con 192 páginas de 120g libre de ácido, ideal para "
            "Bullet Journal."
        ),
        "image": (
            "https://acdn-us.mitiendanube.com/stores/004/014/914/products/"
            "17-9514fb73c18c82d92c17447453882201-1024-1024.webp"
        ),
    },
    {
        "sku": "p2",
        "title": "Set de Estilógrafos de Calibrado Técnico x4",
        "category": "arte",
        "category_label": "Arte y Dibujo Técnico",
        "price": Decimal("34.90"),
        "stock": 20,
        "description": (
            "Puntas de precisión 0.2, 0.4, 0.6 y 0.8mm con tinta pigmentada "
            "resistente al agua."
        ),
        "image": "https://libreriamayoristaleo.com.ar/wp-content/uploads/2025/01/507.jpg",
    },
    {
        "sku": "p3",
        "title": "Bolígrafo Ejecutivo Metálico Retráctil",
        "category": "escritorio",
        "category_label": "Escritorio y Bolígrafos",
        "price": Decimal("15.00"),
        "stock": 50,
        "description": (
            "Cuerpo de aluminio anodizado con fluidez de tinta gel de secado "
            "rápido."
        ),
        "image": (
            "https://ddkjx5kezodfx.cloudfront.net/Weyop/Libreria%20San%20Pablo/"
            "Store/Productos/Escritura/"
            "1742992444_RklMR08tQm9saWdyYWZvLVJldHJhY3RpbC1OZXJvLVRpbnRhLU5l"
            "Z3JhLUFydC1OUjEwLUMzNi0wMDEtQ29kLTkzNDgw.webp"
        ),
    },
    {
        "sku": "p4",
        "title": "Escuadra de Metacrilato Transparente 30cm",
        "category": "arte",
        "category_label": "Arte y Dibujo Técnico",
        "price": Decimal("9.25"),
        "stock": 30,
        "description": (
            "Escala biselada grabada a láser con alta precisión para estudiantes "
            "de arquitectura."
        ),
        "image": (
            "https://acdn-us.mitiendanube.com/stores/001/132/430/products/"
            "escuadra-pizzini-estudio-3732-30cm-60cm-"
            "4599f23d6c3a942a3017315215562572-1024-1024.webp"
        ),
    },
    {
        "sku": "p5",
        "title": "Mochila Urbana Porta-Planos y Laptop",
        "category": "mochilas",
        "category_label": "Mochilas y Organizadores",
        "price": Decimal("65.00"),
        "stock": 15,
        "description": (
            'Compartimento acolchado para laptop de 15.6" y soporte lateral para '
            "tubo portaplanos."
        ),
        "image": (
            "https://images.unsplash.com/photo-1553062407-98eeb64c6a62"
            "?w=500&auto=format&fit=crop&q=80"
        ),
    },
    {
        "sku": "p6",
        "title": "Portaminas de Precisión 0.5mm de Metal",
        "category": "escritorio",
        "category_label": "Escritorio y Bolígrafos",
        "price": Decimal("12.80"),
        "stock": 35,
        "description": (
            "Mecanismo de latón con agarre moleteado antideslizante para dibujo "
            "técnico."
        ),
        "image": "https://m.media-amazon.com/images/I/81RkDcTFZ7L._AC_UF894,1000_QL80_.jpg",
    },
    {
        "sku": "p7",
        "title": "Agenda Planificadora Semanal Minimalista",
        "category": "cuadernos",
        "category_label": "Cuadernos y Agendas",
        "price": Decimal("22.00"),
        "stock": 25,
        "description": (
            "Sin fechas fijas, encuadernación cosida plana y cinta marcadora."
        ),
        "image": (
            "https://images.unsplash.com/photo-1506784983877-45594efa4cbe"
            "?w=500&auto=format&fit=crop&q=80"
        ),
    },
    {
        "sku": "p8",
        "title": "Estuche Organizador Enrollable de Lona",
        "category": "mochilas",
        "category_label": "Mochilas y Organizadores",
        "price": Decimal("14.50"),
        "stock": 40,
        "description": (
            "Capacidad para 36 lápices o marcadores con protección de puntas "
            "plegable."
        ),
        "image": (
            "https://http2.mlstatic.com/D_NQ_NP_703448-MLA108375352226_032026-O.webp"
        ),
    },
]


def seed_database():
    """Insert the catalog when the products table is empty.

    Returns a ``(inserted, skipped)`` tuple. The operation is idempotent: it
    does nothing when products already exist.
    """
    existing = db.session.scalar(db.select(db.func.count(Product.id))) or 0
    if existing:
        return 0, existing

    for product in PRODUCTS:
        db.session.add(Product(**product))
    db.session.commit()

    return len(PRODUCTS), 0
