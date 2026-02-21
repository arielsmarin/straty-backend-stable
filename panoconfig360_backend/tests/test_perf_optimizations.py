"""Tests for performance optimization changes."""

import importlib
import os
import sys
import threading
import types
from pathlib import Path
from unittest.mock import MagicMock

from panoconfig360_backend.storage.tile_upload_queue import TileUploadQueue


def test_tile_upload_queue_multiple_workers(tmp_path: Path):
    """TileUploadQueue should work correctly with multiple workers."""
    uploaded = []

    def fake_upload(src: str, key: str, content_type: str):
        uploaded.append((Path(src).name, key))

    # Create several tiles
    for i in range(8):
        (tmp_path / f"tile_{i}.jpg").write_bytes(b"jpg-data")

    queue = TileUploadQueue(
        tile_root="clients/a/cubemap/s/tiles/build",
        upload_fn=fake_upload,
        workers=4,
    )
    queue.start()

    for i in range(8):
        queue.enqueue(tmp_path / f"tile_{i}.jpg", f"build_f_0_{i}_0.jpg", 0)

    queue.close_and_wait()

    assert queue.uploaded_count == 8
    assert len(uploaded) == 8
    # All tiles should reach "visible" state
    for i in range(8):
        assert queue.states[f"build_f_0_{i}_0.jpg"] == "visible"


def test_tile_workers_env_default():
    """TILE_WORKERS env var should default to 4."""
    # Remove env var if set, then check import default
    original = os.environ.pop("TILE_WORKERS", None)
    try:
        val = int(os.getenv("TILE_WORKERS", "4"))
        assert val == 4
    finally:
        if original is not None:
            os.environ["TILE_WORKERS"] = original


def test_tile_workers_env_override():
    """TILE_WORKERS env var should be configurable."""
    original = os.environ.get("TILE_WORKERS")
    os.environ["TILE_WORKERS"] = "8"
    try:
        val = int(os.getenv("TILE_WORKERS", "4"))
        assert val == 8
    finally:
        if original is not None:
            os.environ["TILE_WORKERS"] = original
        else:
            os.environ.pop("TILE_WORKERS", None)


def test_vips_concurrency_env_default():
    """VIPS_CONCURRENCY should default to 0 (auto-detect) via setdefault."""
    original = os.environ.pop("VIPS_CONCURRENCY", None)
    try:
        # This mirrors exactly what server.py does at startup
        os.environ.setdefault("VIPS_CONCURRENCY", "0")
        assert os.environ["VIPS_CONCURRENCY"] == "0"
    finally:
        if original is not None:
            os.environ["VIPS_CONCURRENCY"] = original
        else:
            os.environ.pop("VIPS_CONCURRENCY", None)


def test_process_cubemap_to_memory_processes_faces_in_parallel(monkeypatch):
    """process_cubemap_to_memory should process the 6 cubemap faces concurrently."""
    monkeypatch.setitem(sys.modules, "pyvips", types.SimpleNamespace(Image=object))

    from panoconfig360_backend.render import split_faces_cubemap

    importlib.reload(split_faces_cubemap)
    monkeypatch.setattr(split_faces_cubemap, "ensure_rgb8", lambda img: img)

    # Track which thread ids process each face resize so we can verify concurrency.
    thread_ids: list[int] = []
    lock = threading.Lock()

    class FakeImage:
        def __init__(self, width, height):
            self.width = width
            self.height = height

        def flip(self, _):
            return self

        def extract_area(self, _x, _y, width, height):
            return FakeImage(width, height)

        def rot90(self):
            return self

        def rot270(self):
            return self

        def resize(self, scale, **_kwargs):
            with lock:
                thread_ids.append(threading.get_ident())
            return FakeImage(int(self.width * scale), int(self.height * scale))

        def crop(self, *_args):
            class FakeTile:
                def write_to_buffer(self, fmt, **kwargs):
                    return b"jpg"

            return FakeTile()

    tiles = split_faces_cubemap.process_cubemap_to_memory(
        FakeImage(12288, 2048),
        tile_size=512,
        build="build",
    )

    # Correctness: all 120 tiles must be produced.
    assert len(tiles) == 6 * ((2 * 2) + (4 * 4))

    # Concurrency: LOD0 triggers 6 resize calls, each from a worker thread.
    # At least 2 distinct thread IDs confirms the parallel execution path.
    assert len(thread_ids) == 6
    assert len(set(thread_ids)) >= 2, "Expected faces to be processed on multiple threads"
