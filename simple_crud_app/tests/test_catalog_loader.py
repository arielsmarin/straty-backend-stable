import importlib
import json


def test_load_catalog_uses_env_root(tmp_path, monkeypatch):
    tenant_key = "tenant-01"
    catalog_root = tmp_path / "clients"
    catalog_dir = catalog_root / tenant_key / "catalog"
    catalog_dir.mkdir(parents=True)

    catalog_file = catalog_dir / f"{tenant_key}_catalog.json"
    catalog_file.write_text(
        json.dumps([{"id": "mat-01", "label": "Material"}]),
        encoding="utf-8",
    )

    monkeypatch.setenv("PANOCONFIG360_CATALOG_ROOT", str(catalog_root))

    from simple_crud_app.backend import catalog_loader

    catalog_loader = importlib.reload(catalog_loader)

    result = catalog_loader.load_catalog(tenant_key)

    assert "mat-01" in result
