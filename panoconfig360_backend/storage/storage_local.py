import os
import json
import logging
from pathlib import Path

ASSETS_ROOT = Path(__file__).resolve().parents[2] / "panoconfig360_cache"

logging.info(f"📁 Using local assets root: {ASSETS_ROOT}")


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
