from pathlib import Path
from dynamic_stack_with_masks import stack_layers_image_only

# -----------------------------------------
# caminho real do SaaS
# -----------------------------------------
client_id = "monte-negro"
scene_id = "kitchen"

BASE_DIR = Path(__file__).resolve().parents[2]
assets_root = BASE_DIR / "panoconfig360_cache" / "clients" / client_id / "scenes" / scene_id



# -----------------------------------------
# seleção desejada
# -----------------------------------------
selection = {
    "backsplash": "diamond-black",
    "island": "naica",
    "countertop": "matterhorn",
}


# -----------------------------------------
# definição mínima das layers (mock do JSON)cle
# -----------------------------------------
layers = [
    {
        "id": "backsplash",
        "build_order": 0,
        "mask": "layer_kitchen_backsplash_mask.png",
        "items": [
            {"id": "diamond-black", "file": "mtl_diamond-black.png", "index": 0},
        ],
    },
    {
        "id": "island",
        "build_order": 1,
        "mask": "layer_kitchen_island_mask.png",
        "items": [
            {"id": "naica", "file": "mtl_naica.png", "index": 0},
        ],
    },
    {
        "id": "countertop",
        "build_order": 2,
        "mask": "layer_kitchen_countertop_mask.png",
        "items": [
            {"id": "matterhorn", "file": "mtl_matterhorn.png", "index": 0},
        ],
    },
]


# -----------------------------------------
# execução do stack
# -----------------------------------------
img = stack_layers_image_only(
    scene_id=scene_id,
    layers=layers,
    selection=selection,
    assets_root=assets_root,
)


# -----------------------------------------
# salvar resultado dentro da própria cena
# -----------------------------------------
output_path = assets_root / "TEST_RENDER.png"
img.save(output_path)

print(f"OK → imagem gerada em: {output_path}")
