from pathlib import Path


def _server_source() -> str:
    server_path = Path(__file__).resolve().parents[1] / "api" / "server.py"
    return server_path.read_text(encoding="utf-8")


def test_server_has_no_frontend_static_mounts():
    source = _server_source()
    assert "from fastapi.staticfiles import StaticFiles" not in source
    assert 'app.mount("/static"' not in source
    assert 'app.mount("/assets"' not in source
    assert 'app.mount("/",' not in source


def test_server_has_no_root_html_route_and_has_cloudflare_cors_default():
    source = _server_source()
    assert '@app.get("/")' not in source
    assert 'os.getenv("CORS_ORIGINS", "https://stratyconfig.pages.dev")' in source
    assert 'allow_methods=["*"]' in source
