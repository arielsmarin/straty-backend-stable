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

    # Fixed LOD: LOD0 1024/512 (2×2) + LOD1 2048/512 (4×4) = 20 tiles/face × 6 = 120
    expected_tiles = 6 * (2 * 2 + 4 * 4)
    assert len(tiles) == expected_tiles
    # LOD0 resizes from 2048→1024 for each of 6 faces
    assert len(calls["resize"]) == 6
    assert all(
        call == (".jpg", {"Q": 70, "strip": True, "optimize_coding": False})
        for call in calls["write"]
    )


def test_process_cubemap_to_memory_1024_produces_120_tiles(monkeypatch):
    """FACEsize=1024 with fixed LOD configs → LOD0 no resize (2×2) + LOD1 resize up (4×4) = 120 tiles."""
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

    # Fixed LOD: LOD0 1024/512 (2×2) + LOD1 2048/512 (4×4) = 20 tiles/face × 6 = 120
    assert len(tiles) == 120
    # LOD0: no resize (face_size==1024==target); LOD1: resize 1024→2048 for 6 faces
    assert len(calls["resize"]) == 6


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


def test_process_cubemap_to_memory_tile_naming_and_lod_counts(monkeypatch):
    """Validate tile names follow BUILD_FACE_LOD_X_Y.jpg and LOD counts are correct."""
    monkeypatch.setitem(sys.modules, "pyvips", types.SimpleNamespace(Image=object))

    from render import split_faces_cubemap

    importlib.reload(split_faces_cubemap)
    monkeypatch.setattr(split_faces_cubemap, "ensure_rgb8", lambda img: img)

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
            return FakeImage(int(self.width * scale), int(self.height * scale))

        def crop(self, *_args):
            class FakeTile:
                def write_to_buffer(self, fmt, **kwargs):
                    return b"jpg"

            return FakeTile()

    tiles = split_faces_cubemap.process_cubemap_to_memory(
        FakeImage(12288, 2048),
        tile_size=512,
        build="000804000000",
    )

    assert len(tiles) == 120

    valid_faces = {"f", "b", "l", "r", "u", "d"}
    lod0_count = 0
    lod1_count = 0

    for filename, _data, lod in tiles:
        # Validate naming: BUILD_FACE_LOD_X_Y.jpg
        assert filename.endswith(".jpg")
        parts = filename[:-4].split("_")
        assert len(parts) == 5, f"Bad tile name: {filename}"
        build_str, face, lod_str, x_str, y_str = parts
        assert build_str == "000804000000"
        assert face in valid_faces, f"Invalid face: {face}"
        assert lod_str in ("0", "1"), f"Invalid LOD: {lod_str}"
        assert int(lod_str) == lod, f"LOD mismatch: filename={lod_str} tuple={lod}"
        x, y = int(x_str), int(y_str)

        # Validate tile coordinate ranges per LOD
        if lod == 0:
            assert 0 <= x <= 1 and 0 <= y <= 1, f"LOD0 coords out of range: {x},{y}"
            lod0_count += 1
        elif lod == 1:
            assert 0 <= x <= 3 and 0 <= y <= 3, f"LOD1 coords out of range: {x},{y}"
            lod1_count += 1

    # LOD0: 6 faces × 2×2 = 24; LOD1: 6 faces × 4×4 = 96
    assert lod0_count == 24
    assert lod1_count == 96
