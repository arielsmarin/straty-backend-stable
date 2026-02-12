from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..repositories.config_repository import ConfigRepository
from ..schemas import (
    ApiResponse,
    ClientCreate,
    ClientResponse,
    ClientUpdate,
    FullConfigOutput,
    LayerCreate,
    LayerResponse,
    ItemCreate,
    ItemResponse,
    SceneCreate,
    SceneResponse,
)
from ..services.config_service import ConfigService, DomainError, NotFoundError, UnauthorizedTenantError
from ..storage.file_storage import BuildLockRegistry, FileStorage

router = APIRouter(prefix="/api")
_lock_registry = BuildLockRegistry()


def get_service(db: AsyncSession = Depends(get_db)) -> ConfigService:
    return ConfigService(ConfigRepository(db), FileStorage(), _lock_registry)


def _tenant_header(x_tenant_id: str | None = Header(default=None)) -> str:
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail={
                            "status": "error", "data": None, "error": "header X-Tenant-ID é obrigatório"})
    return x_tenant_id


def _handle_domain_error(exc: Exception) -> None:
    if isinstance(exc, NotFoundError):
        code = 404
    elif isinstance(exc, UnauthorizedTenantError):
        code = 403
    else:
        code = 400
    raise HTTPException(status_code=code, detail={
                        "status": "error", "data": None, "error": str(exc)})


@router.get("/clients", response_model=ApiResponse[list[ClientResponse]])
async def list_clients(service: ConfigService = Depends(get_service)):
    return ApiResponse(data=await service.list_clients())


@router.post("/clients", response_model=ApiResponse[ClientResponse], status_code=status.HTTP_201_CREATED)
async def create_client(payload: ClientCreate, service: ConfigService = Depends(get_service)):
    try:
        client = await service.create_client(payload)
    except DomainError as exc:
        _handle_domain_error(exc)
    return ApiResponse(data=client)


@router.put("/clients/{client_id}", response_model=ApiResponse[ClientResponse])
async def update_client(client_id: int, payload: ClientUpdate, tenant_key: str = Depends(_tenant_header), service: ConfigService = Depends(get_service)):
    try:
        client = await service.update_client(client_id, payload, tenant_key)
    except DomainError as exc:
        _handle_domain_error(exc)
    return ApiResponse(data=client)


@router.delete("/clients/{client_id}", response_model=ApiResponse[dict])
async def delete_client(client_id: int, tenant_key: str = Depends(_tenant_header), service: ConfigService = Depends(get_service)):
    try:
        await service.delete_client(client_id, tenant_key)
    except DomainError as exc:
        _handle_domain_error(exc)
    return ApiResponse(data={"deleted": True})


@router.get("/clients/{client_id}/scenes", response_model=ApiResponse[list[SceneResponse]])
async def list_scenes(client_id: int, tenant_key: str = Depends(_tenant_header), service: ConfigService = Depends(get_service)):
    try:
        scenes = await service.list_scenes(client_id, tenant_key)
    except DomainError as exc:
        _handle_domain_error(exc)
    return ApiResponse(data=scenes)


@router.post("/clients/{client_id}/scenes", response_model=ApiResponse[SceneResponse], status_code=status.HTTP_201_CREATED)
async def create_scene(client_id: int, payload: SceneCreate, tenant_key: str = Depends(_tenant_header), service: ConfigService = Depends(get_service)):
    try:
        scene = await service.create_scene(client_id, payload, tenant_key)
    except DomainError as exc:
        _handle_domain_error(exc)
    return ApiResponse(data=scene)


@router.get("/scenes/{scene_id}/layers", response_model=ApiResponse[list[LayerResponse]])
async def list_layers(scene_id: int, tenant_key: str = Depends(_tenant_header), service: ConfigService = Depends(get_service)):
    try:
        layers = await service.list_layers(scene_id, tenant_key)
    except DomainError as exc:
        _handle_domain_error(exc)
    return ApiResponse(data=layers)


@router.post("/scenes/{scene_id}/layers", response_model=ApiResponse[LayerResponse], status_code=status.HTTP_201_CREATED)
async def create_layer(scene_id: int, payload: LayerCreate, tenant_key: str = Depends(_tenant_header), service: ConfigService = Depends(get_service)):
    try:
        layer = await service.create_layer(scene_id, payload, tenant_key)
    except DomainError as exc:
        _handle_domain_error(exc)
    return ApiResponse(data=layer)


@router.get("/layers/{layer_id}/items", response_model=ApiResponse[list[ItemResponse]])
async def list_materials(layer_id: int, tenant_key: str = Depends(_tenant_header), service: ConfigService = Depends(get_service)):
    try:
        materials = await service.list_materials(layer_id, tenant_key)
    except DomainError as exc:
        _handle_domain_error(exc)
    return ApiResponse(data=materials)


@router.post("/layers/{layer_id}/items", response_model=ApiResponse[ItemResponse], status_code=status.HTTP_201_CREATED)
async def create_material(layer_id: int, payload: ItemCreate, tenant_key: str = Depends(_tenant_header), service: ConfigService = Depends(get_service)):
    try:
        material = await service.create_material(layer_id, payload, tenant_key)
    except DomainError as exc:
        _handle_domain_error(exc)
    return ApiResponse(data=material)


@router.get("/clients/{client_id}/config", response_model=ApiResponse[FullConfigOutput])
async def export_config(client_id: int, tenant_key: str = Depends(_tenant_header), service: ConfigService = Depends(get_service)):
    try:
        data = await service.export_client_config(client_id, tenant_key)
    except DomainError as exc:
        _handle_domain_error(exc)
    return ApiResponse(data=data)


@router.get("/builds/{build}/validate", response_model=ApiResponse[dict])
async def validate_build(build: str, service: ConfigService = Depends(get_service)):
    valid = await service.validate_build(build)
    if not valid:
        raise HTTPException(status_code=400, detail={
                            "status": "error", "data": None, "error": "build inválida"})
    return ApiResponse(data={"valid": True})


@router.post("/clients/{client_id}/scenes/{scene_index}/layers", response_model=ApiResponse[LayerResponse], status_code=status.HTTP_201_CREATED)
async def create_layer_by_index(
    client_id: int,
    scene_index: int,
    payload: LayerCreate,
    tenant_key: str = Depends(_tenant_header),
    service: ConfigService = Depends(get_service),
):
    try:
        layer = await service.create_layer_by_scene_index(client_id, scene_index, payload, tenant_key)
    except DomainError as exc:
        _handle_domain_error(exc)
    return ApiResponse(data=layer)
