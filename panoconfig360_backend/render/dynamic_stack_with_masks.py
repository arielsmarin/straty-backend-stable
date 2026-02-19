import os
import json
import logging
from pathlib import Path
from panoconfig360_backend.render.vips_compat import resolve_asset, construct_r2_url

import pyvips

from panoconfig360_backend.render.vips_compat import (
    VipsImageCompat,
    blend_with_mask,
    ensure_rgb8,
    load_rgb_image,
    resize_to_match,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

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
            None,
        )

        if not item:
            continue

        index = item.get("index", 0)
        config[build_order] = encode_index(index)

    return "".join(config)


def _load_mask(path: Path) -> pyvips.Image:
    mask = pyvips.Image.new_from_file(str(path), access="random")
    if mask.bands > 1:
        mask = mask.colourspace("b-w")
    return mask.cast("uchar")


def stack_layers_image_only(
    scene_id: str,
    layers: list,
    selection: dict,
    assets_root: Path,
    asset_prefix: str = "",
):
    base_candidates = [
        assets_root / f"{asset_prefix}base_{scene_id}.jpg",
        assets_root / f"{asset_prefix}base_{scene_id}.png",
    ]

    base_base = assets_root / f"{asset_prefix}base_{scene_id}"

    try:
        base_path = resolve_asset(base_base)
    except FileNotFoundError as e:
        # Construct expected remote URL for debugging
        remote_example = construct_r2_url(base_base, ".jpg")
        
        raise FileNotFoundError(
            "❌ Base 2D não encontrada\n"
            f"• Scene: {scene_id}\n"
            f"• Asset prefix: '{asset_prefix or '(none)'}'\n"
            f"• Base esperada (local): {base_base}.(png|jpg|jpeg)\n"
            f"• Remote URL esperada: {remote_example}\n"
            f"• Erro original: {str(e)}\n"
            "👉 Ação: verifique se o arquivo existe no R2 storage ou localmente."
        )

    result = load_rgb_image(base_path)
    missing_assets = []

    for layer in sorted(layers, key=lambda x: x.get("build_order", 0)):
        layer_id = layer["id"]
        item_id = selection.get(layer_id)

        if not item_id:
            continue

        item = next(
            (it for it in layer.get("items", []) if it["id"] == item_id),
            None,
        )

        if not item:
            continue

        material_file = item.get("file")
        mask_file = layer.get("mask")

        if not material_file or not mask_file:
            continue

        material_base = assets_root / "materials" / \
            f"{asset_prefix}{material_file}"
        mask_base = assets_root / "masks" / f"{asset_prefix}{mask_file}"

        try:
            material_path = resolve_asset(material_base)
            mask_path = resolve_asset(mask_base)
        except FileNotFoundError:
            missing_assets.append((layer_id, material_file, mask_file))
            continue

        material = resize_to_match(
            load_rgb_image(material_path),
            result.width,
            result.height,
        )

        mask = resize_to_match(
            _load_mask(mask_path),
            result.width,
            result.height,
        )

        result = blend_with_mask(result, material, mask)
        logging.info(f"🎨 Layer {asset_prefix}{layer_id} → {item_id}")

    if missing_assets:
        logging.warning(f"⚠️ Assets ausentes (ignorados): {missing_assets}")

    logging.info("✅ Stack com masks gerado")
    return VipsImageCompat(ensure_rgb8(result))
