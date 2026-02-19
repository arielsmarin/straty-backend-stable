import json
import os
from pathlib import Path
from typing import Dict

DEFAULT_CATALOG_ROOT = (
    Path(__file__).resolve().parents[3]
    / "panoconfig360_cache"
    / "clients"
)
CATALOG_ROOT = Path(
    os.getenv("PANOCONFIG360_CATALOG_ROOT") or DEFAULT_CATALOG_ROOT
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
