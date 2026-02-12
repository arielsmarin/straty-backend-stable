from sqlalchemy import (
    String,
    Integer,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)
from .database import Base


# ============================================================
# CLIENT
# ============================================================

class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)

    scenes: Mapped[list["Scene"]] = relationship(
        back_populates="client",
        cascade="all, delete-orphan",
    )


# ============================================================
# SCENE  (reflete exatamente o JSON)
# ============================================================

class Scene(Base):
    __tablename__ = "scenes"

    __table_args__ = (
        UniqueConstraint("client_id", "scene_id", name="uq_scene_per_client"),
        UniqueConstraint("client_id", "scene_index", name="uq_scene_index_per_client"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))

    # JSON fields
    scene_id: Mapped[str] = mapped_column(String(80), nullable=False)
    scene_index: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)

    client: Mapped["Client"] = relationship(back_populates="scenes")
    layers: Mapped[list["Layer"]] = relationship(
        back_populates="scene",
        cascade="all, delete-orphan",
    )


# ============================================================
# LAYER  (reflete exatamente o JSON)
# ============================================================

class Layer(Base):
    __tablename__ = "layers"

    __table_args__ = (
        UniqueConstraint("scene_id", "layer_id", name="uq_layer_per_scene"),
        UniqueConstraint("scene_id", "build_order", name="uq_build_order_per_scene"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"))

    # JSON fields
    layer_id: Mapped[str] = mapped_column(String(80), nullable=False)
    build_order: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    mask: Mapped[str] = mapped_column(String(255), nullable=False)

    scene: Mapped["Scene"] = relationship(back_populates="layers")
    items: Mapped[list["Item"]] = relationship(
        back_populates="layer",
        cascade="all, delete-orphan",
    )


# ============================================================
# ITEM  (reflete exatamente o JSON)
# ============================================================

class Item(Base):
    __tablename__ = "items"

    __table_args__ = (
        UniqueConstraint("layer_id", "material_id", name="uq_item_per_layer"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    layer_id: Mapped[int] = mapped_column(ForeignKey("layers.id", ondelete="CASCADE"))

    # JSON fields
    material_id: Mapped[str] = mapped_column(String(80), nullable=False)
    catalog_index: Mapped[int] = mapped_column(Integer, nullable=False)

    layer: Mapped["Layer"] = relationship(back_populates="items")
