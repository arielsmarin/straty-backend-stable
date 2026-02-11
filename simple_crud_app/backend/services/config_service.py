from pathlib import Path

from sqlalchemy.exc import IntegrityError

from .. import models, schemas
from ..repositories.config_repository import ConfigRepository
from ..storage.file_storage import BuildLockRegistry, FileStorage
from ..utils.build import build_key_from_indexes, validate_build


class DomainError(Exception):
    pass


class NotFoundError(DomainError):
    pass


class UnauthorizedTenantError(DomainError):
    pass


class ConfigService:
    def __init__(self, repository: ConfigRepository, storage: FileStorage, lock_registry: BuildLockRegistry) -> None:
        self.repository = repository
        self.storage = storage
        self.lock_registry = lock_registry

    async def list_clients(self) -> list[models.Client]:
        return await self.repository.list_clients()

    async def create_client(self, payload: schemas.ClientCreate) -> models.Client:
        client = models.Client(**payload.model_dump())
        try:
            return await self.repository.create_client(client)
        except IntegrityError as exc:
            raise DomainError("tenant_key ou email já cadastrado") from exc

    async def update_client(self, client_id: int, payload: schemas.ClientUpdate, tenant_key: str) -> models.Client:
        client = await self._get_client_with_tenant(client_id, tenant_key)
        for key, value in payload.model_dump().items():
            setattr(client, key, value)
        try:
            return await self.repository.update_client(client)
        except IntegrityError as exc:
            raise DomainError("email já cadastrado") from exc

    async def delete_client(self, client_id: int, tenant_key: str) -> None:
        client = await self._get_client_with_tenant(client_id, tenant_key)
        await self.repository.delete_client(client)

    async def list_scenes(self, client_id: int, tenant_key: str) -> list[models.Scene]:
        await self._get_client_with_tenant(client_id, tenant_key)
        return await self.repository.list_scenes(client_id)

    async def create_scene(self, client_id: int, payload: schemas.SceneCreate, tenant_key: str) -> models.Scene:
        await self._get_client_with_tenant(client_id, tenant_key)
        self._assert_relative_path(payload.base_asset_path)
        await self._assert_asset_if_provided(payload.base_asset_path)
        scene = models.Scene(client_id=client_id, **payload.model_dump())
        try:
            return await self.repository.create_scene(scene)
        except IntegrityError as exc:
            raise DomainError("scene_index já usado para este cliente") from exc

    async def list_layers(self, scene_id: int, tenant_key: str) -> list[models.Layer]:
        scene = await self._get_scene(scene_id)
        await self._get_client_with_tenant(scene.client_id, tenant_key)
        return await self.repository.list_layers(scene_id)

    async def create_layer(self, scene_id: int, payload: schemas.LayerCreate, tenant_key: str) -> models.Layer:
        scene = await self._get_scene(scene_id)
        await self._get_client_with_tenant(scene.client_id, tenant_key)
        current_layers = await self.repository.list_layers(scene_id)
        if len(current_layers) >= 4:
            raise DomainError("cada cena aceita no máximo 4 layers")
        self._assert_relative_path(payload.mask_path)
        await self._assert_asset_if_provided(payload.mask_path)
        layer = models.Layer(scene_id=scene_id, **payload.model_dump())
        try:
            return await self.repository.create_layer(layer)
        except IntegrityError as exc:
            raise DomainError("layer_id já usado nesta cena") from exc

    async def list_materials(self, layer_id: int, tenant_key: str) -> list[models.Material]:
        layer = await self._get_layer(layer_id)
        scene = await self._get_scene(layer.scene_id)
        await self._get_client_with_tenant(scene.client_id, tenant_key)
        return await self.repository.list_materials(layer_id)

    async def create_material(self, layer_id: int, payload: schemas.MaterialCreate, tenant_key: str) -> models.Material:
        layer = await self._get_layer(layer_id)
        scene = await self._get_scene(layer.scene_id)
        await self._get_client_with_tenant(scene.client_id, tenant_key)
        self._assert_relative_path(payload.file_path)
        self._assert_relative_path(payload.thumbnail)
        await self._assert_asset_if_provided(payload.file_path)
        material = models.Material(layer_id=layer_id, **payload.model_dump())
        try:
            return await self.repository.create_material(material)
        except IntegrityError as exc:
            raise DomainError("material_id já usado neste layer") from exc

    async def export_client_config(self, client_id: int, tenant_key: str) -> schemas.FullConfigOutput:
        client = await self._get_client_with_tenant(client_id, tenant_key)
        lock_key = f"{client.tenant_key}:cfg"
        lock = self.lock_registry.get_lock(lock_key)
        async with lock:
            client_tree = await self.repository.get_client_tree(client_id)
            if not client_tree:
                raise NotFoundError("cliente não encontrado")
            scenes_sorted = sorted(client_tree.scenes, key=lambda s: s.scene_index)
            scenes_output: dict[str, schemas.SceneConfigOutput] = {}
            layer_indexes: list[int] = []

            for scene in scenes_sorted:
                layers_sorted = sorted(scene.layers, key=lambda l: l.build_order)
                if len(layers_sorted) < 3 or len(layers_sorted) > 4:
                    raise DomainError(f"cena {scene.scene_key} precisa ter entre 3 e 4 layers")
                layers_output: list[schemas.LayerConfigOutput] = []
                for layer in layers_sorted:
                    materials_sorted = sorted(layer.materials, key=lambda m: m.item_index)
                    if not materials_sorted:
                        raise DomainError(f"layer {layer.layer_id} sem materiais")
                    layer_indexes.append(materials_sorted[0].item_index)
                    items = [
                        schemas.MaterialConfigOutput(
                            index=m.item_index,
                            id=m.material_id,
                            label=m.label,
                            thumbnail=m.thumbnail,
                            file=m.file_path,
                        )
                        for m in materials_sorted
                    ]
                    layers_output.append(
                        schemas.LayerConfigOutput(
                            id=layer.layer_id,
                            build_order=layer.build_order,
                            label=layer.label,
                            mask=layer.mask_path,
                            items=items,
                        )
                    )
                scenes_output[scene.scene_key] = schemas.SceneConfigOutput(
                    id=scene.scene_key,
                    scene_index=scene.scene_index,
                    label=scene.label,
                    layers=layers_output,
                )

            build = build_key_from_indexes(scenes_sorted[0].scene_index if scenes_sorted else 0, layer_indexes)
            return schemas.FullConfigOutput(
                client={
                    "id": client.id,
                    "tenant_key": client.tenant_key,
                    "name": client.nome,
                    "asset_base_path": client.asset_base_path,
                    "thumbnail": client.thumbnail,
                },
                scenes=scenes_output,
                build=build,
            )

    async def validate_build(self, build: str) -> bool:
        return validate_build(build)

    async def _get_client_with_tenant(self, client_id: int, tenant_key: str) -> models.Client:
        client = await self.repository.get_client(client_id)
        if not client:
            raise NotFoundError("cliente não encontrado")
        if client.tenant_key != tenant_key:
            raise UnauthorizedTenantError("tenant incorreto para este client_id")
        return client

    async def _get_scene(self, scene_id: int) -> models.Scene:
        scene = await self.repository.get_scene(scene_id)
        if not scene:
            raise NotFoundError("cena não encontrada")
        return scene

    async def _get_layer(self, layer_id: int) -> models.Layer:
        layer = await self.repository.db.get(models.Layer, layer_id)
        if not layer:
            raise NotFoundError("layer não encontrado")
        return layer

    async def _assert_asset_if_provided(self, path: str) -> None:
        if not path:
            return
        try:
            exists = await self.storage.exists(path)
        except OSError as exc:
            raise DomainError(f"falha de I/O ao validar asset: {exc}") from exc
        if not exists:
            raise DomainError(f"asset ausente: {path}")

    @staticmethod
    def _assert_relative_path(path: str) -> None:
        if not path:
            return
        if Path(path).is_absolute():
            raise DomainError("caminhos absolutos não são permitidos")
