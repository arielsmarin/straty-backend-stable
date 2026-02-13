import os
import shutil
import tempfile
from pathlib import Path

import pyvips

from panoconfig360_backend.render.vips_compat import VipsImageCompat, ensure_rgb8

STRIP_FACES = ["px", "nx", "py", "ny", "pz", "nz"]

MARZIPANO_FACE_MAP = {
    "px": "r",
    "nx": "l",
    "py": "u",
    "ny": "d",
    "pz": "f",
    "nz": "b",
}


def _to_vips_image(img) -> pyvips.Image:
    if isinstance(img, VipsImageCompat):
        return img.image
    if isinstance(img, pyvips.Image):
        return img
    raise TypeError("Formato de imagem inválido para processamento de cubemap")


def normalize_to_horizontal_cubemap(img):
    return _to_vips_image(img).flip("horizontal")


def split_faces_from_image(cubemap_img, output_base_dir: str, tile_size: int, level: int, build: str):
    output_base_dir = str(output_base_dir)

    width = cubemap_img.width
    height = cubemap_img.height
    face_size = height

    if width != face_size * 6:
        raise ValueError("Cubemap horizontal inválido")

    for i, face_key in enumerate(STRIP_FACES):
        left = i * face_size
        face_img = cubemap_img.extract_area(left, 0, face_size, face_size)

        if face_key == "py":
            face_img = face_img.rot90()
            marzipano_face = MARZIPANO_FACE_MAP["ny"]
        elif face_key == "ny":
            face_img = face_img.rot270()
            marzipano_face = MARZIPANO_FACE_MAP["py"]
        else:
            marzipano_face = MARZIPANO_FACE_MAP[face_key]

        _generate_tiles(face_img, output_base_dir, marzipano_face, tile_size, level, build)


def _generate_tiles(face_img: pyvips.Image, out_dir: str, face: str, tile_size: int, lod: int, build: str):
    width = face_img.width
    height = face_img.height
    if width % tile_size != 0 or height % tile_size != 0:
        raise ValueError("Face não é múltipla do tile_size")

    with tempfile.TemporaryDirectory() as tmp_dir:
        dz_prefix = str(Path(tmp_dir) / "face")
        ensure_rgb8(face_img).dzsave(
            dz_prefix,
            tile_size=tile_size,
            overlap=0,
            depth="one",
            suffix=".jpg[Q=95]",
            container="fs",
        )

        tiles_root = Path(f"{dz_prefix}_files") / "0"
        for tile in tiles_root.glob("*.jpg"):
            stem = tile.stem
            x_str, y_str = stem.split("_")
            filename = f"{build}_{face}_{lod}_{x_str}_{y_str}.jpg"
            shutil.move(str(tile), os.path.join(out_dir, filename))


def process_cubemap(input_image, output_base_dir: Path | str, tile_size=512, level=0, build: str = "unknown"):
    cubemap_img = normalize_to_horizontal_cubemap(input_image)
    split_faces_from_image(cubemap_img, output_base_dir, tile_size, level, build)
