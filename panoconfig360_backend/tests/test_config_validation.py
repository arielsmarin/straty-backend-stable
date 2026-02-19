import importlib
import json
import sys
import types

import pytest


@pytest.fixture
def load_config(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "pyvips", types.SimpleNamespace(Image=object)
    )
    from panoconfig360_backend.render import dynamic_stack

    importlib.reload(dynamic_stack)
    return dynamic_stack.load_config


def _write_config(tmp_path, payload):
    path = tmp_path / "client_cfg.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_config_requires_scenes_or_layers(tmp_path, load_config):
    config_path = _write_config(tmp_path, {"naming": {"foo": "bar"}})

    with pytest.raises(ValueError, match="scenes|layers"):
        load_config(config_path)


def test_load_config_with_layers_fallback(tmp_path, load_config):
    config_path = _write_config(tmp_path, {"layers": []})

    config, scenes, naming = load_config(config_path)

    assert config["layers"] == []
    assert "default" in scenes
    assert naming == {}


def test_load_config_validates_scene_layers(tmp_path, load_config):
    config_path = _write_config(
        tmp_path,
        {"scenes": {"lobby": {"scene_index": 0, "layers": []}}},
    )

    _, scenes, _ = load_config(config_path)

    assert scenes["lobby"]["layers"] == []


def test_load_config_rejects_invalid_scene_layers(tmp_path, load_config):
    config_path = _write_config(
        tmp_path,
        {"scenes": {"bad": {"layers": "oops"}}},
    )

    with pytest.raises(ValueError, match="layers"):
        load_config(config_path)
