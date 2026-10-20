"""SQLAlchemy models for the Lúmen store.

``db`` is the shared Flask-SQLAlchemy instance used by the application
factory, the API blueprint and the seed command.
"""

from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

db = SQLAlchemy()


def money(value):
    """Return a JSON-safe float rounded to two decimals."""
    if value is None:
        return 0.0
    return round(float(value), 2)


class Product(db.Model):
    """A catalog item."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(db.String(32), unique=True, index=True)
    title: Mapped[str] = mapped_column(db.String(120))
    category: Mapped[str] = mapped_column(db.String(32), index=True)
    category_label: Mapped[str] = mapped_column(db.String(64))
    price: Mapped[float] = mapped_column(Numeric(10, 2))
    stock: Mapped[int] = mapped_column(default=0)
    description: Mapped[str] = mapped_column(db.Text)
    image: Mapped[str] = mapped_column(db.String(500))

    def to_dict(self):
        """JSON-safe representation of the product."""
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "category_label": self.category_label,
            "price": money(self.price),
            "stock": self.stock,
            "description": self.description,
            "image": self.image,
        }


class Order(db.Model):
    """A customer order created by a successful checkout."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(db.String(16), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )
    subtotal: Mapped[float] = mapped_column(Numeric(10, 2))
    tax: Mapped[float] = mapped_column(Numeric(10, 2))
    total: Mapped[float] = mapped_column(Numeric(10, 2))

    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderItem.id",
        lazy="selectin",
    )

    def to_dict(self, include_created_at=False):
        """JSON-safe representation of the order."""
        payload = {
            "order_number": self.order_number,
            "subtotal": money(self.subtotal),
            "tax": money(self.tax),
            "total": money(self.total),
            "items": [item.to_dict() for item in self.items],
        }
        if include_created_at:
            payload["created_at"] = (
                self.created_at.isoformat() if self.created_at else None
            )
        return payload


class OrderItem(db.Model):
    """A purchased line, snapshotting title and unit price at purchase time."""

    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        db.ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[int] = mapped_column(
        db.ForeignKey("products.id"), index=True
    )
    title: Mapped[str] = mapped_column(db.String(120))
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2))
    quantity: Mapped[int]
    line_total: Mapped[float] = mapped_column(Numeric(10, 2))

    order: Mapped[Order] = relationship("Order", back_populates="items")

    def to_dict(self):
        """JSON-safe representation of the order line."""
        return {
            "product_id": self.product_id,
            "title": self.title,
            "quantity": self.quantity,
            "unit_price": money(self.unit_price),
            "line_total": money(self.line_total),
        }
