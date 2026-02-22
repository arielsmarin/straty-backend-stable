"""
Storage backend factory.
Selects storage backend based on STORAGE_BACKEND environment variable.

Environment variables:
- STORAGE_BACKEND: "r2" (default) or "local"
"""
import os
import logging

STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "r2")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "https://pub-4503b4acd02140cfb69ab3886530d45b.r2.dev")

logging.info(f"📂 Storage backend: {STORAGE_BACKEND}")

if STORAGE_BACKEND == "r2":
    from storage.storage_r2 import (
        exists,
        upload_file,
        download_file,
        get_json,
        append_jsonl,
        read_jsonl_slice,
        get_public_url,
        upload_tiles_parallel,
    )
    logging.info("✅ Using R2 storage backend")
elif STORAGE_BACKEND == "local":
    from storage.storage_local import (
        exists,
        upload_file,
        download_file,
        get_json,
        append_jsonl,
        read_jsonl_slice,
        upload_tiles_parallel,
    )

    def get_public_url(key: str) -> str:
        """Return R2 public URL even when using local storage."""
        return f"{R2_PUBLIC_URL}/{key}"

    logging.info("📁 Using local storage backend (staging only)")
else:
    raise ValueError(
        f"Invalid STORAGE_BACKEND: {STORAGE_BACKEND!r}. "
        "Set the STORAGE_BACKEND environment variable to 'r2' or 'local'."
    )

__all__ = [
    "exists",
    "upload_file",
    "download_file",
    "get_json",
    "append_jsonl",
    "read_jsonl_slice",
    "get_public_url",
    "upload_tiles_parallel",
]
