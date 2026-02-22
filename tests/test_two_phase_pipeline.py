"""Tests for the two-phase render pipeline (generate-then-upload)."""
import sys
import threading
import types
from pathlib import Path

import pytest

# Stub pyvips so server.py can be imported without the native library installed.
sys.modules.setdefault(
    "pyvips", types.SimpleNamespace(Image=object, __version__="mock")
)


def _import_server():
    import importlib
    from api import server as _srv
    return importlib.reload(_srv)


def test_process_cubemap_called_with_no_on_tile_ready(tmp_path, monkeypatch):
    """Phase 1 must call process_cubemap with on_tile_ready=None so no upload
    occurs during tile generation."""
    server = _import_server()

    captured_on_tile_ready = []

    def fake_process_cubemap(stack_img, out_dir, tile_size, build, min_lod, max_lod, on_tile_ready):
        captured_on_tile_ready.append(on_tile_ready)
        # Simulate generating two tiles
        for i in range(2):
            (Path(out_dir) / f"{build}_f_0_{i}_0.jpg").write_bytes(b"jpg")

    def fake_upload(src: str, key: str, content_type: str):
        pass

    monkeypatch.setattr(server, "process_cubemap", fake_process_cubemap)
    monkeypatch.setattr(server, "upload_file", fake_upload)

    server._stream_tiles_to_storage(
        stack_img=object(),
        tile_root="clients/a/cubemap/s/tiles/testbuild",
        build_str="testbuild",
        tmp_dir=str(tmp_path),
        min_lod=0,
        max_lod=0,
        workers=2,
    )

    assert len(captured_on_tile_ready) == 1
    assert captured_on_tile_ready[0] is None, (
        "on_tile_ready must be None during the generation phase"
    )


def test_upload_starts_only_after_all_tiles_generated(tmp_path, monkeypatch):
    """No upload call should occur before process_cubemap returns."""
    server = _import_server()

    events = []

    def fake_process_cubemap(stack_img, out_dir, tile_size, build, min_lod, max_lod, on_tile_ready):
        # Create tile files, then record generation complete
        for i in range(3):
            (Path(out_dir) / f"{build}_f_0_{i}_0.jpg").write_bytes(b"jpg")
        events.append("generation_complete")

    def fake_upload(src: str, key: str, content_type: str):
        events.append(f"upload:{Path(src).name}")

    monkeypatch.setattr(server, "process_cubemap", fake_process_cubemap)
    monkeypatch.setattr(server, "upload_file", fake_upload)

    server._stream_tiles_to_storage(
        stack_img=object(),
        tile_root="clients/a/cubemap/s/tiles/testbuild",
        build_str="testbuild",
        tmp_dir=str(tmp_path),
        min_lod=0,
        max_lod=0,
        workers=2,
    )

    assert events[0] == "generation_complete", (
        "generation_complete must be the first event"
    )
    upload_events = [e for e in events if e.startswith("upload:")]
    assert len(upload_events) == 3, "All 3 tiles must be uploaded"


def test_all_generated_tiles_are_uploaded(tmp_path, monkeypatch):
    """Every .jpg file written by process_cubemap must be uploaded."""
    server = _import_server()

    tile_names = [
        "build_f_0_0_0.jpg",
        "build_f_0_1_0.jpg",
        "build_b_0_0_0.jpg",
        "build_r_1_0_0.jpg",
    ]

    def fake_process_cubemap(stack_img, out_dir, tile_size, build, min_lod, max_lod, on_tile_ready):
        for name in tile_names:
            (Path(out_dir) / name).write_bytes(b"jpg")

    uploaded_keys = []
    lock = threading.Lock()

    def fake_upload(src: str, key: str, content_type: str):
        with lock:
            uploaded_keys.append(Path(key).name)

    monkeypatch.setattr(server, "process_cubemap", fake_process_cubemap)
    monkeypatch.setattr(server, "upload_file", fake_upload)

    count = server._stream_tiles_to_storage(
        stack_img=object(),
        tile_root="clients/a/cubemap/s/tiles/build",
        build_str="build",
        tmp_dir=str(tmp_path),
        min_lod=0,
        max_lod=None,
        workers=4,
    )

    assert count == len(tile_names)
    assert sorted(uploaded_keys) == sorted(tile_names)


def test_tile_files_removed_after_upload(tmp_path, monkeypatch):
    """All tile files must be deleted from disk after upload completes."""
    server = _import_server()

    def fake_process_cubemap(stack_img, out_dir, tile_size, build, min_lod, max_lod, on_tile_ready):
        for i in range(4):
            (Path(out_dir) / f"{build}_f_0_{i}_0.jpg").write_bytes(b"jpg")

    def fake_upload(src: str, key: str, content_type: str):
        pass

    monkeypatch.setattr(server, "process_cubemap", fake_process_cubemap)
    monkeypatch.setattr(server, "upload_file", fake_upload)

    server._stream_tiles_to_storage(
        stack_img=object(),
        tile_root="clients/a/cubemap/s/tiles/build",
        build_str="build",
        tmp_dir=str(tmp_path),
        min_lod=0,
        max_lod=0,
        workers=2,
    )

    remaining = list(tmp_path.glob("*.jpg"))
    assert remaining == [], f"Expected no leftover tile files, found: {remaining}"


def test_lod_extracted_from_tile_filename(tmp_path, monkeypatch):
    """The lod value passed to enqueue must match the lod in the filename."""
    server = _import_server()

    lod_values_seen = []
    lock = threading.Lock()

    def fake_process_cubemap(stack_img, out_dir, tile_size, build, min_lod, max_lod, on_tile_ready):
        # LOD 0 and LOD 1 tiles
        (Path(out_dir) / f"{build}_f_0_0_0.jpg").write_bytes(b"jpg")
        (Path(out_dir) / f"{build}_f_1_0_0.jpg").write_bytes(b"jpg")

    def fake_upload(src: str, key: str, content_type: str):
        pass

    original_enqueue = server.TileUploadQueue.enqueue

    def capturing_enqueue(self, file_path, filename, lod):
        with lock:
            lod_values_seen.append((filename, lod))
        original_enqueue(self, file_path, filename, lod)

    monkeypatch.setattr(server, "process_cubemap", fake_process_cubemap)
    monkeypatch.setattr(server, "upload_file", fake_upload)
    monkeypatch.setattr(server.TileUploadQueue, "enqueue", capturing_enqueue)

    server._stream_tiles_to_storage(
        stack_img=object(),
        tile_root="clients/a/cubemap/s/tiles/build",
        build_str="build",
        tmp_dir=str(tmp_path),
        min_lod=0,
        max_lod=None,
        workers=2,
    )

    lod_by_name = dict(lod_values_seen)
    assert lod_by_name["build_f_0_0_0.jpg"] == 0
    assert lod_by_name["build_f_1_0_0.jpg"] == 1
