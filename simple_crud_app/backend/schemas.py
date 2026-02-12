from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field
from pydantic.generics import GenericModel

T = TypeVar("T")


class ApiResponse(GenericModel, Generic[T]):
    status: str = "success"
    data: T | None = None
    error: str | None = None


class ClientBase(BaseModel):
    tenant_key: str = Field(min_length=1, max_length=80)
    nome: str = Field(min_length=1, max_length=120)
    email: str
    ativo: bool = True
    asset_base_path: str = ""
    thumbnail: str = ""


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    email: str
    ativo: bool = True
    asset_base_path: str = ""
    thumbnail: str = ""


class ClientResponse(ClientBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class SceneBase(BaseModel):
    scene_id: str = Field(min_length=1, max_length=80)
    scene_index: int = Field(ge=0)
    label: str = Field(min_length=1, max_length=120)


class SceneCreate(SceneBase):
    pass


class SceneResponse(SceneBase):
    id: int
    client_id: int
    model_config = ConfigDict(from_attributes=True)


class LayerBase(BaseModel):
    layer_id: str
    label: str
    build_order: int
    mask: str


class LayerCreate(LayerBase):
    pass


class LayerResponse(LayerBase):
    id: int
    scene_id: int
    model_config = ConfigDict(from_attributes=True)


class MaterialBase(BaseModel):
    material_id: str = Field(min_length=1, max_length=80)
    item_index: int = Field(ge=0)


class ItemCreate(BaseModel):
    material_id: str
    catalog_index: int


class ItemResponse(MaterialBase):
    id: int
    layer_id: int
    model_config = ConfigDict(from_attributes=True)


class ItemConfigOutput(BaseModel):
    index: int
    id: str
    label: str
    thumbnail: str
    file: str | None


class LayerConfigOutput(BaseModel):
    id: str
    build_order: int
    label: str
    mask: str
    items: list[ItemConfigOutput
                ]


class SceneConfigOutput(BaseModel):
    id: str
    scene_index: int
    label: str
    layers: list[LayerConfigOutput]


class ClientInfo(BaseModel):
    id: str
    label: str


class ProjectConfig(BaseModel):
    configStringBase: int
    buildChars: int
    description: str


class NamingConfig(BaseModel):
    tilePattern: str
    metadataPattern: str


class ViewerConfig(BaseModel):
    type: str
    tileSize: int
    cubeSize: int
    defaultFov: float
    camera_rotation_max: float
    camera_rotation_min: float
    limit_camera_rotation: int


class FullConfigOutput(BaseModel):
    schemaVersion: str = "2.0"
    client: ClientInfo
    project: ProjectConfig
    naming: NamingConfig
    viewer: ViewerConfig
    scenes: dict[str, SceneConfigOutput]
