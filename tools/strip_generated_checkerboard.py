"""Remove a baked-in gray checkerboard from an isolated colorful sprite.

The generator occasionally renders its transparency preview into RGB pixels.
This tool flood-fills low-saturation pixels from the canvas border and turns
only that connected background transparent. Low-saturation highlights enclosed
by the colorful subject remain intact.
"""

from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

from PIL import Image


def clean(source: Path, destination: Path) -> None:
    image = Image.open(source).convert("RGBA")
    hsv = image.convert("HSV")
    width, height = image.size
    rgba = image.load()
    hsv_pixels = hsv.load()

    def is_subject_barrier(x: int, y: int) -> bool:
        saturation = hsv_pixels[x, y][1]
        value = hsv_pixels[x, y][2]
        alpha = rgba[x, y][3]
        return alpha > 8 and saturation >= 34 and value >= 18

    background = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    def enqueue(x: int, y: int) -> None:
        index = y * width + x
        if background[index] or is_subject_barrier(x, y):
            return
        background[index] = 1
        queue.append((x, y))

    for x in range(width):
        enqueue(x, 0)
        enqueue(x, height - 1)
    for y in range(height):
        enqueue(0, y)
        enqueue(width - 1, y)

    while queue:
        x, y = queue.popleft()
        if x > 0:
            enqueue(x - 1, y)
        if x + 1 < width:
            enqueue(x + 1, y)
        if y > 0:
            enqueue(x, y - 1)
        if y + 1 < height:
            enqueue(x, y + 1)

    output = image.copy()
    output_pixels = output.load()
    transparent = 0
    for y in range(height):
        for x in range(width):
            if background[y * width + x]:
                red, green, blue, _ = output_pixels[x, y]
                output_pixels[x, y] = (red, green, blue, 0)
                transparent += 1
            else:
                red, green, blue, _ = output_pixels[x, y]
                output_pixels[x, y] = (red, green, blue, 255)

    destination.parent.mkdir(parents=True, exist_ok=True)
    output.save(destination)
    corners = [output.getpixel(point)[3] for point in (
        (0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)
    )]
    print(
        f"saved={destination} size={width}x{height} "
        f"transparent={transparent / (width * height):.1%} corners={corners}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    clean(args.source, args.destination)


if __name__ == "__main__":
    main()
