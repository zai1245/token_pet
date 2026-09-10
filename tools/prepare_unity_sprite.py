"""Normalize generated transparent art into a Unity-friendly square sprite.

The source image is kept untouched. Transparent padding is trimmed, the artwork
is resized without changing its aspect ratio, and it is centered on a clean
RGBA canvas so every generated furniture/accessory uses the same import rules.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def normalize_sprite(
    source: Path,
    destination: Path,
    size: int,
    padding: int,
    preserve_canvas_aspect: bool,
) -> None:
    image = Image.open(source).convert("RGBA")
    alpha = image.getchannel("A")
    bbox = alpha.point(lambda value: 255 if value > 6 else 0).getbbox()
    if bbox is None:
        raise ValueError(f"Sprite has no visible pixels: {source}")

    image = image.crop(bbox)
    available = max(1, size - padding * 2)
    scale = min(available / image.width, available / image.height)
    target = (
        max(1, round(image.width * scale)),
        max(1, round(image.height * scale)),
    )
    image = image.resize(target, Image.Resampling.LANCZOS)

    canvas_size = (
        (target[0] + padding * 2, target[1] + padding * 2)
        if preserve_canvas_aspect
        else (size, size)
    )
    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    canvas.alpha_composite(
        image,
        ((canvas_size[0] - target[0]) // 2, (canvas_size[1] - target[1]) // 2),
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--size", type=int, default=512)
    parser.add_argument("--padding", type=int, default=18)
    parser.add_argument(
        "--preserve-canvas-aspect",
        action="store_true",
        help="Use a tight rectangular canvas; useful for furniture sprites.",
    )
    args = parser.parse_args()
    normalize_sprite(
        args.source,
        args.destination,
        args.size,
        args.padding,
        args.preserve_canvas_aspect,
    )


if __name__ == "__main__":
    main()
