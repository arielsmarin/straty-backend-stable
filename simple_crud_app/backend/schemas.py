from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field
from pydantic.generics import GenericModel

T = TypeVar("T")


class ApiResponse(GenericModel, Generic[T]):
    status: str = "success"
    data: T | None = None
    error: str | None = None


class ClientBase(BaseModel):
    tenant_key: str = Field(min_length=2, max_length=80)
    nome: str = Field(min_length=2, max_length=120)
    email: str
    ativo: bool = True
    asset_base_path: str = ""
    thumbnail: str = ""


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    email: str
    ativo: bool = True
    asset_base_path: str = ""
    thumbnail: str = ""


class ClientResponse(ClientBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class SceneBase(BaseModel):
    scene_key: str = Field(min_length=2, max_length=80)
    scene_index: int = Field(ge=0)
    label: str = Field(min_length=2, max_length=120)
    base_asset_path: str = ""
    thumbnail: str = ""


class SceneCreate(SceneBase):
    pass


class SceneResponse(SceneBase):
    id: int
    client_id: int
    model_config = ConfigDict(from_attributes=True)


class LayerBase(BaseModel):
    layer_id: str = Field(min_length=2, max_length=80)
    label: str = Field(min_length=2, max_length=120)
    build_order: int = Field(ge=0)
    mask_path: str = ""


class LayerCreate(LayerBase):
    pass


class LayerResponse(LayerBase):
    id: int
    scene_id: int
    model_config = ConfigDict(from_attributes=True)


class MaterialBase(BaseModel):
    material_id: str = Field(min_length=2, max_length=80)
    label: str = Field(min_length=2, max_length=120)
    item_index: int = Field(ge=0)
    file_path: str = Field(min_length=1)
    thumbnail: str = ""


class MaterialCreate(MaterialBase):
    pass


class MaterialResponse(MaterialBase):
    id: int
    layer_id: int
    model_config = ConfigDict(from_attributes=True)


class MaterialConfigOutput(BaseModel):
    index: int
    id: str
    label: str
    thumbnail: str
    file: str


class LayerConfigOutput(BaseModel):
    id: str
    build_order: int
    label: str
    mask: str
    items: list[MaterialConfigOutput]


class SceneConfigOutput(BaseModel):
    id: str
    scene_index: int
    label: str
    layers: list[LayerConfigOutput]


class FullConfigOutput(BaseModel):
    schemaVersion: str = "1.0"
    client: dict
    scenes: dict[str, SceneConfigOutput]
    build: str
