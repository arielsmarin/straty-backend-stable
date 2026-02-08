import os
import json
import logging
from pathlib import Path
from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# ======================================================
# 🔧 CONSTANTES
# ======================================================
CONFIG_STRING_BASE = 36
FIXED_LAYERS = 5
SCENE_CHARS = 2
LAYER_CHARS = 2
BUILD_TOTAL = SCENE_CHARS + FIXED_LAYERS * LAYER_CHARS


def get_build_chars() -> int:
    if CONFIG_STRING_BASE == 16:
        return 2
    elif CONFIG_STRING_BASE == 336:
        return 3
    return 2


def get_actual_base() -> int:
    return 36 if CONFIG_STRING_BASE == 336 else CONFIG_STRING_BASE


# ======================================================
# 📦 CONFIG LOADER
# ======================================================

def load_config(config_path):
    if isinstance(config_path, Path):
        config_path = str(config_path)

    if config_path.startswith("http"):
        raise RuntimeError("Config remoto não permitido em modo offline")

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config não encontrado: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    scenes = config.get("scenes")

    if not scenes:
        scenes = {
            "default": {
                "scene_index": 0,
                "layers": config.get("layers", []),
                "base_image": config.get("base_image"),
            }
        }

    naming = config.get("naming", {})
    return config, scenes, naming


# ======================================================
# 🔢 ENCODE / DECODE
# ======================================================

def base36_encode(num: int, width: int = 2) -> str:
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    result = ""
    n = num
    while n:
        n, i = divmod(n, 36)
        result = chars[i] + result
    return (result or "0").zfill(width)


def base36_decode(s: str) -> int:
    return int(s.lower(), 36)


def hex_encode(num: int, width: int = 2) -> str:
    return format(num, f"0{width}x")


def hex_decode(s: str) -> int:
    return int(s, 16)


def encode_index(index: int) -> str:
    chars = get_build_chars()
    base = get_actual_base()
    if base == 16:
        return hex_encode(index, chars)
    return base36_encode(index, chars)


def decode_index(s: str) -> int:
    base = get_actual_base()
    if base == 16:
        return hex_decode(s)
    return base36_decode(s)


# ======================================================
# 🔢 BUILD STRING
# ======================================================

def build_string_from_selection(scene_index: int, layers: list, selection: dict) -> str:
    parts = [base36_encode(scene_index, SCENE_CHARS)]

    layer_values = [0] * FIXED_LAYERS

    for layer in layers:
        build_order = layer.get("build_order", 0)

        if build_order < 0 or build_order >= FIXED_LAYERS:
            continue

        layer_id = layer["id"]
        selected_id = selection.get(layer_id)

        if not selected_id:
            continue

        item = next(
            (it for it in layer.get("items", []) if it["id"] == selected_id),
            None
        )

        if not item:
            continue

        layer_values[build_order] = item.get("index", 0)

    for v in layer_values:
        parts.append(base36_encode(v, LAYER_CHARS))

    return "".join(parts)


# ======================================================
# 🧩 STACK DE IMAGENS
# ======================================================

def stack_layers_image_only(
    scene_id: str,
    layers: list,
    selection: dict,
    assets_root: Path,
) -> Image.Image:
    """
    Empilha base + overlays.
    Retorna APENAS a imagem PIL.
    """
    base_image_name = f"base_{scene_id}.jpg"
    base_path = assets_root / base_image_name

    if not base_path.exists():
        raise FileNotFoundError(f"Imagem base não encontrada: {base_path}")

    missing_overlays = []

    # Abre e mantém referência fora do with
    base = Image.open(base_path).convert("RGBA")

    for layer in sorted(layers, key=lambda x: x.get("build_order", 0)):
        layer_id = layer["id"]
        item_id = selection.get(layer_id)

        if not item_id:
            continue

        item = next(
            (it for it in layer.get("items", []) if it["id"] == item_id),
            None
        )

        if not item:
            continue

        if item.get("file") is None:
            continue

        file_name = f"{layer_id}_{item_id}.png"
        overlay_path = assets_root / "layers" / layer_id / file_name

        if not overlay_path.exists():
            missing_overlays.append((layer_id, file_name))
            continue

        overlay = Image.open(overlay_path).convert("RGBA")
        base.alpha_composite(overlay)
        overlay.close()

    if missing_overlays:
        logging.warning(
            f"⚠️ Overlays ausentes (ignorados): {missing_overlays}")

    logging.info(f"✅ Stack de imagem gerado: {base.size}")
    return base.convert("RGB")
