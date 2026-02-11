from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import models


class ConfigRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_clients(self) -> list[models.Client]:
        result = await self.db.execute(select(models.Client).order_by(models.Client.id))
        return list(result.scalars().all())

    async def get_client(self, client_id: int) -> models.Client | None:
        return await self.db.get(models.Client, client_id)

    async def create_client(self, client: models.Client) -> models.Client:
        self.db.add(client)
        await self.db.commit()
        await self.db.refresh(client)
        return client

    async def update_client(self, client: models.Client) -> models.Client:
        await self.db.commit()
        await self.db.refresh(client)
        return client

    async def delete_client(self, client: models.Client) -> None:
        await self.db.delete(client)
        await self.db.commit()

    async def list_scenes(self, client_id: int) -> list[models.Scene]:
        result = await self.db.execute(
            select(models.Scene).where(models.Scene.client_id == client_id).order_by(models.Scene.scene_index)
        )
        return list(result.scalars().all())

    async def get_scene(self, scene_id: int) -> models.Scene | None:
        return await self.db.get(models.Scene, scene_id)

    async def create_scene(self, scene: models.Scene) -> models.Scene:
        self.db.add(scene)
        await self.db.commit()
        await self.db.refresh(scene)
        return scene

    async def list_layers(self, scene_id: int) -> list[models.Layer]:
        result = await self.db.execute(
            select(models.Layer).where(models.Layer.scene_id == scene_id).order_by(models.Layer.build_order)
        )
        return list(result.scalars().all())

    async def create_layer(self, layer: models.Layer) -> models.Layer:
        self.db.add(layer)
        await self.db.commit()
        await self.db.refresh(layer)
        return layer

    async def list_materials(self, layer_id: int) -> list[models.Material]:
        result = await self.db.execute(
            select(models.Material).where(models.Material.layer_id == layer_id).order_by(models.Material.item_index)
        )
        return list(result.scalars().all())

    async def create_material(self, material: models.Material) -> models.Material:
        self.db.add(material)
        await self.db.commit()
        await self.db.refresh(material)
        return material

    async def get_client_tree(self, client_id: int) -> models.Client | None:
        query = (
            select(models.Client)
            .where(models.Client.id == client_id)
            .options(
                selectinload(models.Client.scenes)
                .selectinload(models.Scene.layers)
                .selectinload(models.Layer.materials)
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
