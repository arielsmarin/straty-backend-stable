import gc
import logging
import os
import shutil
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

import pyvips

from panoconfig360_backend.render.vips_compat import VipsImageCompat, ensure_rgb8

STRIP_FACES = ["px", "nx", "py", "ny", "pz", "nz"]
logger = logging.getLogger(__name__)
_PYVIPS_CONCURRENCY_CONFIGURED = False
_PYVIPS_CONCURRENCY_LOCK = threading.Lock()

MARZIPANO_FACE_MAP = {
    "px": "r",
    "nx": "l",
    "py": "u",
    "ny": "d",
    "pz": "f",
    "nz": "b",
}


def _to_vips_image(img) -> pyvips.Image:
    if isinstance(img, VipsImageCompat):
        return img.image
    if isinstance(img, pyvips.Image):
        return img
    raise TypeError("Formato de imagem inválido para processamento de cubemap")


def normalize_to_horizontal_cubemap(img):
    return _to_vips_image(img).flip("horizontal")


def _resize_face_for_lod(face_img: pyvips.Image, scale: float) -> pyvips.Image:
    return face_img.resize(scale, kernel="linear")


def configure_pyvips_concurrency(limit: int = 0) -> None:
    """Configure libvips via VIPS_CONCURRENCY when unset; limit=0 lets libvips use all cores."""
    global _PYVIPS_CONCURRENCY_CONFIGURED
    with _PYVIPS_CONCURRENCY_LOCK:
        if _PYVIPS_CONCURRENCY_CONFIGURED:
            return

        logger.info("pyvips version detected: %s", getattr(pyvips, "__version__", "unknown"))
        os.environ.setdefault("VIPS_CONCURRENCY", str(limit))
        logger.info("Configured libvips concurrency via VIPS_CONCURRENCY=%s", os.environ["VIPS_CONCURRENCY"])
        _PYVIPS_CONCURRENCY_CONFIGURED = True


def split_faces_from_image(cubemap_img, output_base_dir: str, tile_size: int, level: int, build: str):
    output_base_dir = str(output_base_dir)

    width = cubemap_img.width
    height = cubemap_img.height
    face_size = height

    if width != face_size * 6:
        raise ValueError("Cubemap horizontal inválido")

    for i, face_key in enumerate(STRIP_FACES):
        left = i * face_size
        face_img = cubemap_img.extract_area(left, 0, face_size, face_size)

        if face_key == "py":
            face_img = face_img.rot270()
            marzipano_face = MARZIPANO_FACE_MAP["ny"]
        elif face_key == "ny":
            face_img = face_img.rot90()
            marzipano_face = MARZIPANO_FACE_MAP["py"]
        else:
            marzipano_face = MARZIPANO_FACE_MAP[face_key]

        _generate_tiles(face_img, output_base_dir,
                        marzipano_face, tile_size, level, build)


def _generate_tiles(face_img: pyvips.Image, out_dir: str, face: str, tile_size: int, lod: int, build: str):
    width = face_img.width
    height = face_img.height
    if width % tile_size != 0 or height % tile_size != 0:
        raise ValueError("Face não é múltipla do tile_size")

    with tempfile.TemporaryDirectory() as tmp_dir:
        dz_prefix = str(Path(tmp_dir) / "face")
        ensure_rgb8(face_img).dzsave(
            dz_prefix,
            tile_size=tile_size,
            overlap=0,
            depth="one",
            suffix=".jpg[Q=70,strip=true]",
            container="fs",
        )

        tiles_root = Path(f"{dz_prefix}_files") / "0"
        for tile in tiles_root.glob("*.jpg"):
            stem = tile.stem
            x_str, y_str = stem.split("_")
            filename = f"{build}_{face}_{lod}_{x_str}_{y_str}.jpg"
            shutil.move(str(tile), os.path.join(out_dir, filename))


