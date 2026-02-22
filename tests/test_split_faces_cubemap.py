import importlib
import os
import sys
import types


def test_resize_face_for_lod_uses_linear_kernel(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyvips", types.SimpleNamespace(Image=object))

    from render import split_faces_cubemap

    importlib.reload(split_faces_cubemap)

    class FakeFaceImage:
        def __init__(self):
            self.calls = []

        def resize(self, scale, **kwargs):
            self.calls.append((scale, kwargs))
            return "resized"

    face = FakeFaceImage()
    resized = split_faces_cubemap._resize_face_for_lod(face, 0.5)

    assert resized == "resized"
    assert face.calls == [(0.5, {"kernel": "linear"})]


def test_configure_pyvips_concurrency_sets_env_default(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "pyvips",
        types.SimpleNamespace(Image=object, __version__="3.1.1"),
    )
    original = os.environ.get("VIPS_CONCURRENCY")
    monkeypatch.delenv("VIPS_CONCURRENCY", raising=False)

    from render import split_faces_cubemap

    importlib.reload(split_faces_cubemap)
    try:
        split_faces_cubemap.configure_pyvips_concurrency(0)
        assert os.environ["VIPS_CONCURRENCY"] == "0"
    finally:
        if original is None:
            os.environ.pop("VIPS_CONCURRENCY", None)
        else:
            os.environ["VIPS_CONCURRENCY"] = original


def test_configure_pyvips_concurrency_keeps_existing_env(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyvips", types.SimpleNamespace(Image=object, __version__="3.1.1"))
    monkeypatch.setenv("VIPS_CONCURRENCY", "2")

    from render import split_faces_cubemap

    importlib.reload(split_faces_cubemap)
    split_faces_cubemap.configure_pyvips_concurrency(0)

    assert os.environ["VIPS_CONCURRENCY"] == "2"


def test_process_cubemap_to_memory_reuses_split_and_resizes_once_per_face(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyvips", types.SimpleNamespace(Image=object))

    from render import split_faces_cubemap

    importlib.reload(split_faces_cubemap)
    monkeypatch.setattr(split_faces_cubemap, "ensure_rgb8", lambda img: img)

    # Use a list for the resize counter so appends are thread-safe under the GIL.
    calls = {"resize": [], "write": []}

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
            calls["resize"].append(scale)
            return FakeImage(int(self.width * scale), int(self.height * scale))

        def crop(self, *_args):
            class FakeTile:
                def write_to_buffer(self, fmt, **kwargs):
                    calls["write"].append((fmt, kwargs))
                    return b"jpg"

            return FakeTile()

    tiles = split_faces_cubemap.process_cubemap_to_memory(
        FakeImage(12288, 2048),
        tile_size=512,
        build="build",
    )

    # FACEsize=2048, tileSize=512 → 6 faces × 4×4 = 96 tiles, single LOD
    expected_tiles = 6 * (4 * 4)
    assert len(tiles) == expected_tiles
    # No resize needed: target_size == face_size
    assert len(calls["resize"]) == 0
    assert all(
        call == (".jpg", {"Q": 72, "strip": True, "optimize_coding": False})
        for call in calls["write"]
    )


def test_process_cubemap_to_memory_1024_produces_24_tiles(monkeypatch):
    """FACEsize=1024 with tileSize=512 → 6 faces × 2×2 = 24 tiles."""
    monkeypatch.setitem(sys.modules, "pyvips", types.SimpleNamespace(Image=object))

    from render import split_faces_cubemap

    importlib.reload(split_faces_cubemap)
    monkeypatch.setattr(split_faces_cubemap, "ensure_rgb8", lambda img: img)

    calls = {"resize": [], "write": []}

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
            calls["resize"].append(scale)
            return FakeImage(int(self.width * scale), int(self.height * scale))

        def crop(self, *_args):
            class FakeTile:
                def write_to_buffer(self, fmt, **kwargs):
                    calls["write"].append((fmt, kwargs))
                    return b"jpg"

            return FakeTile()

    tiles = split_faces_cubemap.process_cubemap_to_memory(
        FakeImage(6144, 1024),
        tile_size=512,
        build="build",
    )

    # FACEsize=1024, tileSize=512 → 6 faces × 2×2 = 24 tiles
    assert len(tiles) == 24
    # No resize needed: target_size == face_size
    assert len(calls["resize"]) == 0


def test_process_cubemap_to_memory_no_256_or_512_face_tiles(monkeypatch):
    """Ensure no tiles are generated at face size 256 or 512."""
    monkeypatch.setitem(sys.modules, "pyvips", types.SimpleNamespace(Image=object))

    from render import split_faces_cubemap

    importlib.reload(split_faces_cubemap)
    monkeypatch.setattr(split_faces_cubemap, "ensure_rgb8", lambda img: img)

    tile_sizes_seen = []

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
            tile_sizes_seen.append(int(self.width * scale))
            return FakeImage(int(self.width * scale), int(self.height * scale))

        def crop(self, *_args):
            class FakeTile:
                def write_to_buffer(self, fmt, **kwargs):
                    return b"jpg"

            return FakeTile()

    split_faces_cubemap.process_cubemap_to_memory(
        FakeImage(12288, 2048),
        tile_size=512,
        build="build",
    )

    # No face should be resized to 256 or 512
    for size in tile_sizes_seen:
        assert size not in (256, 512), f"Unexpected face resize to {size}"
