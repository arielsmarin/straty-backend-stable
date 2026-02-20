import os
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ASSETS_ROOT = Path(__file__).resolve().parents[2] / "panoconfig360_cache"

logging.info(f"📁 Using local assets root: {ASSETS_ROOT}")
_append_lock = threading.Lock()


def _resolve_path(key: str) -> Path:
    path = ASSETS_ROOT / key
    return path


def exists(key: str) -> bool:
    path = _resolve_path(key)
    return path.exists()


def upload_file(file_path: str, key: str, content_type: str = "application/octet-stream"):
    dest = _resolve_path(key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _ = content_type  # Ignorado para armazenamento local, mas mantido para compatibilidade com interface

    try:
        with open(file_path, "rb") as src, open(dest, "wb") as dst:
            dst.write(src.read())

        logging.info(f"💾 Cached locally: {key}")
    except Exception as e:
        logging.error(f"❌ Failed to cache file {key}: {e}")
        raise


def download_file(key: str, dest_path: str):
    src = _resolve_path(key)
    if not src.exists():
        raise FileNotFoundError(f"Asset not found in local cache: {key}")

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    try:
        with open(src, "rb") as fsrc, open(dest_path, "wb") as fdst:
            fdst.write(fsrc.read())

        logging.info(f"📤 Copied from local cache: {key} -> {dest_path}")

    except Exception as e:
        logging.error(f"❌ Failed to copy {key}: {e}")
        raise


def upload_tiles_parallel(
    tiles: list[tuple[str, bytes]],
    content_type: str = "image/jpeg",
    max_workers: int = 25,
    on_tile_uploaded=None,
):
    _ = content_type
    max_workers = max(1, max_workers)

    def _write_tile(tile_key: str, tile_bytes: bytes):
        dest = _resolve_path(tile_key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as dst:
            dst.write(tile_bytes)
        if on_tile_uploaded is not None:
            on_tile_uploaded(tile_key)

    futures = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for tile_key, tile_bytes in tiles:
            futures.append(executor.submit(_write_tile, tile_key, tile_bytes))
        for future in as_completed(futures):
            future.result()

    logging.info("💾 Upload paralelo local concluído: %s tiles", len(tiles))


def get_json(key: str) -> dict:
    path = _resolve_path(key)
    if not path.exists():
        raise FileNotFoundError(f"JSON not found in local cache: {key}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logging.error(f"❌ Failed to read JSON {key}: {e}")
        raise
    return data


def append_jsonl(key: str, payload: dict):
    path = _resolve_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)

    line = json.dumps(payload, ensure_ascii=False)
    with _append_lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def read_jsonl_slice(key: str, cursor: int = 0, limit: int = 200) -> tuple[list[dict], int]:
    path = _resolve_path(key)
    if not path.exists():
        return [], cursor

    events: list[dict] = []
    next_cursor = cursor

    with open(path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if idx < cursor:
                continue

            line = line.strip()
            if not line:
                continue

            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                logging.warning("⚠️ Linha inválida em jsonl: %s", key)

            next_cursor = idx + 1
            if len(events) >= limit:
                break

    return events, next_cursor
