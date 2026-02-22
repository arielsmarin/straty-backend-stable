from pathlib import Path
import threading
import time

from storage.tile_upload_queue import TileUploadQueue


def test_tile_upload_queue_tracks_states_and_uploads(tmp_path: Path):
    uploaded = []

    def fake_upload(src: str, key: str, content_type: str):
        uploaded.append((Path(src).name, key, content_type))

    tile_path = tmp_path / "tile_0.jpg"
    tile_path.write_bytes(b"jpg")

    queue = TileUploadQueue(
        tile_root="clients/a/cubemap/s/tiles/build",
        upload_fn=fake_upload,
        workers=2,
    )

    queue.start()
    queue.enqueue(tile_path, "build_f_0_0_0.jpg", 0)
    queue.close_and_wait()

    assert queue.uploaded_count == 1
    assert uploaded == [
        (
            "tile_0.jpg",
            "clients/a/cubemap/s/tiles/build/build_f_0_0_0.jpg",
            "image/jpeg",
        )
    ]
    assert queue.states["build_f_0_0_0.jpg"] == "visible"


def test_tile_upload_queue_raises_on_upload_failure(tmp_path: Path):
    def failing_upload(src: str, key: str, content_type: str):
        raise OSError("io-fail")

    tile_path = tmp_path / "tile_1.jpg"
    tile_path.write_bytes(b"jpg")

    queue = TileUploadQueue(
        tile_root="clients/a/cubemap/s/tiles/build",
        upload_fn=failing_upload,
        workers=1,
    )

    queue.start()
    queue.enqueue(tile_path, "build_f_0_1_0.jpg", 0)

    try:
        queue.close_and_wait()
        assert False, "close_and_wait should fail when uploads fail"
    except RuntimeError as exc:
        assert "Falha em 1 uploads" in str(exc)


def test_no_uploads_start_before_start_uploads(tmp_path: Path):
    """Verify that no upload starts until start_uploads() is explicitly called.

    This ensures strict two-phase operation: all tiles are enqueued first
    (Phase 1), then uploads begin (Phase 2).
    """
    upload_started_times = []
    lock = threading.Lock()

    def tracking_upload(src: str, key: str, content_type: str):
        with lock:
            upload_started_times.append(time.monotonic())
        # Small delay to ensure timing is detectable
        time.sleep(0.01)

    # Create tile files
    for i in range(5):
        (tmp_path / f"tile_{i}.jpg").write_bytes(b"jpg")

    queue = TileUploadQueue(
        tile_root="clients/a/cubemap/s/tiles/build",
        upload_fn=tracking_upload,
        workers=4,
    )

    # Enqueue all tiles - no uploads should start yet
    for i in range(5):
        queue.enqueue(tmp_path / f"tile_{i}.jpg", f"build_f_0_{i}_0.jpg", 0)

    # Wait a moment to ensure no uploads started during enqueueing
    time.sleep(0.05)

    # Verify no uploads have started
    with lock:
        assert len(upload_started_times) == 0, (
            "Uploads should not start before start_uploads() is called"
        )

    # Now start uploads
    enqueue_end_time = time.monotonic()
    queue.start_uploads()
    queue.close_and_wait()

    # Verify all uploads happened after enqueue phase
    with lock:
        assert len(upload_started_times) == 5
        for upload_time in upload_started_times:
            assert upload_time >= enqueue_end_time, (
                "All uploads should start after start_uploads() is called"
            )
