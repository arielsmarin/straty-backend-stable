from __future__ import annotations

import os
import logging
from pathlib import Path

import pyvips
import requests

SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg")

# Remote asset configuration
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "https://pub-4503b4acd02140cfb69ab3886530d45b.r2.dev")


def construct_r2_url(asset_path: Path, extension: str) -> str:
    """
    Construct R2 public URL for an asset.
    
    Args:
        asset_path: Base path without extension (e.g., 'panoconfig360_cache/clients/monte-negro/scenes/kitchen/base_kitchen')
        extension: File extension including dot (e.g., '.jpg')
    
    Returns:
        Full R2 public URL
    """
    candidate = asset_path.with_suffix(extension)
    relative_path = str(candidate)
    
    # Strip 'panoconfig360_cache/' prefix to get the R2 key
    if relative_path.startswith("panoconfig360_cache/"):
        r2_key = relative_path.replace("panoconfig360_cache/", "", 1)
    else:
        r2_key = relative_path
    
    return f"{R2_PUBLIC_URL}/{r2_key}"

class VipsImageCompat:
    def __init__(self, image: pyvips.Image):
        self.image = image

    @property
    def size(self) -> tuple[int, int]:
        return self.image.width, self.image.height

    def save(self, output_path: str | Path, _format: str = "JPEG", quality: int = 80, subsampling: int = 0) -> None:
        _ = subsampling
        path = str(output_path)
        self.image.write_to_file(f"{path}[Q={quality}]")


def resolve_asset(base_path: Path) -> Path:
    """
    Resolve asset path by checking local file system first, then attempting to
    download from remote R2 storage if not found locally.
    
    Args:
        base_path: Path without extension (e.g., 'panoconfig360_cache/clients/monte-negro/scenes/kitchen/base_kitchen')
    
    Returns:
        Path to the resolved asset file
        
    Raises:
        FileNotFoundError: If asset is not found locally or remotely
    """
    # First, try to find the asset locally
    for ext in SUPPORTED_EXTENSIONS:
        candidate = base_path.with_suffix(ext)
        if candidate.exists():
            return candidate
    
    # If not found locally, try to download from R2
    logging.info(f"🌐 Asset not found locally, attempting remote download: {base_path}")
    
    for ext in SUPPORTED_EXTENSIONS:
        candidate = base_path.with_suffix(ext)
        remote_url = construct_r2_url(base_path, ext)
        
        try:
            logging.info(f"📥 Attempting to download: {remote_url}")
            response = requests.get(remote_url, timeout=30, stream=True)
            
            if response.status_code == 200:
                # Create directory if it doesn't exist
                candidate.parent.mkdir(parents=True, exist_ok=True)
                
                # Save the file, streaming for large assets
                with open(candidate, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                logging.info(f"✅ Downloaded and cached: {candidate}")
                return candidate
            elif response.status_code == 404:
                logging.debug(f"Asset not found at {remote_url}")
                continue
            else:
                logging.warning(f"⚠️ Unexpected status {response.status_code} for {remote_url}")
                continue
                
        except requests.RequestException as e:
            logging.warning(f"⚠️ Failed to download from {remote_url}: {e}")
            continue
    
    raise FileNotFoundError(f"Asset não encontrado para base: {base_path}")


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
    scaled = img.resize(width / img.width, vscale=height / img.height, kernel="linear")
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
