import json
from pathlib import Path
from typing import Dict

CATALOG_ROOT = Path(
    r"H:\temp\simulador_totem\panoconfig360_cache\clients"
)

def load_catalog(tenant_key: str) -> Dict[str, dict]:
    catalog_path = (
        CATALOG_ROOT
        / tenant_key
        / "catalog"
        / f"{tenant_key}_catalog.json"
    )

    if not catalog_path.exists():
        raise FileNotFoundError(
            f"Catálogo não encontrado em: {catalog_path}"
        )

    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    return {item["id"]: item for item in data}
