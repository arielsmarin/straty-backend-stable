"""
Tests to ensure no API response contains panoconfig360_cache paths.
All public URLs must use the R2 public base URL.
"""
import importlib
import sys
import types

from fastapi.testclient import TestClient


def _load_server_module():
    sys.modules["pyvips"] = types.SimpleNamespace(Image=object, __version__="mock")
    server = importlib.import_module("api.server")
    return importlib.reload(server)


def test_render_cached_response_uses_r2_url(monkeypatch):
    """Cached render response must contain R2 base URL, not panoconfig360_cache."""
    server = _load_server_module()

    monkeypatch.setattr(server, "load_client_config", lambda cid: ({"scenes": {"s": {}}}, {}))
    monkeypatch.setattr(
        server,
        "resolve_scene_context",
        lambda proj, sid: {"layers": [], "assets_root": "", "scene_index": 0},
    )
    monkeypatch.setattr(server, "build_string_from_selection", lambda *a, **kw: "ab12cd34ef56")
    monkeypatch.setattr(server, "exists", lambda key: True)
    monkeypatch.setattr(server, "get_json", lambda key: {"status": "ready", "tiles_count": 48})

    client = TestClient(server.app)
    resp = client.post(
        "/api/render",
        json={"client": "client1", "scene": "scene1", "selection": {"a": 1}},
    )

    body = resp.json()
    body_str = str(body)
    assert "panoconfig360_cache" not in body_str
    assert body["tiles"]["baseUrl"].startswith("http")


def test_render_processing_response_uses_r2_url(monkeypatch):
    """Processing (202) render response must use R2 base URL."""
    server = _load_server_module()

    monkeypatch.setattr(server, "load_client_config", lambda cid: ({"scenes": {"s": {}}}, {}))
    monkeypatch.setattr(
        server,
        "resolve_scene_context",
        lambda proj, sid: {"layers": [], "assets_root": "", "scene_index": 0},
    )
    monkeypatch.setattr(server, "build_string_from_selection", lambda *a, **kw: "ab12cd34")
    monkeypatch.setattr(server, "exists", lambda key: False)
    monkeypatch.setattr(server, "_render_build_background", lambda *a, **kw: None)

    client = TestClient(server.app)
    resp = client.post(
        "/api/render",
        json={"client": "client1", "scene": "scene1", "selection": {"a": 1}},
    )

    body = resp.json()
    body_str = str(body)
    assert "panoconfig360_cache" not in body_str
    assert body["tiles"]["baseUrl"].startswith("http")


def test_status_completed_requires_tiles_uploaded(monkeypatch):
    """Status endpoint must not return completed when tiles_count is 0."""
    server = _load_server_module()

    # Metadata says ready but tiles_count is 0
    monkeypatch.setattr(server, "get_json", lambda key: {"status": "ready", "tiles_count": 0})

    client = TestClient(server.app)
    resp = client.get("/api/status/ab0000000000?client=client1&scene=scene1")

    body = resp.json()
    assert body["status"] != "completed"


def test_status_completed_when_tiles_match(monkeypatch):
    """Status endpoint returns completed when tiles_uploaded >= tiles_total > 0."""
    server = _load_server_module()

    monkeypatch.setattr(server, "get_json", lambda key: {"status": "ready", "tiles_count": 48})

    client = TestClient(server.app)
    resp = client.get("/api/status/ab0000000000?client=client1&scene=scene1")

    body = resp.json()
    assert body["status"] == "completed"
    assert body["tiles_uploaded"] == 48
    assert body["tiles_total"] == 48


def test_legacy_tile_endpoint_redirects_to_r2():
    """Legacy /panoconfig360_cache/cubemap/... endpoint must redirect to R2."""
    server = _load_server_module()

    client = TestClient(server.app, follow_redirects=False)
    resp = client.get(
        "/panoconfig360_cache/cubemap/client1/scene1/tiles/ab12cd34ef56/ab12cd34ef56_f_0_0_0.jpg"
    )

    assert resp.status_code == 301
    location = resp.headers["location"]
    assert "panoconfig360_cache" not in location
    assert "clients/client1/cubemap/scene1/tiles/ab12cd34ef56/ab12cd34ef56_f_0_0_0.jpg" in location


def test_get_public_url_no_local_paths():
    """get_public_url must never return a local filesystem path."""
    from storage.factory import get_public_url

    url = get_public_url("clients/test/cubemap/scene/tiles/build123/tile.jpg")
    assert "panoconfig360_cache" not in url
    assert url.startswith("http")
