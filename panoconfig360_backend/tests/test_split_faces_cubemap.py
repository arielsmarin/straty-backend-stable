import importlib
import os
import sys
import types


def test_resize_face_for_lod_uses_linear_kernel(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyvips", types.SimpleNamespace(Image=object))

    from panoconfig360_backend.render import split_faces_cubemap

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

    from panoconfig360_backend.render import split_faces_cubemap

    importlib.reload(split_faces_cubemap)
    try:
        split_faces_cubemap._configure_pyvips_concurrency(0)
        assert os.environ["VIPS_CONCURRENCY"] == "0"
    finally:
        if original is None:
            os.environ.pop("VIPS_CONCURRENCY", None)
        else:
            os.environ["VIPS_CONCURRENCY"] = original


def test_configure_pyvips_concurrency_keeps_existing_env(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyvips", types.SimpleNamespace(Image=object, __version__="3.1.1"))
    monkeypatch.setenv("VIPS_CONCURRENCY", "2")

    from panoconfig360_backend.render import split_faces_cubemap

    importlib.reload(split_faces_cubemap)
    split_faces_cubemap._configure_pyvips_concurrency(0)

    assert os.environ["VIPS_CONCURRENCY"] == "2"
