from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]

ASSETS_ROOT = ROOT_DIR / "assets"


def resolve_2d_base() -> str:
    path = ASSETS_ROOT / "2d_base_baccarat.jpg"
    if not path.exists():
        raise FileNotFoundError(f"Base 2D não encontrada: {path}")
    return str(path)


def resolve_2d_overlay(layer_id: str, filename: str) -> str:
    path = ASSETS_ROOT / "layers" / layer_id / filename

    if not path.exists():
        raise FileNotFoundError(f"Overlay 2D não encontrado: {path}")

    return str(path)
