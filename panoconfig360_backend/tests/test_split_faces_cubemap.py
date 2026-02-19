import importlib
import logging
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


def test_configure_pyvips_concurrency_uses_legacy_api(monkeypatch):
    calls = []
    monkeypatch.setitem(
        sys.modules,
        "pyvips",
        types.SimpleNamespace(Image=object, __version__="2.1.0", concurrency_set=lambda value: calls.append(value)),
    )

    from panoconfig360_backend.render import split_faces_cubemap

    importlib.reload(split_faces_cubemap)
    split_faces_cubemap._configure_pyvips_concurrency(1)

    assert calls == [1]


def test_configure_pyvips_concurrency_uses_vips_lib_api(monkeypatch):
    calls = []
    monkeypatch.setitem(
        sys.modules,
        "pyvips",
        types.SimpleNamespace(
            Image=object,
            __version__="2.2.0",
            vips_lib=types.SimpleNamespace(vips_concurrency_set=lambda value: calls.append(value)),
        ),
    )

    from panoconfig360_backend.render import split_faces_cubemap

    importlib.reload(split_faces_cubemap)
    split_faces_cubemap._configure_pyvips_concurrency(1)

    assert calls == [1]


def test_configure_pyvips_concurrency_falls_back_to_env(monkeypatch, caplog):
    monkeypatch.setitem(sys.modules, "pyvips", types.SimpleNamespace(Image=object, __version__="2.2.0"))
    monkeypatch.delenv("VIPS_CONCURRENCY", raising=False)

    from panoconfig360_backend.render import split_faces_cubemap

    importlib.reload(split_faces_cubemap)
    with caplog.at_level(logging.WARNING):
        split_faces_cubemap._configure_pyvips_concurrency(1)

    assert os.environ["VIPS_CONCURRENCY"] == "1"
    assert "Pyvips concurrency API unavailable" in caplog.text
