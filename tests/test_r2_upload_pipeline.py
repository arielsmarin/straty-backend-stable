"""Tests for R2 upload pipeline, storage factory defaults, and tile lifecycle logging."""
import importlib
import logging
import os
import sys
import types
from pathlib import Path

from storage.tile_upload_queue import TileUploadQueue


def test_storage_factory_defaults_to_r2(monkeypatch):
    """Storage factory must default to R2 when STORAGE_BACKEND is not set."""
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)

    from storage import factory

    reloaded = importlib.reload(factory)
    assert reloaded.STORAGE_BACKEND == "r2"


def test_storage_factory_rejects_invalid_backend(monkeypatch):
    """Storage factory must raise ValueError for unknown backend names."""
    import pytest

    monkeypatch.setenv("STORAGE_BACKEND", "gcs")

    from storage import factory

    with pytest.raises(ValueError, match="gcs"):
        importlib.reload(factory)


def test_storage_factory_accepts_local_backend(monkeypatch):
    """Storage factory still supports 'local' for staging/development."""
    monkeypatch.setenv("STORAGE_BACKEND", "local")

    from storage import factory

    reloaded = importlib.reload(factory)
    assert reloaded.STORAGE_BACKEND == "local"
    assert callable(reloaded.get_public_url)
    url = reloaded.get_public_url("clients/test/tile.jpg")
    assert url.startswith("http")
    assert "panoconfig360_cache" not in url


def test_tile_upload_lifecycle_logging(tmp_path, caplog):
    """Tile upload must log queueing and upload lifecycle without generation logs."""
    uploaded = []

    def fake_upload(src: str, key: str, content_type: str):
        uploaded.append(key)

    tile_path = tmp_path / "tile_log.jpg"
    tile_path.write_bytes(b"jpg-data")

    queue = TileUploadQueue(
        tile_root="clients/a/cubemap/s/tiles/build",
        upload_fn=fake_upload,
        workers=1,
    )

    with caplog.at_level(logging.INFO):
        queue.start()
        queue.enqueue(tile_path, "build_f_0_0_0.jpg", 0)
        queue.close_and_wait()

    log_text = caplog.text
    assert "tile generated" not in log_text
    assert "tile queued" in log_text
    assert "upload started" in log_text
    assert "upload completed" in log_text
    assert "local file removed" in log_text


def test_multiple_tiles_all_cleaned_after_upload(tmp_path):
    """After all tiles are uploaded, no tile files should remain in local directory."""
    uploaded = []

    def fake_upload(src: str, key: str, content_type: str):
        uploaded.append(key)

    tile_files = []
    for i in range(5):
        tile_path = tmp_path / f"build_f_0_{i}_0.jpg"
        tile_path.write_bytes(b"jpg-data")
        tile_files.append((tile_path, f"build_f_0_{i}_0.jpg"))

    queue = TileUploadQueue(
        tile_root="clients/a/cubemap/s/tiles/build",
        upload_fn=fake_upload,
        workers=2,
    )

    queue.start()
    for path, filename in tile_files:
        queue.enqueue(path, filename, 0)
    queue.close_and_wait()

    assert queue.uploaded_count == 5
    assert len(uploaded) == 5
    # All tile files must be deleted after upload
    remaining = list(tmp_path.glob("*.jpg"))
    assert remaining == []


def test_cache_hit_uses_storage_factory_not_local_fs(monkeypatch):
    """Cache check must go through storage factory, not local filesystem."""
    sys.modules.setdefault(
        "pyvips", types.SimpleNamespace(Image=object, __version__="mock")
    )
    from api import server

    importlib.reload(server)

    exists_calls = []

    def mock_exists(key):
        exists_calls.append(key)
        return True

    monkeypatch.setattr(server, "exists", mock_exists)
    monkeypatch.setattr(
        server, "load_client_config", lambda cid: ({"scenes": {"s": {}}}, {})
    )
    monkeypatch.setattr(
        server,
        "resolve_scene_context",
        lambda proj, sid: {"layers": [], "assets_root": "", "scene_index": 0},
    )
    monkeypatch.setattr(
        server, "build_string_from_selection", lambda *a, **kw: "ab12cd34ef56"
    )

    from fastapi.testclient import TestClient

    client = TestClient(server.app)
    resp = client.post(
        "/api/render",
        json={"client": "client1", "scene": "scene1", "selection": {"a": 1}},
    )

    body = resp.json()
    assert body["status"] == "cached"
    # The cache check must have called exists() with R2-style key
    assert any("metadata.json" in k for k in exists_calls)
    assert any(k.startswith("clients/") for k in exists_calls)
