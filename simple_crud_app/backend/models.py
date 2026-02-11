from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    asset_base_path: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    thumbnail: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    scenes: Mapped[list["Scene"]] = relationship(back_populates="client", cascade="all, delete-orphan")


class Scene(Base):
    __tablename__ = "scenes"
    __table_args__ = (UniqueConstraint("client_id", "scene_index", name="uq_scene_client_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    scene_key: Mapped[str] = mapped_column(String(80), nullable=False)
    scene_index: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    base_asset_path: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    thumbnail: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    client: Mapped[Client] = relationship(back_populates="scenes")
    layers: Mapped[list["Layer"]] = relationship(back_populates="scene", cascade="all, delete-orphan")


class Layer(Base):
    __tablename__ = "layers"
    __table_args__ = (UniqueConstraint("scene_id", "layer_id", name="uq_layer_scene_layer_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), index=True)
    layer_id: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    build_order: Mapped[int] = mapped_column(Integer, nullable=False)
    mask_path: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    scene: Mapped[Scene] = relationship(back_populates="layers")
    materials: Mapped[list["Material"]] = relationship(back_populates="layer", cascade="all, delete-orphan")


class Material(Base):
    __tablename__ = "materials"
    __table_args__ = (UniqueConstraint("layer_id", "material_id", name="uq_material_layer_material_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    layer_id: Mapped[int] = mapped_column(ForeignKey("layers.id", ondelete="CASCADE"), index=True)
    material_id: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    item_index: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(String(255), nullable=False)
    thumbnail: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    layer: Mapped[Layer] = relationship(back_populates="materials")
