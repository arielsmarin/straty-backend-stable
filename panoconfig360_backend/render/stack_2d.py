import os
from PIL import Image

def render_stack_2d(base_image_path, layers, output_path):
    base = Image.open(base_image_path).convert("RGBA")

    for layer in layers:
        path = layer.get("path")
        if not path:
            continue
        
        if not os.path.exists(path):
            continue
        
        overlay = Image.open(path).convert("RGBA")

        if overlay.size != base.size:
            overlay = overlay.resize(base.size, Image.BICUBIC)

        base = Image.alpha_composite(base, overlay)

    base.convert("RGB").save(output_path, "JPEG", quality=95)
