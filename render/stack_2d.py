import os

import pyvips

from render.vips_compat import ensure_rgb8, load_rgb_image, resize_to_match


def render_stack_2d(base_image_path, layers, output_path):
    base = load_rgb_image(base_image_path)

    for layer in layers:
        path = layer.get("path")
        if not path:
            continue

        if not os.path.exists(path):
            continue

        overlay = pyvips.Image.new_from_file(path, access="random")
        if overlay.bands == 1:
            overlay = overlay.bandjoin([overlay, overlay]).bandjoin_const(255)
        elif overlay.bands == 2:
            gray = overlay.extract_band(0)
            alpha = overlay.extract_band(1)
            overlay = gray.bandjoin([gray, gray, alpha])
        elif overlay.bands == 3:
            overlay = overlay.bandjoin_const(255)
        else:
            overlay = overlay.extract_band(0, n=4)

        overlay = resize_to_match(overlay.cast("uchar"), base.width, base.height)
        base = base.bandjoin_const(255).composite2(overlay, "over").extract_band(0, n=3)

    ensure_rgb8(base).write_to_file(f"{output_path}[Q=80]")
