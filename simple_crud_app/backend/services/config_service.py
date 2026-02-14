from sqlalchemy.exc import IntegrityError

from .. import models, schemas
from ..repositories.config_repository import ConfigRepository
from ..storage.file_storage import BuildLockRegistry, FileStorage
from ..utils.build import validate_build
from ..catalog_loader import load_catalog


class DomainError(Exception):
    pass


class NotFoundError(DomainError):
    pass


class UnauthorizedTenantError(DomainError):
    pass


class ConfigService:
    def __init__(
        self,
        repository: ConfigRepository,
        storage: FileStorage,
        lock_registry: BuildLockRegistry,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.lock_registry = lock_registry

    # ============================================================
    # CLIENT
    # ============================================================

    async def list_clients(self) -> list[models.Client]:
        return await self.repository.list_clients()

    async def create_client(
        self, payload: schemas.ClientCreate
    ) -> models.Client:
        client = models.Client(**payload.model_dump())
        try:
            return await self.repository.create_client(client)
        except IntegrityError as exc:
            raise DomainError(
                "tenant_key já cadastrado"
            ) from exc

    async def update_client(
        self,
        client_id: int,
        payload: schemas.ClientUpdate,
        tenant_key: str,
    ) -> models.Client:
        client = await self._get_client_with_tenant(
            client_id, tenant_key
        )

        for key, value in payload.model_dump().items():
            setattr(client, key, value)

        try:
            return await self.repository.update_client(client)
        except IntegrityError as exc:
            raise DomainError(
                "tenant_key já cadastrado"
            ) from exc

    async def delete_client(
        self, client_id: int, tenant_key: str
    ) -> None:
        client = await self._get_client_with_tenant(
            client_id, tenant_key
        )
        await self.repository.delete_client(client)

    # ============================================================
    # SCENE
    # ============================================================

    async def list_scenes(
        self, client_id: int, tenant_key: str
    ) -> list[models.Scene]:
        await self._get_client_with_tenant(
            client_id, tenant_key
        )
        return await self.repository.list_scenes(client_id)

    async def create_scene(
        self,
        client_id: int,
        payload: schemas.SceneCreate,
        tenant_key: str,
    ) -> models.Scene:
        await self._get_client_with_tenant(
            client_id, tenant_key
        )

        data = payload.model_dump()
        data["client_id"] = client_id

        try:
            return await self.repository.create_scene(
                models.Scene(**data)
            )
        except IntegrityError as exc:
            raise DomainError(
                "scene_id ou scene_index já usado para este cliente"
            ) from exc

    # ============================================================
    # LAYER
    # ============================================================

    async def list_layers(
        self, scene_id: int, tenant_key: str
    ) -> list[models.Layer]:
        scene = await self._get_scene(scene_id)
        await self._get_client_with_tenant(
            scene.client_id, tenant_key
        )
        return await self.repository.list_layers(scene_id)

    async def create_layer(
        self,
        scene_id: int,
        payload: schemas.LayerCreate,
        tenant_key: str,
    ) -> models.Layer:

        scene = await self._get_scene(scene_id)
        await self._get_client_with_tenant(
            scene.client_id, tenant_key
        )

        current_layers = await self.repository.list_layers(
            scene_id
        )

        if len(current_layers) >= 4:
            raise DomainError(
                "cada cena aceita no máximo 4 layers"
            )

        data = payload.model_dump()
        data["scene_id"] = scene_id

        try:
            return await self.repository.create_layer(
                models.Layer(**data)
            )
        except IntegrityError as exc:
            raise DomainError(
                "layer_id ou build_order já usado nesta cena"
            ) from exc

    async def create_layer_by_scene_index(
        self,
        client_id: int,
        scene_index: int,
        payload: schemas.LayerCreate,
        tenant_key: str,
    ) -> models.Layer:

        await self._get_client_with_tenant(
            client_id, tenant_key
        )

        scene = await self.repository.get_scene_by_index(
            client_id, scene_index
        )

        if not scene:
            raise NotFoundError(
                "cena não encontrada para este client_id e scene_index"
            )

        current_layers = await self.repository.list_layers(
            scene.id
        )

        if len(current_layers) >= 4:
            raise DomainError(
                "cada cena aceita no máximo 4 layers"
            )

        data = payload.model_dump()
        data["scene_id"] = scene.id

        return await self.repository.create_layer(
            models.Layer(**data)
        )

    # ============================================================
    # ITEM
    # ============================================================

    async def list_items(
        self, layer_id: int, tenant_key: str
    ) -> list[models.Item]:
        layer = await self._get_layer(layer_id)
        scene = await self._get_scene(layer.scene_id)
        await self._get_client_with_tenant(
            scene.client_id, tenant_key
        )
        return await self.repository.list_items(layer_id)

    async def create_item(
        self,
        layer_id: int,
        payload: schemas.ItemCreate,
        tenant_key: str,
    ) -> models.Item:

        layer = await self._get_layer(layer_id)
        scene = await self._get_scene(layer.scene_id)
        client = await self._get_client_with_tenant(
            scene.client_id, tenant_key
        )

        catalog = load_catalog(client.tenant_key)

        if payload.material_id not in catalog:
            raise DomainError(
                f"material '{payload.material_id}' não existe no catálogo"
            )

        data = {
            "layer_id": layer_id,
            "material_id": payload.material_id,
            "catalog_index": payload.catalog_index,
        }

        try:
            return await self.repository.create_item(
                models.Item(**data)
            )
        except IntegrityError as exc:
            raise DomainError(
                "material_id ou catalog_index já usado neste layer"
            ) from exc

    # ============================================================
    # EXPORT
    # ============================================================

    async def export_client_config(
        self, client_id: int, tenant_key: str
    ) -> schemas.FullConfigOutput:

        client = await self._get_client_with_tenant(
            client_id, tenant_key
        )

        lock_key = f"{client.tenant_key}:cfg"
        lock = self.lock_registry.get_lock(lock_key)

        async with lock:
            client_tree = await self.repository.get_client_tree(
                client_id
            )

            if not client_tree:
                raise NotFoundError(
                    "cliente não encontrado"
                )

            catalog = load_catalog(client.tenant_key)

            scenes_sorted = sorted(
                client_tree.scenes,
                key=lambda s: s.scene_index,
            )

            scenes_output: dict[
                str, schemas.SceneConfigOutput
            ] = {}

            for scene in scenes_sorted:

                layers_sorted = sorted(
                    scene.layers,
                    key=lambda l: l.build_order,
                )

                if not 3 <= len(layers_sorted) <= 4:
                    raise DomainError(
                        f"cena {scene.scene_id} precisa ter entre 3 e 4 layers"
                    )

                layers_output: list[
                    schemas.LayerConfigOutput
                ] = []

                for layer in layers_sorted:

                    items_sorted = sorted(
                        layer.items,
                        key=lambda m: m.catalog_index,
                    )

                    if not items_sorted:
                        raise DomainError(
                            f"layer {layer.layer_id} sem materiais"
                        )

                    items_output = []

                    for item in items_sorted:
                        catalog_item = catalog.get(
                            item.material_id
                        )

                        if not catalog_item:
                            raise DomainError(
                                f"material '{item.material_id}' não encontrado no catálogo"
                            )

                        items_output.append(
                            schemas.ItemConfigOutput(
                                index=catalog_item["index"],
                                id=catalog_item["id"],
                                label=catalog_item["label"],
                                thumbnail=catalog_item[
                                    "thumbnail"
                                ],
                                file=catalog_item["file"],
                            )
                        )

                    layers_output.append(
                        schemas.LayerConfigOutput(
                            id=layer.layer_id,
                            build_order=layer.build_order,
                            label=layer.label,
                            mask=layer.mask,
                            items=items_output,
                        )
                    )

                scenes_output[scene.scene_id] = (
                    schemas.SceneConfigOutput(
                        id=scene.scene_id,
                        scene_index=scene.scene_index,
                        label=scene.label,
                        layers=layers_output,
                    )
                )

            return schemas.FullConfigOutput(
                client=schemas.ClientInfo(
                    id=client.tenant_key,
                    label=client.label,
                ),
                project=schemas.ProjectConfig(
                    configStringBase=36,
                    buildChars=2,
                    description="Empilhamento on-demand via R2, 1 config por cliente",
                ),
                naming=schemas.NamingConfig(
                    tilePattern="{BUILD}_{FACE}_{LOD}_{X}_{Y}.jpg",
                    metadataPattern="{BUILD}.json",
                ),
                viewer=schemas.ViewerConfig(
                    type="pano_cubic",
                    tileSize=512,
                    cubeSize=2048,
                    defaultFov=1.5708,
                    camera_rotation_max=1.5708,
                    camera_rotation_min=-1.57,
                    limit_camera_rotation=0,
                ),
                scenes=scenes_output,
            )

    # ============================================================
    # HELPERS
    # ============================================================

    async def validate_build(self, build: str) -> bool:
        return validate_build(build)

    async def _get_client_with_tenant(
        self, client_id: int, tenant_key: str
    ) -> models.Client:

        client = await self.repository.get_client(client_id)

        if not client:
            raise NotFoundError(
                "cliente não encontrado"
            )

        if client.tenant_key != tenant_key:
            raise UnauthorizedTenantError(
                "tenant incorreto para este client_id"
            )

        return client

    async def _get_scene(
        self, scene_id: int
    ) -> models.Scene:
        scene = await self.repository.get_scene(scene_id)
        if not scene:
            raise NotFoundError("cena não encontrada")
        return scene

    async def _get_layer(
        self, layer_id: int
    ) -> models.Layer:
        layer = await self.repository.get_layer(layer_id)
        if not layer:
            raise NotFoundError("layer não encontrado")
        return layer