def process_cubemap(
    input_image,
    output_base_dir,
    tile_size=512,
    build="unknown",
    max_lod: Optional[int] = None,
    min_lod: int = 0,
    on_tile_ready: Optional[Callable[[Path, str, int], None]] = None,
):
    output_base_dir = Path(output_base_dir)
    output_base_dir.mkdir(parents=True, exist_ok=True)

    cubemap_img = normalize_to_horizontal_cubemap(input_image)
    cubemap_img = ensure_rgb8(cubemap_img)

    face_size = cubemap_img.height

    if cubemap_img.width != face_size * 6:
        raise ValueError("Cubemap horizontal inválido")

    # LODs EXATOS esperados pelo frontend
    # Cada entrada é (lod_face_size, lod_tile_size):
    #   lod0: face=512,  tile=256  -> { tileSize: 256, size: 512, fallbackOnly: true }
    #   lod1: face=1024, tile=512  -> { tileSize: 512, size: 1024 }
    lod_sizes = []
    # lod0: face=tile_size, tile=tile_size//2
    if tile_size <= face_size:
        lod_sizes.append((tile_size, tile_size // 2))
    # lod1: face dobra uma vez, tile permanece tile_size
    if tile_size * 2 <= face_size:
        lod_sizes.append((tile_size * 2, tile_size))

    if not lod_sizes:
        raise ValueError("Nenhum LOD válido foi calculado para o cubemap")

    if min_lod < 0:
        raise ValueError("min_lod deve ser >= 0")

    final_lod = len(lod_sizes) - 1 if max_lod is None else max_lod
    if final_lod < min_lod:
        return

    final_lod = min(final_lod, len(lod_sizes) - 1)

    # Extrair faces uma única vez
    faces = []

    for i, face_key in enumerate(STRIP_FACES):
        left = i * face_size
        face_img = cubemap_img.extract_area(left, 0, face_size, face_size)

        if face_key == "py":
            face_img = face_img.rot270()
            marzipano_face = MARZIPANO_FACE_MAP["ny"]
        elif face_key == "ny":
            face_img = face_img.rot90()
            marzipano_face = MARZIPANO_FACE_MAP["py"]
        else:
            marzipano_face = MARZIPANO_FACE_MAP[face_key]

        faces.append((face_img, marzipano_face))

    # Gerar LOD controlado
    for lod, (target_size, lod_tile_size) in enumerate(lod_sizes):
        if lod < min_lod or lod > final_lod:
            continue

        scale = target_size / face_size

        def _process_face(face_data, _scale=scale, _lod=lod, _lod_tile_size=lod_tile_size):
            face_img, marzipano_face = face_data

            resized = _resize_face_for_lod(face_img, scale)

            with tempfile.TemporaryDirectory() as tmp_dir:

                dz_prefix = str(Path(tmp_dir) / "face")

                resized.dzsave(
                    dz_prefix,
                    tile_size=_lod_tile_size,
                    overlap=0,
                    depth="one",
                    suffix=".jpg[Q=70,strip=true]",
                    container="fs",
                )

                tiles_root = Path(f"{dz_prefix}_files") / "0"

                for tile in tiles_root.glob("*.jpg"):
                    stem = tile.stem
                    x_str, y_str = stem.split("_")

                    filename = (
                        f"{build}_{marzipano_face}_"
                        f"{_lod}_{x_str}_{y_str}.jpg"
                    )

                    shutil.move(
                        str(tile),
                        str(output_base_dir / filename)
                    )

                    if on_tile_ready is not None:
                        on_tile_ready(output_base_dir /
                                      filename, filename, _lod)

            del resized

        # Process faces concurrently — libvips releases the GIL
        with ThreadPoolExecutor(max_workers=min(6, os.cpu_count() or 2)) as pool:
            list(pool.map(_process_face, faces))

        # Free memory after each LOD level
        gc.collect()


def _process_face_to_tiles(
    face_data: tuple,
    lod: int,
    target_size: int,
    face_size: int,
    lod_tile_size: int,
    build: str,
    jpeg_quality: int,
) -> tuple[list[tuple[str, bytes, int]], float]:
    """Process a single cubemap face into in-memory tiles.

    Returns the tile list and the time spent resizing (for logging).
    pyvips releases the GIL, so this function is safe to run in threads.
    """
    face_img, marzipano_face = face_data
    face_tiles: list[tuple[str, bytes, int]] = []
    resize_elapsed = 0.0

    resized = face_img
    if target_size != face_size:
        resize_start = time.monotonic()
        resized = _resize_face_for_lod(face_img, target_size / face_size)
        resize_elapsed = time.monotonic() - resize_start

    cols = target_size // lod_tile_size
    rows = target_size // lod_tile_size

    for x in range(cols):
        for y in range(rows):
            tile = resized.crop(x * lod_tile_size, y * lod_tile_size, lod_tile_size, lod_tile_size)
            tile_bytes = tile.write_to_buffer(
                ".jpg",
                Q=jpeg_quality,
                strip=True,
                optimize_coding=False,
            )
            filename = f"{build}_{marzipano_face}_{lod}_{x}_{y}.jpg"
            face_tiles.append((filename, tile_bytes, lod))

    del resized
    return face_tiles, resize_elapsed


def process_cubemap_to_memory(
    input_image,
    tile_size: int = 512,
    build: str = "unknown",
    max_lod: Optional[int] = None,
    min_lod: int = 0,
    jpeg_quality: int = 72,
):
    split_start = time.monotonic()
    cubemap_img = normalize_to_horizontal_cubemap(input_image)
    cubemap_img = ensure_rgb8(cubemap_img)

    face_size = cubemap_img.height
    if cubemap_img.width != face_size * 6:
        raise ValueError("Cubemap horizontal inválido")

    lod_sizes = []
    if tile_size * 2 <= face_size:
        lod_sizes.append((face_size // 2, tile_size))
    if tile_size <= face_size:
        lod_sizes.append((face_size, tile_size))
    if not lod_sizes:
        raise ValueError("Nenhum LOD válido foi calculado para o cubemap")
    if min_lod < 0:
        raise ValueError("min_lod deve ser >= 0")

    final_lod = len(lod_sizes) - 1 if max_lod is None else min(max_lod, len(lod_sizes) - 1)
    if final_lod < min_lod:
        return []

    faces = []
    for i, face_key in enumerate(STRIP_FACES):
        left = i * face_size
        face_img = cubemap_img.extract_area(left, 0, face_size, face_size)
        if face_key == "py":
            face_img = face_img.rot270()
            marzipano_face = MARZIPANO_FACE_MAP["ny"]
        elif face_key == "ny":
            face_img = face_img.rot90()
            marzipano_face = MARZIPANO_FACE_MAP["py"]
        else:
            marzipano_face = MARZIPANO_FACE_MAP[face_key]
        faces.append((face_img, marzipano_face))
    logger.info("Tempo split faces: %.2fs", time.monotonic() - split_start)

    tiles: list[tuple[str, bytes, int]] = []
    resize_lod0_elapsed = 0.0
    extraction_start = time.monotonic()
    for lod, (target_size, lod_tile_size) in enumerate(lod_sizes):
        if lod < min_lod or lod > final_lod:
            continue

        # Process all 6 faces concurrently — pyvips releases the GIL so threads
        # achieve real CPU-bound parallelism across all available cores.
        def _do_face(face_data, _lod=lod, _target=target_size, _tile_sz=lod_tile_size):
            return _process_face_to_tiles(
                face_data, _lod, _target, face_size, _tile_sz, build, jpeg_quality
            )

        with ThreadPoolExecutor(max_workers=min(6, os.cpu_count() or 2)) as pool:
            results = list(pool.map(_do_face, faces))

        for face_tiles, elapsed in results:
            tiles.extend(face_tiles)
            resize_lod0_elapsed += elapsed

        gc.collect()
    logger.info("Tempo resize LOD0: %.2fs", resize_lod0_elapsed)
    logger.info("Tempo tile extraction total: %.2fs", time.monotonic() - extraction_start)

    return tiles


""" def process_cubemap(
    input_image,
    output_base_dir: Path | str,
    tile_size: int = 512,
    build: str = "unknown"
):
    cubemap_img = normalize_to_horizontal_cubemap(input_image)

    face_size = cubemap_img.height

    if cubemap_img.width != face_size * 6:
        raise ValueError("Cubemap horizontal inválido")

    current_size = tile_size
    lod = 0

    while current_size <= face_size:
        scale = current_size / face_size

        resized = cubemap_img.resize(scale)

        split_faces_from_image(
            resized,
            output_base_dir,
            tile_size,
            lod,
            build
        )

        current_size *= 2
        lod += 1 """
