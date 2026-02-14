from __future__ import annotations

from pathlib import Path

import pyvips


class VipsImageCompat:
    def __init__(self, image: pyvips.Image):
        self.image = image

    @property
    def size(self) -> tuple[int, int]:
        return self.image.width, self.image.height

    def save(self, output_path: str | Path, _format: str = "JPEG", quality: int = 95, subsampling: int = 0) -> None:
        _ = subsampling
        path = str(output_path)
        self.image.write_to_file(f"{path}[Q={quality}]")


def load_rgb_image(path: str | Path) -> pyvips.Image:
    img = pyvips.Image.new_from_file(str(path), access="random")
    if img.bands == 1:
        img = img.bandjoin([img, img])
    elif img.bands >= 3:
        img = img.extract_band(0, n=3)
    return img.cast("uchar")


def ensure_rgb8(img: pyvips.Image) -> pyvips.Image:
    if img.bands == 1:
        img = img.bandjoin([img, img])
    elif img.bands >= 3:
        img = img.extract_band(0, n=3)
    return img.cast("uchar")


def resize_to_match(img: pyvips.Image, width: int, height: int) -> pyvips.Image:
    if img.width == width and img.height == height:
        return img
    scaled = img.resize(width / img.width, vscale=height / img.height, kernel="cubic")
    return scaled


def blend_with_mask(base: pyvips.Image, material: pyvips.Image, mask: pyvips.Image) -> pyvips.Image:
    base_f = base.cast("float")
    material_f = material.cast("float")
    mask_f = mask.cast("float") / 255.0
    if mask_f.bands > 1:
        mask_f = mask_f.extract_band(0)
    if base_f.bands > 1:
        mask_f = mask_f.bandjoin([mask_f] * (base_f.bands - 1))
    out = base_f * (1.0 - mask_f) + material_f * mask_f
    return out.cast("uchar")
