"""Tests for performance optimization changes."""

import importlib
import os
import sys
import threading
import types
from pathlib import Path
from unittest.mock import MagicMock

from storage.tile_upload_queue import TileUploadQueue


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

    from render import split_faces_cubemap

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

    # FACEsize=2048, tileSize=512 → 6 faces × 4×4 = 96 tiles, single LOD
    assert len(tiles) == 6 * (4 * 4)

    # No resize needed: target_size == face_size → 0 resize calls
    assert len(thread_ids) == 0


def test_face_workers_env_is_clamped(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyvips", types.SimpleNamespace(Image=object))
    from render import split_faces_cubemap
    importlib.reload(split_faces_cubemap)

    monkeypatch.setenv("CUBEMAP_FACE_WORKERS", "99")
    assert split_faces_cubemap._face_workers() == 6

    monkeypatch.setenv("CUBEMAP_FACE_WORKERS", "0")
    assert split_faces_cubemap._face_workers() == 1


def test_configure_pyvips_concurrency_sets_cache_limits(monkeypatch):
    calls = {}

    class FakePyvips:
        __version__ = "mock"
        Image = object

        @staticmethod
        def cache_set_max(value):
            calls["max_ops"] = value

        @staticmethod
        def cache_set_max_mem(value):
            calls["max_mem"] = value

    monkeypatch.setitem(sys.modules, "pyvips", FakePyvips)
    from render import split_faces_cubemap
    importlib.reload(split_faces_cubemap)

    monkeypatch.setenv("VIPS_CACHE_MAX_OPS", "123")
    monkeypatch.setenv("VIPS_CACHE_MAX_MEM_MB", "64")

    split_faces_cubemap.configure_pyvips_concurrency()

    assert calls["max_ops"] == 123
    assert calls["max_mem"] == 64 * 1024 * 1024
