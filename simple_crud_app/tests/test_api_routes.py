import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

pytest.importorskip("sqlalchemy")
pytest.importorskip("email_validator")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from backend.main import app
from backend.routes.config_routes import get_service
from backend.services.config_service import DomainError, UnauthorizedTenantError


class FakeService:
    async def list_clients(self):
        return []

    async def create_client(self, payload):
        return {
            "id": 1,
            "tenant_key": payload.tenant_key,
            "nome": payload.nome,
            "email": payload.email,
            "ativo": payload.ativo,
            "asset_base_path": payload.asset_base_path,
            "thumbnail": payload.thumbnail,
        }

    async def list_scenes(self, client_id, tenant_key):
        if tenant_key != "tenant-a":
            raise UnauthorizedTenantError("tenant incorreto para este client_id")
        return []

    async def create_scene(self, client_id, payload, tenant_key):
        if payload.base_asset_path == "missing/asset.png":
            raise DomainError("asset ausente: missing/asset.png")
        return {
            "id": 10,
            "client_id": client_id,
            "scene_key": payload.scene_key,
            "scene_index": payload.scene_index,
            "label": payload.label,
            "base_asset_path": payload.base_asset_path,
            "thumbnail": payload.thumbnail,
        }

    async def validate_build(self, build):
        return build == "abc123"


@pytest.fixture
def client():
    app.dependency_overrides[get_service] = lambda: FakeService()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_validate_build_invalid_returns_envelope(client: TestClient):
    response = client.get("/api/builds/INVALID+/validate")
    assert response.status_code == 400
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"] == "build inválida"


def test_create_scene_missing_asset_returns_envelope(client: TestClient):
    response = client.post(
        "/api/clients/1/scenes",
        headers={"X-Tenant-ID": "tenant-a"},
        json={
            "scene_key": "kitchen",
            "scene_index": 0,
            "label": "Kitchen",
            "base_asset_path": "missing/asset.png",
            "thumbnail": "",
        },
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["status"] == "error"
    assert "asset ausente" in payload["error"]


def test_list_scenes_with_wrong_tenant_returns_envelope(client: TestClient):
    response = client.get("/api/clients/1/scenes", headers={"X-Tenant-ID": "tenant-b"})
    assert response.status_code == 403
    payload = response.json()
    assert payload["status"] == "error"
    assert "tenant incorreto" in payload["error"]
