from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT / "assets"
SOURCE_PNG = ASSETS_DIR / "AppIcon.png"
ICONSET_DIR = ASSETS_DIR / "AppIcon.iconset"
ICNS_PATH = ASSETS_DIR / "AppIcon.icns"
APP_RESOURCE_DIRS = [
    ROOT / "姓名学取名工具.app" / "Contents" / "Resources",
    ROOT / "姓名学取名工具独立版.app" / "Contents" / "Resources",
]

FONT_CANDIDATES = [
    Path("/System/Library/Fonts/Supplemental/Songti.ttc"),
    Path("/System/Library/Fonts/STHeiti Medium.ttc"),
    Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
]


def scaled(value: int, scale: int) -> int:
    return value * scale


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def vertical_gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    gradient = Image.new("RGBA", size)
    draw = ImageDraw.Draw(gradient)
    height = size[1]
    for y in range(height):
        t = y / max(height - 1, 1)
        color = tuple(round(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        draw.line((0, y, size[0], y), fill=color + (255,))
    return gradient


def draw_shadow(canvas: Image.Image, rect: tuple[int, int, int, int], radius: int, alpha: int, blur: int, y_offset: int) -> None:
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow_mask = Image.new("L", canvas.size, 0)
    shadow_draw = ImageDraw.Draw(shadow_mask)
    shifted = (rect[0], rect[1] + y_offset, rect[2], rect[3] + y_offset)
    shadow_draw.rounded_rectangle(shifted, radius=radius, fill=alpha)
    shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(blur))
    shadow.putalpha(shadow_mask)
    canvas.alpha_composite(shadow)


def font_path() -> Path:
    for candidate in FONT_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("No Chinese system font was found.")


def draw_icon() -> None:
    scale = 4
    size = scaled(1024, scale)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    def s(value: int) -> int:
        return scaled(value, scale)

    base_rect = (s(82), s(82), s(942), s(942))
    draw_shadow(canvas, base_rect, s(190), alpha=78, blur=s(34), y_offset=s(24))

    base = vertical_gradient((base_rect[2] - base_rect[0], base_rect[3] - base_rect[1]), (249, 247, 239), (226, 244, 244))
    base_mask = rounded_mask(base.size, s(190))
    canvas.paste(base, base_rect[:2], base_mask)
    draw.rounded_rectangle(base_rect, radius=s(190), outline=(255, 255, 255, 190), width=s(8))

    sheet_rect = (s(178), s(192), s(846), s(826))
    draw_shadow(canvas, sheet_rect, s(66), alpha=42, blur=s(18), y_offset=s(12))
    draw.rounded_rectangle(sheet_rect, radius=s(66), fill=(255, 255, 255, 238), outline=(207, 211, 204, 160), width=s(3))

    grid_left, grid_top, cell = s(228), s(244), s(142)
    line_color = (83, 93, 93, 86)
    for row in range(4):
        for col in range(4):
            x0 = grid_left + col * cell
            y0 = grid_top + row * cell
            fill = (250, 252, 248, 216)
            if (row, col) in {(0, 1), (1, 0), (2, 0)}:
                fill = (106, 189, 214, 210)
            if (row, col) in {(1, 3), (2, 3), (3, 2)}:
                fill = (246, 184, 42, 226)
            draw.rounded_rectangle((x0, y0, x0 + cell, y0 + cell), radius=s(12), fill=fill, outline=line_color, width=s(3))

    brush_rect = (s(248), s(566), s(776), s(676))
    brush = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    brush_draw = ImageDraw.Draw(brush)
    brush_draw.rounded_rectangle(brush_rect, radius=s(55), fill=(242, 182, 42, 212))
    brush = brush.filter(ImageFilter.GaussianBlur(s(1)))
    canvas.alpha_composite(brush)

    name_font = ImageFont.truetype(str(font_path()), s(450))
    text = "名"
    text_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    text_draw = ImageDraw.Draw(text_layer)
    bbox = text_draw.textbbox((0, 0), text, font=name_font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = s(512) - text_w // 2 - bbox[0]
    y = s(512) - text_h // 2 - bbox[1] + s(22)
    text_draw.text((x + s(10), y + s(13)), text, font=name_font, fill=(255, 255, 255, 170))
    text_draw.text((x, y), text, font=name_font, fill=(31, 45, 49, 255))
    canvas.alpha_composite(text_layer)

    accent = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    accent_draw = ImageDraw.Draw(accent)
    accent_draw.ellipse((s(724), s(274), s(788), s(338)), fill=(246, 184, 42, 235))
    accent_draw.ellipse((s(738), s(288), s(774), s(324)), fill=(255, 248, 219, 150))
    accent_draw.rounded_rectangle((s(256), s(720), s(392), s(754)), radius=s(17), fill=(106, 189, 214, 235))
    accent_draw.rounded_rectangle((s(412), s(720), s(548), s(754)), radius=s(17), fill=(246, 184, 42, 235))
    canvas.alpha_composite(accent)

    output = canvas.resize((1024, 1024), Image.Resampling.LANCZOS)
    ASSETS_DIR.mkdir(exist_ok=True)
    output.save(SOURCE_PNG)


def build_iconset() -> None:
    if ICONSET_DIR.exists():
        shutil.rmtree(ICONSET_DIR)
    ICONSET_DIR.mkdir(parents=True)

    source = Image.open(SOURCE_PNG)
    sizes = [
        ("icon_16x16.png", 16),
        ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32),
        ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256),
        ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512),
        ("icon_512x512@2x.png", 1024),
    ]
    for filename, output_size in sizes:
        resized = source.resize((output_size, output_size), Image.Resampling.LANCZOS)
        resized.save(ICONSET_DIR / filename)

    subprocess.run(["iconutil", "--convert", "icns", "--output", str(ICNS_PATH), str(ICONSET_DIR)], check=True)


def copy_to_apps() -> None:
    for resource_dir in APP_RESOURCE_DIRS:
        if resource_dir.exists():
            shutil.copyfile(ICNS_PATH, resource_dir / "AppIcon.icns")


def main() -> None:
    draw_icon()
    build_iconset()
    copy_to_apps()
    print(f"Generated {SOURCE_PNG}")
    print(f"Generated {ICNS_PATH}")


if __name__ == "__main__":
    main()
