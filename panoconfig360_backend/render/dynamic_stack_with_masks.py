import os
import json
import logging
from pathlib import Path
from PIL import Image
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# ======================================================
# 🔧 CONSTANTES (INALTERADAS)
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
# 📦 CONFIG LOADER (INALTERADO)
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
# 🔢 ENCODE / DECODE (INALTERADO)
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
# 🔢 BUILD STRING (INALTERADO)
# ======================================================

def build_string_from_selection(layers: list, selection: dict) -> str:
    config = [encode_index(0)] * FIXED_LAYERS

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

        index = item.get("index", 0)
        config[build_order] = encode_index(index)

    return "".join(config)


# ======================================================
# 🧠 UTIL DE COMPOSITE COM MASK
# ======================================================

def _load_rgb_np(path: Path):
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0


def _load_mask_np(path: Path):
    m = np.asarray(Image.open(path).convert("L"), dtype=np.float32) / 255.0
    return m[..., None]


def _composite_np(base, material, mask):
    return base * (1.0 - mask) + material * mask


# ======================================================
# 🧩 NOVO STACK COM MASKS (SUBSTITUI PNG OVERLAY)
# ======================================================

def stack_layers_image_only(
    scene_id: str,
    layers: list,
    selection: dict,
    assets_root: Path,
) -> Image.Image:
    """
    Novo stack:
    base + material full-frame * mask P&B por layer.
    Mantém assinatura e retorno do método antigo.
    """

    base_image_name = f"base_{scene_id}.png"
    base_path = assets_root / base_image_name

    if not base_path.exists():
        raise FileNotFoundError(f"Imagem base não encontrada: {base_path}")

    # base em NumPy float
    result = _load_rgb_np(base_path)

    missing_assets = []

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

        material_file = item.get("file")
        mask_file = layer.get("mask")

        if not material_file or not mask_file:
            continue

        material_path = assets_root / "materials" / material_file
        mask_path = assets_root / "masks" / mask_file

        if not material_path.exists() or not mask_path.exists():
            missing_assets.append((layer_id, material_file, mask_file))
            continue

        material = _load_rgb_np(material_path)
        mask = _load_mask_np(mask_path)

        result = _composite_np(result, material, mask)

    if missing_assets:
        logging.warning(f"⚠️ Assets ausentes (ignorados): {missing_assets}")

    logging.info("✅ Stack com masks gerado")

    return Image.fromarray((result * 255).astype("uint8"))
