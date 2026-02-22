import importlib
import sys
import types


def test_server_has_no_frontend_static_mounts():
    sys.modules["pyvips"] = types.SimpleNamespace(Image=object, __version__="mock")
    server = importlib.import_module("api.server")
    app = importlib.reload(server).app
    paths = {route.path for route in app.routes}
    assert "/static" not in paths
    assert "/assets" not in paths
    assert "/" not in paths


def test_server_has_no_root_html_route():
    sys.modules["pyvips"] = types.SimpleNamespace(Image=object, __version__="mock")
    server = importlib.import_module("api.server")
    app = importlib.reload(server).app
    paths = {route.path for route in app.routes}
    assert "/" not in paths


def test_server_has_cloudflare_cors_default():
    sys.modules["pyvips"] = types.SimpleNamespace(Image=object, __version__="mock")
    server = importlib.import_module("api.server")
    module = importlib.reload(server)
    cors = next(m for m in module.app.user_middleware if m.cls.__name__ == "CORSMiddleware")
    assert cors.kwargs["allow_origins"] == ["https://stratyconfig.pages.dev"]
    assert cors.kwargs["allow_methods"] == ["*"]
