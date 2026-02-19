import importlib
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
