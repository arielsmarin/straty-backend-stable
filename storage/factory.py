"""
Storage backend factory.
Selects storage backend based on STORAGE_BACKEND environment variable.

Environment variables:
- STORAGE_BACKEND: "local" (default) or "r2"
"""
import os
import logging

STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "https://pub-4503b4acd02140cfb69ab3886530d45b.r2.dev")

logging.info(f"📂 Storage backend: {STORAGE_BACKEND}")

if STORAGE_BACKEND == "r2":
    try:
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
    except Exception as e:
        logging.error(f"❌ Failed to initialize R2 storage: {e}")
        logging.info("📂 Falling back to local storage")
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
else:
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
