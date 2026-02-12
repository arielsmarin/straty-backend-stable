import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

import asyncio
import pytest
from dataclasses import dataclass, field

pytest.importorskip("sqlalchemy")

from backend import schemas
from backend.services.config_service import ConfigService, DomainError, UnauthorizedTenantError
from backend.storage.file_storage import BuildLockRegistry


@dataclass
class FakeClient:
    id: int
    tenant_key: str
    nome: str
    email: str
    ativo: bool = True
    asset_base_path: str = ""
    thumbnail: str = ""
    scenes: list = field(default_factory=list)


@dataclass
class FakeScene:
    id: int
    client_id: int
    scene_key: str
    scene_index: int
    label: str
    base_asset_path: str = ""
    thumbnail: str = ""
    layers: list = field(default_factory=list)


@dataclass
class FakeLayer:
    id: int
    scene_id: int
    layer_id: str
    label: str
    build_order: int
    mask_path: str
    materials: list = field(default_factory=list)


@dataclass
class FakeMaterial:
    id: int
    layer_id: int
    material_id: str
    label: str
    item_index: int
    file_path: str
    thumbnail: str = ""


class FakeRepo:
    def __init__(self):
        self.clients = {}
        self.scenes = {}
        self.layers = {}
        self.materials = {}
        self.cid = self.sid = self.lid = self.mid = 0
        self.db = self

    async def list_clients(self):
        return list(self.clients.values())

    async def get_client(self, client_id):
        return self.clients.get(client_id)

    async def create_client(self, client):
        self.cid += 1
        data = FakeClient(id=self.cid, **client.__dict__)
        self.clients[self.cid] = data
        return data

    async def update_client(self, client):
        return client

    async def delete_client(self, client):
        del self.clients[client.id]

    async def list_scenes(self, client_id):
        return [s for s in self.scenes.values() if s.client_id == client_id]

    async def get_scene(self, scene_id):
        return self.scenes.get(scene_id)

    async def create_scene(self, scene):
        self.sid += 1
        data = FakeScene(id=self.sid, **scene.__dict__)
        self.scenes[self.sid] = data
        self.clients[data.client_id].scenes.append(data)
        return data

    async def list_layers(self, scene_id):
        return [l for l in self.layers.values() if l.scene_id == scene_id]

    async def create_layer(self, layer):
        self.lid += 1
        data = FakeLayer(id=self.lid, **layer.__dict__)
        self.layers[self.lid] = data
        self.scenes[data.scene_id].layers.append(data)
        return data

    async def list_materials(self, layer_id):
        return [m for m in self.materials.values() if m.layer_id == layer_id]

    async def create_material(self, material):
        self.mid += 1
        data = FakeMaterial(id=self.mid, **material.__dict__)
        self.materials[self.mid] = data
        self.layers[data.layer_id].materials.append(data)
        return data

    async def get_client_tree(self, client_id):
        return self.clients.get(client_id)

    async def get(self, model, layer_id):
        return self.layers.get(layer_id)


class FakeStorage:
    def __init__(self, should_fail=False, existing=True):
        self.should_fail = should_fail
        self.existing = existing

    async def exists(self, _):
        if self.should_fail:
            raise OSError("disk error")
        return self.existing


def run(coro):
    return asyncio.run(coro)


def mk_service(storage=None):
    return ConfigService(FakeRepo(), storage or FakeStorage(existing=True), BuildLockRegistry())


def test_full_flow_and_export():
    service = mk_service()
    c = run(service.create_client(schemas.ClientCreate(tenant_key="t1", nome="Tenant 1", email="t1@example.com")))
    scene = run(service.create_scene(c.id, schemas.SceneCreate(scene_key="kitchen", scene_index=0, label="Kitchen"), "t1"))

    for idx, lid in enumerate(["barbecue", "countertop", "island"]):
        layer = run(service.create_layer(scene.id, schemas.LayerCreate(layer_id=lid, label=lid, build_order=idx, mask_path="m"), "t1"))
        run(service.create_material(layer.id, schemas.ItemCreate(material_id=f"mtl-{lid}", label=lid, item_index=idx, file_path="f"), "t1"))

    cfg = run(service.export_client_config(c.id, "t1"))
    assert cfg.client["tenant_key"] == "t1"
    assert len(cfg.scenes["kitchen"].layers) == 3
    assert isinstance(cfg.build, str)


def test_invalid_build():
    service = mk_service()
    assert run(service.validate_build("abc123"))
    assert not run(service.validate_build("INVALID+"))


def test_tenant_incorrect_error():
    service = mk_service()
    c = run(service.create_client(schemas.ClientCreate(tenant_key="t1", nome="Tenant 1", email="t1@example.com")))
    try:
        run(service.list_scenes(c.id, "other"))
        assert False
    except UnauthorizedTenantError:
        assert True


def test_asset_missing_error():
    service = mk_service(storage=FakeStorage(existing=False))
    c = run(service.create_client(schemas.ClientCreate(tenant_key="t2", nome="Tenant 2", email="t2@example.com")))
    try:
        run(service.create_scene(c.id, schemas.SceneCreate(scene_key="k", scene_index=0, label="K", base_asset_path="not/found"), "t2"))
        assert False
    except DomainError as exc:
        assert "asset ausente" in str(exc)


def test_io_failure_error():
    service = mk_service(storage=FakeStorage(should_fail=True))
    c = run(service.create_client(schemas.ClientCreate(tenant_key="t3", nome="Tenant 3", email="t3@example.com")))
    try:
        run(service.create_scene(c.id, schemas.SceneCreate(scene_key="k", scene_index=0, label="K", base_asset_path="x"), "t3"))
        assert False
    except DomainError as exc:
        assert "falha de I/O" in str(exc)
