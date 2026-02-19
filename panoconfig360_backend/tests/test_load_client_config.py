import json
import pytest
from fastapi import HTTPException


def test_load_client_config_file_not_found(monkeypatch):
    """Config file doesn't exist should raise FileNotFoundError."""
    from panoconfig360_backend.api import server

    monkeypatch.setattr(server, "LOCAL_CACHE_DIR", __import__("pathlib").Path("/tmp/nonexistent"))

    with pytest.raises(FileNotFoundError, match="não encontrada"):
        server.load_client_config("testclient")


def test_load_client_config_invalid_json(tmp_path, monkeypatch):
    """Invalid JSON in config should raise ValueError."""
    from panoconfig360_backend.api import server

    monkeypatch.setattr(server, "LOCAL_CACHE_DIR", tmp_path)

    client_dir = tmp_path / "clients" / "testclient"
    client_dir.mkdir(parents=True)
    cfg_path = client_dir / "testclient_cfg.json"
    cfg_path.write_text("{invalid json content")

    with pytest.raises(ValueError, match="JSON inválido"):
        server.load_client_config("testclient")


def test_load_client_config_no_scenes(tmp_path, monkeypatch):
    """Config with empty scenes should raise ValueError."""
    from panoconfig360_backend.api import server

    monkeypatch.setattr(server, "LOCAL_CACHE_DIR", tmp_path)

    client_dir = tmp_path / "clients" / "testclient"
    client_dir.mkdir(parents=True)
    cfg_path = client_dir / "testclient_cfg.json"
    cfg_path.write_text(json.dumps({"scenes": {}, "layers": []}))

    # load_config will provide a default scene when scenes is empty/falsy
    # so this should succeed and return a project with a "default" scene
    project, naming = server.load_client_config("testclient")
    assert "default" in project["scenes"]


def test_load_client_config_valid(tmp_path, monkeypatch):
    """Valid config should load successfully."""
    from panoconfig360_backend.api import server

    monkeypatch.setattr(server, "LOCAL_CACHE_DIR", tmp_path)

    client_dir = tmp_path / "clients" / "testclient"
    client_dir.mkdir(parents=True)
    cfg_path = client_dir / "testclient_cfg.json"
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
    cfg_path.write_text(json.dumps(cfg))

    project, naming = server.load_client_config("testclient")
    assert project["client_id"] == "testclient"
    assert "kitchen" in project["scenes"]
    assert naming == {"prefix": "test"}


def test_load_client_config_path_traversal():
    """Path traversal in client_id should raise HTTPException 400."""
    from panoconfig360_backend.api import server

    with pytest.raises(HTTPException) as exc_info:
        server.load_client_config("../../../etc/passwd")
    assert exc_info.value.status_code == 400
