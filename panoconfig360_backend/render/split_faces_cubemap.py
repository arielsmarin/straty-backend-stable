# backend/split_faces_cubemap.py

import os
from PIL import Image
from pathlib import Path
import numpy as np


# Ordem das faces no strip vertical (de cima para baixo)
STRIP_FACES = ["px", "nx", "py", "ny", "pz", "nz"]

# Mapeamento para o padrão Marzipano
MARZIPANO_FACE_MAP = {
    "px": "r",
    "nx": "l",
    "py": "u",
    "ny": "d",
    "pz": "f",
    "nz": "b",
}

# Normaliza qualquer entrada para um cubemap horizontal


def normalize_to_horizontal_cubemap(img: Image.Image) -> Image.Image:
    """
    Recebe qualquer formato e retorna um cubemap horizontal em memória
    """
    # por enquanto: assume que já vem horizontal
    return img.transpose(Image.FLIP_LEFT_RIGHT)  # espelha horizontalmente

# Divide as faces do cubemap e gera os tiles


def split_faces_from_image(
    cubemap_img: Image.Image,
    output_base_dir: str,
    tile_size: int,
    level: int,
    build: str
):
    output_base_dir = str(output_base_dir)

    width, height = cubemap_img.size
    face_size = height

    if width != face_size * 6:
        raise ValueError("Cubemap horizontal inválido")

    for i, face_key in enumerate(STRIP_FACES):
        left = i * face_size
        face_img = cubemap_img.crop((left, 0, left + face_size, face_size))

        if face_key == "py":
            face_img = face_img.rotate(90, expand=False)
            marzipano_face = MARZIPANO_FACE_MAP["ny"]
        elif face_key == "ny":
            face_img = face_img.rotate(-90, expand=False)
            marzipano_face = MARZIPANO_FACE_MAP["py"]
        else:
            marzipano_face = MARZIPANO_FACE_MAP[face_key]

        _generate_tiles(face_img, output_base_dir,
                        marzipano_face, tile_size, level, build)


def _generate_tiles(face_img: Image.Image, out_dir: str, face: str, tile_size: int, lod: int, build: str):
    width, height = face_img.size
    if width % tile_size != 0 or height % tile_size != 0:
        raise ValueError("Face não é múltipla do tile_size")

    tiles_x = width // tile_size
    tiles_y = height // tile_size

    for y in range(tiles_y):
        for x in range(tiles_x):
            tile = face_img.crop((
                x * tile_size,
                y * tile_size,
                (x + 1) * tile_size,
                (y + 1) * tile_size
            ))

            filename = f"{build}_{face}_{lod}_{x}_{y}.jpg"
            tile_path = os.path.join(out_dir, filename)
            tile.save(tile_path, "JPEG", quality=95, subsampling=0)

# Função principal para processar o cubemap


# Função principal para processar o cubemap
def process_cubemap(
    input_image: Image.Image,
    output_base_dir: Path | str,
    tile_size=512,
    level=0,
    build: str = "unknown"
):
    """
    Processa o cubemap completo e gera os tiles com o padrão:
    {BUILD}_{FACE}_{LOD}_{X}_{Y}.jpg
    """
    img = input_image
    cubemap_img = normalize_to_horizontal_cubemap(img)

    split_faces_from_image(
        cubemap_img,
        output_base_dir,
        tile_size,
        level,
        build
    )

# Fim do arquivo backend/split_faces_cubemap.py
