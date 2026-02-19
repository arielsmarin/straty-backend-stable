from pathlib import Path

from panoconfig360_backend.storage.tile_upload_queue import TileUploadQueue


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
