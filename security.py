"""Seguridad de la aplicación Lúmen.

Acá se juntan todas las protecciones pedidas para el parcial:

- Sesiones seguras: la cookie de sesión no se puede leer desde JavaScript
  (HttpOnly) y no se manda desde otros sitios (SameSite).
- CSRF: Flask-WTF exige un token en cada POST.
- XSS: cabecera Content-Security-Policy que solo deja cargar scripts
  propios y de los CDN que usa la página.
- Fuerza bruta: Flask-Limiter limita cuántas peticiones puede hacer una IP.
- Secuestro de clic (clickjacking): cabecera X-Frame-Options para que la
  página no se pueda meter dentro de un <iframe> de otro sitio.
"""

from flask import jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFError, CSRFProtect

csrf = CSRFProtect()

#: Límite general por IP; las rutas sensibles tienen uno más estricto.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per hour"],
    storage_uri="memory://",
)

#: Solo se permite cargar recursos propios y de los CDN de Bootstrap y
#: FontAwesome. Las imágenes de productos vienen de varios sitios https.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
    "font-src 'self' https://cdnjs.cloudflare.com; "
    "img-src 'self' https: data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "base-uri 'self'"
)


def init_security(app):
    """Activa todas las protecciones sobre la aplicación."""

    # Sesiones de usuario seguras.
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
    # En producción (con HTTPS) hay que poner SESSION_COOKIE_SECURE=True.
    # En localhost se usa http, así que lo dejamos en False.
    app.config.setdefault("SESSION_COOKIE_SECURE", False)

    csrf.init_app(app)
    limiter.init_app(app)

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        return jsonify({"error": "Token CSRF inválido o faltante"}), 400

    @app.errorhandler(429)
    def too_many_requests(error):
        return jsonify(
            {"error": "Demasiadas peticiones. Esperá un momento e intentá de nuevo."}
        ), 429

    @app.after_request
    def add_security_headers(response):
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
