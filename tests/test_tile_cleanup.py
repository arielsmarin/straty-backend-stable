"""Tests for tile file cleanup after upload."""
from pathlib import Path

from storage.tile_upload_queue import TileUploadQueue


def test_tile_upload_queue_deletes_temp_file_after_upload(tmp_path: Path):
    """Tile file is removed from disk immediately after successful upload."""
    uploaded = []

    def fake_upload(src: str, key: str, content_type: str):
        uploaded.append(key)

    tile_path = tmp_path / "tile_cleanup.jpg"
    tile_path.write_bytes(b"jpg-data")

    assert tile_path.exists()

    queue = TileUploadQueue(
        tile_root="clients/a/cubemap/s/tiles/build",
        upload_fn=fake_upload,
        workers=1,
    )

    queue.start()
    queue.enqueue(tile_path, "build_f_0_0_0.jpg", 0)
    queue.close_and_wait()

    assert queue.uploaded_count == 1
    # File should be deleted after upload
    assert not tile_path.exists()


def test_tile_upload_queue_deletes_temp_file_after_failed_upload(tmp_path: Path):
    """Tile file is removed from disk even when upload fails."""
    def failing_upload(src: str, key: str, content_type: str):
        raise OSError("upload-fail")

    tile_path = tmp_path / "tile_fail.jpg"
    tile_path.write_bytes(b"jpg-data")

    assert tile_path.exists()

    queue = TileUploadQueue(
        tile_root="clients/a/cubemap/s/tiles/build",
        upload_fn=failing_upload,
        workers=1,
    )

    queue.start()
    queue.enqueue(tile_path, "build_f_0_0_1.jpg", 0)

    try:
        queue.close_and_wait()
    except RuntimeError:
        pass  # expected

    # File should still be deleted even on upload failure
    assert not tile_path.exists()
