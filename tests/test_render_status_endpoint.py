import importlib
import sys
import types

from fastapi.testclient import TestClient


def _load_server_module():
    sys.modules["pyvips"] = types.SimpleNamespace(Image=object, __version__="mock")
    server = importlib.import_module("api.server")
    return importlib.reload(server)


def test_render_cache_miss_returns_202(monkeypatch):
    server = _load_server_module()

    monkeypatch.setattr(server, "load_client_config", lambda client_id: ({"scenes": {"scene": {}}}, {}))
    monkeypatch.setattr(
        server,
        "resolve_scene_context",
        lambda project, scene_id: {"layers": [], "assets_root": "", "scene_index": 0},
    )
    monkeypatch.setattr(server, "build_string_from_selection", lambda *args, **kwargs: "ab12cd34")
    monkeypatch.setattr(server, "exists", lambda key: False)
    monkeypatch.setattr(server, "_render_build_background", lambda *args, **kwargs: None)

    client = TestClient(server.app)
    response = client.post(
        "/api/render",
        json={"client": "client1", "scene": "scene1", "selection": {"a": 1}},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "processing"
    assert response.json()["build"] == "ab12cd34"
    assert response.json()["tiles"]["build"] == "ab12cd34"
    assert response.json()["tiles"]["tileRoot"] == "clients/client1/cubemap/scene1/tiles/ab12cd34"


def test_status_returns_processing_when_metadata_missing(monkeypatch):
    server = _load_server_module()

    def _raise_not_found(key):
        raise FileNotFoundError(key)

    monkeypatch.setattr(server, "get_json", _raise_not_found)

    client = TestClient(server.app)
    response = client.get("/api/status/ab0000000000?client=client1&scene=scene1")

    assert response.status_code == 200
    assert response.json() == {"status": "idle"}


def test_status_returns_done_when_metadata_ready(monkeypatch):
    server = _load_server_module()

    monkeypatch.setattr(server, "get_json", lambda key: {"status": "ready", "tiles_count": 48})

    client = TestClient(server.app)
    response = client.get("/api/status/ab0000000000?client=client1&scene=scene1")

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["build"] == "ab0000000000"
    tiles = response.json()["tiles"]
    assert "baseUrl" in tiles
    assert tiles["tileRoot"] == "clients/client1/cubemap/scene1/tiles/ab0000000000"
    assert tiles["build"] == "ab0000000000"


def test_status_returns_idle_for_invalid_build():
    server = _load_server_module()

    client = TestClient(server.app)
    response = client.get("/api/status/invalid-build?client=client1&scene=scene1")

    assert response.status_code == 200
    assert response.json() == {"status": "idle"}


def test_status_returns_upload_progress(monkeypatch):
    server = _load_server_module()

    def _raise_not_found(key):
        raise FileNotFoundError(key)

    monkeypatch.setattr(server, "get_json", _raise_not_found)
    with server.BUILD_LOCK:
        server.BUILD_STATUS["ab0000000000"] = {
            "status": "uploading",
            "tiles_uploaded": 12,
            "tiles_total": 48,
            "progress": 0.25,
            "error": None,
        }

    client = TestClient(server.app)
    try:
        response = client.get("/api/status/ab0000000000?client=client1&scene=scene1")

        assert response.status_code == 200
        data = response.json()
        assert data["build"] == "ab0000000000"
        assert data["status"] == "uploading"
        assert data["tiles_uploaded"] == 12
        assert data["tiles_total"] == 48
        assert data["progress"] == 0.25
        assert "tiles" in data
        assert data["tiles"]["tileRoot"] == "clients/client1/cubemap/scene1/tiles/ab0000000000"
        assert data["tiles"]["build"] == "ab0000000000"
    finally:
        with server.BUILD_LOCK:
            server.BUILD_STATUS.pop("ab0000000000", None)


def test_status_returns_extended_progress_fields(monkeypatch):
    server = _load_server_module()

    def _raise_not_found(key):
        raise FileNotFoundError(key)

    monkeypatch.setattr(server, "get_json", _raise_not_found)
    with server.BUILD_LOCK:
        server.BUILD_STATUS["ab0000000000"] = {
            "status": "uploading",
            "tiles_uploaded": 12,
            "tiles_total": 48,
            "progress": 0.25,
            "percent_complete": 0.25,
            "faces_ready": True,
            "tiles_ready": True,
            "lod_ready": 0,
            "error": None,
        }

    client = TestClient(server.app)
    try:
        response = client.get("/api/status/ab0000000000?client=client1&scene=scene1")

        assert response.status_code == 200
        assert response.json()["percent_complete"] == 0.25
        assert response.json()["faces_ready"] is True
        assert response.json()["tiles_ready"] is True
        assert response.json()["lod_ready"] == 0
    finally:
        with server.BUILD_LOCK:
            server.BUILD_STATUS.pop("ab0000000000", None)


def test_stream_tiles_to_storage_uses_queue_and_returns_uploaded_count(monkeypatch, tmp_path):
    server = _load_server_module()

    observed = {}

    class FakeQueue:
        def __init__(self, tile_root, upload_fn, workers, on_state_change):
            observed["tile_root"] = tile_root
            observed["workers"] = workers
            observed["state_cb"] = on_state_change
            self.uploaded_count = 3
            self.enqueue = lambda *args, **kwargs: None
            self.close_calls = 0

        def start(self):
            observed["started"] = True

        def close_and_wait(self):
            self.close_calls += 1
            observed["close_calls"] = self.close_calls

    def fake_process_cubemap(img, out_dir, tile_size, build, min_lod, max_lod, on_tile_ready):
        observed["out_dir"] = out_dir
        observed["build"] = build
        observed["min_lod"] = min_lod
        observed["max_lod"] = max_lod
        assert on_tile_ready is None, "on_tile_ready must be None in the two-phase pipeline"
        # Create tile files so the upload phase can find them
        from pathlib import Path
        for i in range(3):
            (Path(out_dir) / f"{build}_f_0_{i}_0.jpg").write_bytes(b"jpg")

    monkeypatch.setattr(server, "TileUploadQueue", FakeQueue)
    monkeypatch.setattr(server, "process_cubemap", fake_process_cubemap)

    total = server._stream_tiles_to_storage(
        stack_img=object(),
        tile_root="clients/a/cubemap/s/tiles/ab12",
        build_str="ab12",
        tmp_dir=str(tmp_path),
        min_lod=0,
        max_lod=0,
        workers=2,
        on_state_change=lambda *_: None,
    )

    assert total == 3
    assert observed["started"] is True
    assert observed["tile_root"] == "clients/a/cubemap/s/tiles/ab12"
    assert observed["workers"] == 2
    assert observed["out_dir"] == str(tmp_path)
    assert observed["build"] == "ab12"
    assert observed["min_lod"] == 0
    assert observed["max_lod"] == 0
    assert observed["close_calls"] >= 1


def test_render_returns_queued_when_capacity_is_full(monkeypatch):
    server = _load_server_module()

    monkeypatch.setattr(server, "load_client_config", lambda client_id: ({"scenes": {"scene": {}}}, {}))
    monkeypatch.setattr(
        server,
        "resolve_scene_context",
        lambda project, scene_id: {"layers": [], "assets_root": "", "scene_index": 0},
    )
    monkeypatch.setattr(server, "build_string_from_selection", lambda *args, **kwargs: "ab12cd34")
    monkeypatch.setattr(server, "exists", lambda key: False)

    class BusySlots:
        def acquire(self, blocking=False):
            return False

    monkeypatch.setattr(server, "_active_render_pipeline_slots", BusySlots())

    client = TestClient(server.app)
    response = client.post(
        "/api/render",
        json={"client": "client1", "scene": "scene1", "selection": {"a": 1}},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["reason"] == "render_capacity"
