from fastapi.testclient import TestClient


def test_render_cache_miss_returns_202(monkeypatch):
    from panoconfig360_backend.api import server

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
    from panoconfig360_backend.api import server

    def _raise_not_found(key):
        raise FileNotFoundError(key)

    monkeypatch.setattr(server, "get_json", _raise_not_found)

    client = TestClient(server.app)
    response = client.get("/api/status/ab0000000000?client=client1&scene=scene1")

    assert response.status_code == 200
    assert response.json() == {"status": "idle"}


def test_status_returns_done_when_metadata_ready(monkeypatch):
    from panoconfig360_backend.api import server

    monkeypatch.setattr(server, "get_json", lambda key: {"status": "ready"})

    client = TestClient(server.app)
    response = client.get("/api/status/ab0000000000?client=client1&scene=scene1")

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["build"] == "ab0000000000"


def test_status_returns_idle_for_invalid_build():
    from panoconfig360_backend.api import server

    client = TestClient(server.app)
    response = client.get("/api/status/invalid-build?client=client1&scene=scene1")

    assert response.status_code == 200
    assert response.json() == {"status": "idle"}


def test_status_returns_upload_progress(monkeypatch):
    from panoconfig360_backend.api import server

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
        assert response.json() == {
            "build": "ab0000000000",
            "status": "uploading",
            "tiles_uploaded": 12,
            "tiles_total": 48,
            "progress": 0.25,
        }
    finally:
        with server.BUILD_LOCK:
            server.BUILD_STATUS.pop("ab0000000000", None)


def test_status_returns_extended_progress_fields(monkeypatch):
    from panoconfig360_backend.api import server

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
