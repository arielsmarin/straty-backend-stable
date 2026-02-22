import gc
import logging
import multiprocessing
import os
import shutil
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

import pyvips

from render.vips_compat import VipsImageCompat, ensure_rgb8

STRIP_FACES = ["px", "nx", "py", "ny", "pz", "nz"]
logger = logging.getLogger(__name__)
_PYVIPS_CONCURRENCY_CONFIGURED = False
_PYVIPS_CONCURRENCY_LOCK = threading.Lock()

# 4 CPUs × 100 000 µs per 100 ms period
_MIN_RECOMMENDED_CPU_QUOTA = 4 * 100_000
# Upper-bound for libvips thread-pool when auto-detecting
_MAX_DEFAULT_CONCURRENCY = 4

MARZIPANO_FACE_MAP = {
    "px": "r",
    "nx": "l",
    "py": "u",
    "ny": "d",
    "pz": "f",
    "nz": "b",
}

LOD_CONFIGS = [
    (1024, 512),  # LOD 0: face 1024, tile 512, 2×2 grid
    (2048, 512),  # LOD 1: face 2048, tile 512, 4×4 grid
]


def _face_workers() -> int:
    configured = os.getenv("CUBEMAP_FACE_WORKERS")
    if configured is None:
        return max(2, min(6, os.cpu_count() or 2))
    return max(1, min(6, int(configured)))


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


def _log_cgroup_cpu_limit() -> None:
    """Log the container CPU quota from cgroup v2 (if available)."""
    try:
        with open("/sys/fs/cgroup/cpu.max", "r") as f:
            raw = f.read().strip()
        logger.info("cgroup cpu.max: %s", raw)
        parts = raw.split()
        if len(parts) == 2 and parts[0] != "max":
            quota = int(parts[0])
            if quota < _MIN_RECOMMENDED_CPU_QUOTA:
                logger.warning(
                    "Container CPU quota %d < 400000 — fewer than 4 effective CPUs",
                    quota,
                )
    except FileNotFoundError:
        logger.info("cgroup cpu.max not available (not running in a container?)")
    except Exception:
        logger.debug("Could not read cgroup cpu.max", exc_info=True)


def configure_pyvips_concurrency(limit: int = 0) -> None:
    """Configure libvips concurrency explicitly; limit=0 lets libvips use all cores."""
    global _PYVIPS_CONCURRENCY_CONFIGURED
    with _PYVIPS_CONCURRENCY_LOCK:
        if _PYVIPS_CONCURRENCY_CONFIGURED:
            return

        cpu_count = multiprocessing.cpu_count()
        logger.info("CPU count: %d", cpu_count)
        logger.info("PID: %d", os.getpid())
        _log_cgroup_cpu_limit()

        logger.info("pyvips version detected: %s", getattr(pyvips, "__version__", "unknown"))
        os.environ.setdefault("VIPS_CONCURRENCY", str(limit))

        # Explicitly set libvips thread concurrency so it takes effect even if
        # the library was already initialised before the env-var was written.
        concurrency_value = int(os.environ["VIPS_CONCURRENCY"])
        if concurrency_value == 0:
            concurrency_value = min(_MAX_DEFAULT_CONCURRENCY, cpu_count)
        if hasattr(pyvips, "concurrency_set"):
            pyvips.concurrency_set(concurrency_value)

        effective = pyvips.concurrency_get() if hasattr(pyvips, "concurrency_get") else "unknown"
        logger.info(
            "VIPS concurrency: env=%s effective=%s",
            os.environ["VIPS_CONCURRENCY"],
            effective,
        )

        max_ops = int(os.getenv("VIPS_CACHE_MAX_OPS", "200"))
        max_mem_mb = int(os.getenv("VIPS_CACHE_MAX_MEM_MB", "256"))
        if hasattr(pyvips, "cache_set_max"):
            pyvips.cache_set_max(max_ops)
        if hasattr(pyvips, "cache_set_max_mem"):
            pyvips.cache_set_max_mem(max_mem_mb * 1024 * 1024)
        logger.info(
            "Configured libvips cache: max_ops=%s max_mem_mb=%s",
            max_ops,
            max_mem_mb,
        )
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
            suffix=".jpg[Q=85,strip=true,optimize_coding=true]",
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

    # Fixed two-level LOD: LOD0 1024/512 (2×2), LOD1 2048/512 (4×4)
    # Total per face: 4 + 16 = 20 tiles; total per cubemap: 120 tiles
    lod_sizes = LOD_CONFIGS

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

            resized = face_img if _scale == 1.0 else _resize_face_for_lod(face_img, _scale)

            with tempfile.TemporaryDirectory() as tmp_dir:

                dz_prefix = str(Path(tmp_dir) / "face")

                resized.dzsave(
                    dz_prefix,
                    tile_size=_lod_tile_size,
                    overlap=0,
                    depth="one",
                    suffix=".jpg[Q=85,strip=true,optimize_coding=true]",
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
        with ThreadPoolExecutor(max_workers=_face_workers()) as pool:
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
            extract_start = time.monotonic()
            tile = resized.crop(x * lod_tile_size, y * lod_tile_size, lod_tile_size, lod_tile_size)
            extract_ms = (time.monotonic() - extract_start) * 1000

            encode_start = time.monotonic()
            tile_bytes = tile.write_to_buffer(
                ".jpg",
                Q=jpeg_quality,
                strip=True,
                optimize_coding=True,
            )
            encode_ms = (time.monotonic() - encode_start) * 1000

            filename = f"{build}_{marzipano_face}_{lod}_{x}_{y}.jpg"
            face_tiles.append((filename, tile_bytes, lod))
            logger.debug(
                "TILE face=%s level=%d x=%d y=%d extract=%.0fms jpeg=%.0fms",
                marzipano_face, lod, x, y, extract_ms, encode_ms,
            )

    del resized
    return face_tiles, resize_elapsed


def process_cubemap_to_memory(
    input_image,
    tile_size: int = 512,
    build: str = "unknown",
    max_lod: Optional[int] = None,
    min_lod: int = 0,
    jpeg_quality: int = 85,
):
    split_start = time.monotonic()
    cubemap_img = normalize_to_horizontal_cubemap(input_image)
    cubemap_img = ensure_rgb8(cubemap_img)

    face_size = cubemap_img.height
    if cubemap_img.width != face_size * 6:
        raise ValueError("Cubemap horizontal inválido")

    # Fixed two-level LOD: LOD0 1024/512 (2×2), LOD1 2048/512 (4×4)
    # Total per face: 4 + 16 = 20 tiles; total per cubemap: 120 tiles
    lod_sizes = LOD_CONFIGS
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

        with ThreadPoolExecutor(max_workers=_face_workers()) as pool:
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
