"""Tests for parallel tile upload using ThreadPoolExecutor."""
import logging
import os
import threading
import time
from pathlib import Path

from storage.tile_upload_queue import TileUploadQueue, _DEFAULT_UPLOAD_WORKERS


def test_default_upload_workers_uses_cpu_count():
    """Default upload workers should be min(8, cpu_count * 2)."""
    expected = min(8, (os.cpu_count() or 4) * 2)
    assert _DEFAULT_UPLOAD_WORKERS == expected


def test_tiles_upload_in_parallel(tmp_path: Path):
    """Multiple tiles should be uploaded concurrently by different threads."""
    thread_ids = []
    lock = threading.Lock()
    barrier = threading.Barrier(3, timeout=5)

    def fake_upload(src: str, key: str, content_type: str):
        with lock:
            thread_ids.append(threading.get_ident())
        barrier.wait()

    for i in range(3):
        (tmp_path / f"tile_{i}.jpg").write_bytes(b"jpg-data")

    queue = TileUploadQueue(
        tile_root="clients/a/cubemap/s/tiles/build",
        upload_fn=fake_upload,
        workers=4,
    )
    queue.start()

    for i in range(3):
        queue.enqueue(tmp_path / f"tile_{i}.jpg", f"build_f_0_{i}_0.jpg", 0)

    queue.close_and_wait()

    assert queue.uploaded_count == 3
    assert len(set(thread_ids)) >= 2, "Expected uploads on multiple threads"


def test_upload_queued_log(tmp_path: Path, caplog):
    """Enqueue should log 'upload queued' for each tile."""
    def fake_upload(src: str, key: str, content_type: str):
        pass

    tile_path = tmp_path / "tile_q.jpg"
    tile_path.write_bytes(b"jpg-data")

    queue = TileUploadQueue(
        tile_root="clients/a/cubemap/s/tiles/build",
        upload_fn=fake_upload,
        workers=2,
    )

    with caplog.at_level(logging.INFO):
        queue.start()
        queue.enqueue(tile_path, "build_f_0_0_0.jpg", 0)
        queue.close_and_wait()

    assert "upload queued" in caplog.text


def test_120_tiles_parallel_upload_and_cleanup(tmp_path: Path):
    """Upload 120 tiles in parallel; all files cleaned after completion."""
    uploaded_keys = []
    lock = threading.Lock()

    def fake_upload(src: str, key: str, content_type: str):
        with lock:
            uploaded_keys.append(key)

    faces = ["f", "b", "l", "r", "u", "d"]
    tile_files = []
    for face in faces:
        for row in range(4):
            for col in range(4):
                fname = f"build_{face}_0_{row}_{col}.jpg"
                path = tmp_path / fname
                path.write_bytes(b"jpg-data")
                tile_files.append((path, fname))
        for row in range(2):
            for col in range(2):
                fname = f"build_{face}_1_{row}_{col}.jpg"
                path = tmp_path / fname
                path.write_bytes(b"jpg-data")
                tile_files.append((path, fname))

    assert len(tile_files) == 120

    queue = TileUploadQueue(
        tile_root="clients/a/cubemap/s/tiles/build",
        upload_fn=fake_upload,
        workers=8,
    )
    queue.start()

    for path, fname in tile_files:
        queue.enqueue(path, fname, 0)

    queue.close_and_wait()

    assert queue.uploaded_count == 120
    assert len(uploaded_keys) == 120
    remaining = list(tmp_path.glob("*.jpg"))
    assert remaining == [], f"Expected no leftover files, found {len(remaining)}"


def test_build_fails_on_upload_error(tmp_path: Path):
    """Build must fail if any upload raises an error."""
    call_count = 0
    lock = threading.Lock()

    def sometimes_fail(src: str, key: str, content_type: str):
        nonlocal call_count
        with lock:
            call_count += 1
            current = call_count
        if current == 2:
            raise OSError("network-fail")

    for i in range(3):
        (tmp_path / f"tile_{i}.jpg").write_bytes(b"jpg-data")

    queue = TileUploadQueue(
        tile_root="clients/a/cubemap/s/tiles/build",
        upload_fn=sometimes_fail,
        workers=1,
    )
    queue.start()

    for i in range(3):
        queue.enqueue(tmp_path / f"tile_{i}.jpg", f"build_f_0_{i}_0.jpg", 0)

    try:
        queue.close_and_wait()
        assert False, "close_and_wait should raise on upload failure"
    except RuntimeError as exc:
        assert "Falha em" in str(exc)
