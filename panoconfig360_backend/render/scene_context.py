from pathlib import Path

ASSETS_ROOT = Path("panoconfig360_cache/clients")


def resolve_scene_context(project: dict, scene_id: str | None):
    client_id = project.get("client_id")
    if not client_id or not isinstance(client_id, str):
        raise ValueError("client_id inválido no project")

    scenes = project["scenes"]

    if not scene_id:
        scene_id = next(iter(scenes.keys()))

    if scene_id not in scenes:
        raise ValueError(f"Scene inválida: {scene_id}")

    scene = scenes[scene_id]

    return {
        "scene_id": scene_id,
        "scene_index": scene.get("scene_index", 0),
        "layers": scene["layers"],
        "assets_root": ASSETS_ROOT / client_id / "scenes" / scene_id,
    }
