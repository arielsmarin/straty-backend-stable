from pathlib import Path

from render.scene_context import resolve_scene_context


def test_resolve_scene_context_supports_assets_root_override():
    project = {
        "client_id": "client-a",
        "scenes": {
            "kitchen": {
                "scene_index": 2,
                "layers": [],
            }
        },
    }
    custom_root = Path("/tmp/render_123/panoconfig360_cache/clients/client-a/scenes/kitchen")

    ctx = resolve_scene_context(project, "kitchen", assets_root=custom_root)

    assert ctx["assets_root"] == custom_root
    assert ctx["scene_index"] == 2
