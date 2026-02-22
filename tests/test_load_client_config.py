import json
import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException


class _FakeBody:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload


class _FakeS3Client:
    def __init__(self, data_by_key=None, missing_keys=None):
        self.data_by_key = data_by_key or {}
        self.missing_keys = set(missing_keys or [])

    def get_object(self, Bucket, Key):
        if Key in self.missing_keys:
            raise ClientError(
                error_response={"Error": {"Code": "NoSuchKey"}},
                operation_name="GetObject",
            )
        return {"Body": _FakeBody(self.data_by_key[Key])}


def test_load_client_config_not_found_in_r2(monkeypatch):
    """Missing config in R2 should raise ValueError."""
    from api import server

    key = "clients/testclient/testclient_cfg.json"
    monkeypatch.setattr(
        server.storage_r2,
        "s3_client",
        _FakeS3Client(missing_keys={key}),
    )

    with pytest.raises(ValueError, match="não encontrada no R2"):
        server.load_client_config("testclient")


def test_load_client_config_invalid_json(monkeypatch):
    """Invalid JSON in config should raise ValueError."""
    from api import server

    key = "clients/testclient/testclient_cfg.json"
    monkeypatch.setattr(
        server.storage_r2,
        "s3_client",
        _FakeS3Client(data_by_key={key: b"{invalid json content"}),
    )

    with pytest.raises(ValueError, match="JSON inválido"):
        server.load_client_config("testclient")


def test_load_client_config_no_scenes(monkeypatch):
    """Config with empty scenes should return default scene."""
    from api import server

    key = "clients/testclient/testclient_cfg.json"
    payload = json.dumps({"scenes": {}, "layers": []}).encode("utf-8")
    monkeypatch.setattr(
        server.storage_r2,
        "s3_client",
        _FakeS3Client(data_by_key={key: payload}),
    )

    project, naming = server.load_client_config("testclient")
    assert "default" in project["scenes"]
    assert naming == {}


def test_load_client_config_valid(monkeypatch):
    """Valid config should load successfully from R2."""
    from api import server

    key = "clients/testclient/testclient_cfg.json"
    cfg = {
        "scenes": {
            "kitchen": {
                "scene_index": 0,
                "layers": [
                    {
                        "id": "floor",
                        "build_order": 0,
                        "items": [{"id": "marble", "index": 1, "file": "marble.png"}],
                    }
                ],
            }
        },
        "naming": {"prefix": "test"},
    }
    monkeypatch.setattr(
        server.storage_r2,
        "s3_client",
        _FakeS3Client(data_by_key={key: json.dumps(cfg).encode("utf-8")}),
    )

    project, naming = server.load_client_config("testclient")
    assert project["client_id"] == "testclient"
    assert "kitchen" in project["scenes"]
    assert naming == {"prefix": "test"}


def test_load_client_config_path_traversal():
    """Path traversal in client_id should raise HTTPException 400."""
    from api import server

    with pytest.raises(HTTPException) as exc_info:
        server.load_client_config("../../../etc/passwd")
    assert exc_info.value.status_code == 400
