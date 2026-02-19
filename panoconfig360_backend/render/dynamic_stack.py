import os
import json
import logging
from pathlib import Path
from panoconfig360_backend.render.vips_compat import resolve_asset
import pyvips

from panoconfig360_backend.render.vips_compat import (
    VipsImageCompat,
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


def _validate_config(config: dict) -> None:
    if not isinstance(config, dict):
        raise ValueError("Config inválido: esperado um objeto.")

    scenes = config.get("scenes")
    layers = config.get("layers")

    if scenes:
        if not isinstance(scenes, dict):
            raise ValueError("Config inválido: 'scenes' deve ser um objeto.")

        for scene_id, scene in scenes.items():
            if not isinstance(scene, dict):
                raise ValueError(
                    f"Config inválido: cena '{scene_id}' deve ser objeto."
                )

            scene_layers = scene.get("layers")
            if scene_layers is None:
                raise ValueError(
                    f"Config inválido: cena '{scene_id}' sem layers."
                )

            if not isinstance(scene_layers, list):
                raise ValueError(
                    f"Config inválido: layers da cena '{scene_id}' deve ser lista."
                )

            for layer in scene_layers:
                if not isinstance(layer, dict) or not layer.get("id"):
                    raise ValueError(
                        f"Config inválido: layer inválido na cena '{scene_id}'."
                    )

                items = layer.get("items", [])
                if items is not None and not isinstance(items, list):
                    raise ValueError(
                        "Config inválido: items do layer "
                        f"'{layer.get('id', '?')}' deve ser lista."
                    )
    elif layers is None:
        raise ValueError(
            "Config inválido: 'scenes' ou 'layers' é obrigatório."
        )
    elif not isinstance(layers, list):
        raise ValueError("Config inválido: 'layers' deve ser uma lista.")


def load_config(config_path):
    if isinstance(config_path, Path):
        config_path = str(config_path)

    if config_path.startswith("http"):
        raise RuntimeError("Config remoto não permitido em modo offline")

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config não encontrado: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        try:
            config = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Config JSON inválido em {config_path}: {exc}"
            ) from exc

    _validate_config(config)

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

        item = next((it for it in layer.get("items", [])
                    if it["id"] == selected_id), None)

        if not item:
            continue

        layer_values[build_order] = item.get("index", 0)

    for v in layer_values:
        parts.append(base36_encode(v, LAYER_CHARS))

    return "".join(parts)


def _load_overlay_with_alpha(path: Path) -> pyvips.Image:
    img = pyvips.Image.new_from_file(str(path), access="random")
    if img.bands == 1:
        img = img.bandjoin([img, img]).bandjoin_const(255)
    elif img.bands == 2:
        gray = img.extract_band(0)
        alpha = img.extract_band(1)
        img = gray.bandjoin([gray, gray, alpha])
    elif img.bands == 3:
        img = img.bandjoin_const(255)
    else:
        img = img.extract_band(0, n=4)
    return img.cast("uchar")


def stack_layers_image_only(
    scene_id: str,
    layers: list,
    selection: dict,
    assets_root: Path,
):
    base_image_name = f"base_{scene_id}.jpg"
    base_path = assets_root / base_image_name

    if not base_path.exists():
        raise FileNotFoundError(f"Imagem base não encontrada: {base_path}")

    missing_overlays = []
    base = load_rgb_image(base_path)

    for layer in sorted(layers, key=lambda x: x.get("build_order", 0)):
        layer_id = layer["id"]
        item_id = selection.get(layer_id)

        if not item_id:
            continue

        item = next((it for it in layer.get("items", [])
                    if it["id"] == item_id), None)

        if not item:
            continue

        if item.get("file") is None:
            continue

        file_name = f"{layer_id}_{item_id}"
        overlay_base = assets_root / "layers" / layer_id / file_name
        overlay_path = resolve_asset(overlay_base)

        if not overlay_path.exists():
            missing_overlays.append((layer_id, file_name))
            continue

        overlay = resize_to_match(_load_overlay_with_alpha(
            overlay_path), base.width, base.height)
        base_rgba = base.bandjoin_const(255)
        base = base_rgba.composite2(overlay, "over").extract_band(0, n=3)

    if missing_overlays:
        logging.warning(
            f"⚠️ Overlays ausentes (ignorados): {missing_overlays}")

    logging.info(f"✅ Stack de imagem gerado: {(base.width, base.height)}")
    return VipsImageCompat(ensure_rgb8(base))
