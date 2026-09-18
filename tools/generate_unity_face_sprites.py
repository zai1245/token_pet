"""Generate antialiased Unity face layers from the original Canvas geometry.

The legacy pet is drawn at a 52 px body radius.  Unity displays the body at
2.2 world units, with face sprites at 100 pixels per unit, so every coordinate
below is converted from that original 52 px Canvas coordinate system.  Keeping
this generator in the repo makes new expressions reproducible instead of
requiring hand-edited copies of the full character art.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "unity_poc" / "Assets" / "TokenPet" / "Resources" / "FaceExpressions"
SIZE = 256
SUPERSAMPLE = 4
CANVAS_TO_ASSET = 2.2 / 104.0 * 100.0

INK = (60, 34, 3, 255)          # Canvas #3c2203
BLUSH = (244, 168, 184, 220)    # Canvas #f4a8b8
BLUSH_HAPPY = (243, 139, 168, 232)
WHITE = (255, 255, 255, 255)
MOUTH_RED = (184, 53, 38, 255)
STAR_GOLD = (252, 168, 38, 255)


def cv(value: float) -> float:
    return value * CANVAS_TO_ASSET * SUPERSAMPLE


def point(x: float, y: float) -> tuple[float, float]:
    center = SIZE * SUPERSAMPLE / 2.0
    return center + cv(x), center + cv(y)


def quadratic(a, b, c, steps: int = 24):
    for index in range(steps + 1):
        t = index / steps
        inv = 1.0 - t
        yield (
            inv * inv * a[0] + 2.0 * inv * t * b[0] + t * t * c[0],
            inv * inv * a[1] + 2.0 * inv * t * b[1] + t * t * c[1],
        )


def rounded_line(draw: ImageDraw.ImageDraw, points, fill, width: float) -> None:
    pts = [(round(x), round(y)) for x, y in points]
    pixel_width = max(1, round(cv(width)))
    draw.line(pts, fill=fill, width=pixel_width, joint="curve")
    radius = pixel_width / 2.0
    for x, y in (pts[0], pts[-1]):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)


def ellipse(draw: ImageDraw.ImageDraw, x: float, y: float, rx: float, ry: float, fill, outline=None, width=1.0):
    cx, cy = point(x, y)
    box = (cx - cv(rx), cy - cv(ry), cx + cv(rx), cy + cv(ry))
    draw.ellipse(box, fill=fill, outline=outline, width=max(1, round(cv(width))))


def draw_blush(draw: ImageDraw.ImageDraw, happy: bool = False) -> None:
    color = BLUSH_HAPPY if happy else BLUSH
    for side in (-1, 1):
        center_x = side * 22.88
        ellipse(draw, center_x, 2.08, 8.5 * (1.12 if happy else 1.0), 4.2 * (1.12 if happy else 1.0), color)
        # The small white slash is present in the Canvas version and keeps the
        # blush soft instead of reading as a flat rectangular sticker.
        start = point(center_x - side * 2.5, -0.42)
        end = point(center_x - side * 0.5, 4.58)
        rounded_line(draw, [start, end], (255, 255, 255, 150), 1.2)


def draw_brow(draw: ImageDraw.ImageDraw, center_x: float, lift: float = 0.0, tilt: float = 0.0) -> None:
    center_y = -14.56 - lift
    radians = math.radians(tilt)
    cos_a, sin_a = math.cos(radians), math.sin(radians)

    def rotate(local_x: float, local_y: float):
        x = center_x + local_x * cos_a - local_y * sin_a
        y = center_y + local_x * sin_a + local_y * cos_a
        return point(x, y)

    samples = []
    for index in range(25):
        t = index / 24.0
        x = -6.5 + 13.0 * t
        y = -3.64 * math.sin(math.pi * t)
        samples.append(rotate(x, y))
    rounded_line(draw, samples, INK, 4.0)


def draw_brows(draw: ImageDraw.ImageDraw, *, worried: bool = False) -> None:
    if worried:
        draw_brow(draw, -16.64, lift=-1.0, tilt=15.0)
        draw_brow(draw, 16.64, lift=-1.0, tilt=-15.0)
    else:
        draw_brow(draw, -16.64, tilt=-3.0)
        draw_brow(draw, 16.64, tilt=3.0)


def draw_dot_eyes(draw: ImageDraw.ImageDraw, *, tired: bool = False) -> None:
    eye_y = -4.16
    for center_x in (-14.56, 14.56):
        if tired:
            ellipse(draw, center_x, eye_y + 1.0, 4.6, 2.7, INK)
        else:
            ellipse(draw, center_x, eye_y, 4.6, 4.6, INK)
            ellipse(draw, center_x - 1.2, eye_y - 1.2, 1.2, 1.2, WHITE)


def draw_closed_eyes(draw: ImageDraw.ImageDraw, *, happy: bool = False) -> None:
    eye_y = -4.16
    for center_x in (-14.56, 14.56):
        samples = []
        for index in range(25):
            t = index / 24.0
            x = center_x - 4.25 + 8.5 * t
            curve = math.sin(math.pi * t) * 2.30
            y = eye_y - curve if happy else eye_y + curve
            samples.append(point(x, y))
        rounded_line(draw, samples, INK, 4.0)


def draw_cross_eyes(draw: ImageDraw.ImageDraw) -> None:
    for center_x in (-14.56, 14.56):
        rounded_line(draw, [point(center_x - 5, -9.16), point(center_x + 5, 0.84)], INK, 3.5)
        rounded_line(draw, [point(center_x - 5, 0.84), point(center_x + 5, -9.16)], INK, 3.5)


def draw_star(draw: ImageDraw.ImageDraw, center_x: float) -> None:
    cx, cy = point(center_x, -4.16)
    outer = cv(7.5)
    inner = outer * 0.40
    vertices = []
    for index in range(10):
        radius = outer if index % 2 == 0 else inner
        angle = -math.pi / 2.0 + index * math.pi / 5.0
        vertices.append((cx + math.cos(angle) * radius, cy + math.sin(angle) * radius))
    draw.polygon(vertices, fill=STAR_GOLD)
    rounded_line(draw, vertices + [vertices[0]], INK, 1.8)


def draw_star_eyes(draw: ImageDraw.ImageDraw) -> None:
    draw_star(draw, -14.56)
    draw_star(draw, 14.56)


def draw_cat_mouth(draw: ImageDraw.ImageDraw, *, narrow: bool = False) -> None:
    center_y = 8.32
    width = 6.2 if narrow else 7.0
    control_x = width * 0.64
    depth = 3.8 if narrow else 4.5
    left = list(quadratic(point(-width, center_y + 1.0), point(-control_x, center_y + depth), point(0, center_y)))
    right = list(quadratic(point(0, center_y), point(control_x, center_y + depth), point(width, center_y + 1.0)))
    rounded_line(draw, left, INK, 4.0)
    rounded_line(draw, right, INK, 4.0)


def draw_philtrum(draw: ImageDraw.ImageDraw, *, short: bool = False) -> None:
    end_y = 6.32 if short else 8.32
    rounded_line(draw, [point(0, -2.16), point(0, end_y)], INK, 4.0)


def draw_open_mouth(draw: ImageDraw.ImageDraw, *, tongue: bool = False, surprised: bool = False) -> None:
    center_y = 11.32
    radius_x = 9.5 if surprised else 7.5
    radius_top = 6.0 if surprised else 6.0
    radius_bottom = 11.0 if surprised else 9.0
    cx, cy = point(0, center_y)
    box = (cx - cv(radius_x), cy - cv(radius_top), cx + cv(radius_x), cy + cv(radius_bottom))
    draw.ellipse(box, fill=MOUTH_RED, outline=INK, width=max(1, round(cv(3.5))))
    if tongue:
        ellipse(draw, 0, center_y + 5.0, 3.3, 1.9, (255, 116, 105, 255))


def render(name: str) -> Image.Image:
    image = Image.new("RGBA", (SIZE * SUPERSAMPLE, SIZE * SUPERSAMPLE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    happy = name in {"happy", "happy_open", "star"}
    draw_blush(draw, happy=happy)

    if name in {"happy", "happy_open"}:
        draw_closed_eyes(draw, happy=True)
    elif name == "blink" or name == "sleep":
        if name == "blink":
            draw_brows(draw)
        draw_closed_eyes(draw, happy=False)
    elif name == "dizzy":
        draw_cross_eyes(draw)
    elif name == "star":
        draw_star_eyes(draw)
    elif name == "surprised":
        for center_x in (-14.56, 14.56):
            ellipse(draw, center_x, -4.16, 7.5, 7.5, WHITE, outline=INK, width=2.5)
            ellipse(draw, center_x, -4.16, 2.5, 2.5, INK)
        draw_brows(draw, worried=True)
    elif name in {"hungry", "worried"}:
        draw_brows(draw, worried=True)
        draw_dot_eyes(draw, tired=True)
    else:
        draw_brows(draw)
        draw_dot_eyes(draw)

    if name in {"open", "happy_open", "dizzy", "star", "surprised"}:
        draw_philtrum(draw, short=True)
        draw_open_mouth(draw, tongue=name in {"happy_open", "star"}, surprised=name == "surprised")
    else:
        draw_philtrum(draw)
        draw_cat_mouth(draw, narrow=name in {"sleep", "hungry"})

    return image.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    names = (
        "normal", "blink", "happy", "open", "happy_open", "dizzy",
        "star", "sleep", "hungry", "worried", "surprised",
    )
    for name in names:
        target = OUTPUT / f"{name}.png"
        render(name).save(target, optimize=True)
        print(target.relative_to(ROOT))


if __name__ == "__main__":
    main()
