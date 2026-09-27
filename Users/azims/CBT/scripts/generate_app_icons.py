"""
scripts/generate_app_icons.py
==============================
Generates native high-resolution app icon PNG (256x256) and ICO files
for Windows and Linux / Ubuntu application packaging.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = REPO_ROOT / "frontend" / "public"


def create_png_rgba(width: int, height: int, pixels: list[tuple[int, int, int, int]]) -> bytes:
    """Creates a raw PNG file from RGBA pixel tuples."""
    raw_data = bytearray()
    for y in range(height):
        raw_data.append(0)  # Filter type None
        for x in range(width):
            r, g, b, a = pixels[y * width + x]
            raw_data.extend((r, g, b, a))

    def make_chunk(chunk_type: bytes, data: bytes) -> bytes:
        length = len(data)
        crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        return struct.pack(">I", length) + chunk_type + data + struct.pack(">I", crc)

    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    compressed = zlib.compress(bytes(raw_data), 9)

    png = (
        b"\x89PNG\r\n\x1a\n"
        + make_chunk(b"IHDR", ihdr_data)
        + make_chunk(b"IDAT", compressed)
        + make_chunk(b"IEND", b"")
    )
    return png


def create_ico(png_bytes: bytes, width: int = 256, height: int = 256) -> bytes:
    """Wraps a PNG inside a standard Windows ICO container."""
    # ICO header: Reserved(2), Type=1(2), ImageCount=1(2)
    header = struct.pack("<HHH", 0, 1, 1)
    # Directory entry: Width(1), Height(1), Colors(1), Reserved(1), Planes(2), BPP(2), BytesInRes(4), ImageOffset(4)
    w_byte = 0 if width >= 256 else width
    h_byte = 0 if height >= 256 else height
    entry = struct.pack(
        "<BBBBHHII",
        w_byte,
        h_byte,
        0,  # 0 color count
        0,  # reserved
        1,  # color planes
        32,  # 32 bpp
        len(png_bytes),
        6 + 16,  # Offset where image data starts
    )
    return header + entry + png_bytes


def generate_cbt_icon_pixels(size: int = 256) -> list[tuple[int, int, int, int]]:
    """Renders a sleek obsidian-dark background with neon cyan & emerald quant emblem."""
    pixels = []
    center = size / 2.0
    radius = size * 0.44

    for y in range(size):
        for x in range(size):
            dx = x - center
            dy = y - center
            dist = (dx * dx + dy * dy) ** 0.5

            # Outer rounded square mask
            corner_radius = size * 0.22
            # Bounding box for rounded rectangle
            inset = size * 0.05
            in_x = max(0, abs(dx) - (center - inset - corner_radius))
            in_y = max(0, abs(dy) - (center - inset - corner_radius))
            corner_dist = (in_x * in_x + in_y * in_y) ** 0.5

            if corner_dist > corner_radius:
                # Fully transparent outside
                pixels.append((0, 0, 0, 0))
                continue

            # Base gradient: deep obsidian background (#0B0E14 to #161B26)
            t = (x + y) / (2.0 * size)
            r = int(11 * (1 - t) + 22 * t)
            g = int(14 * (1 - t) + 27 * t)
            b = int(20 * (1 - t) + 38 * t)
            a = 255

            # Border glow (neon cyan/slate)
            if corner_dist > corner_radius - 4:
                r, g, b = 35, 43, 62

            # Quant Grid Lines
            if y % 32 == 0 and abs(dx) < radius * 0.8:
                r, g, b = min(255, r + 20), min(255, g + 25), min(255, b + 35)

            # Central Emblem: Cyan Impulsive Bar & Emerald Bullish Bar
            # Bar 1: Green Candlestick (Left)
            if 65 <= x <= 85 and 90 <= y <= 190:
                # Candle body
                if 115 <= y <= 165:
                    r, g, b = 0, 255, 157
                elif 72 <= x <= 78:  # Wick
                    r, g, b = 0, 255, 157

            # Bar 2: Center Impulsive Neon Cyan Candlestick
            if 116 <= x <= 140 and 55 <= y <= 210:
                if 80 <= y <= 185:
                    r, g, b = 0, 240, 255
                elif 125 <= x <= 131:  # Wick
                    r, g, b = 0, 240, 255

            # Bar 3: Magenta/Red Bearish Retracement (Right)
            if 171 <= x <= 191 and 100 <= y <= 195:
                if 125 <= y <= 170:
                    r, g, b = 255, 59, 105
                elif 178 <= x <= 184:  # Wick
                    r, g, b = 255, 59, 105

            # Diamond nodes in central cluster
            if abs(dx) + abs(dy) < 18:
                r, g, b = 255, 255, 255

            pixels.append((r, g, b, a))

    return pixels


def main() -> None:
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    pixels = generate_cbt_icon_pixels(256)
    png_data = create_png_rgba(256, 256, pixels)
    ico_data = create_ico(png_data, 256, 256)

    png_path = PUBLIC_DIR / "favicon.png"
    ico_path = PUBLIC_DIR / "favicon.ico"
    icon_png_path = PUBLIC_DIR / "icon.png"

    with open(png_path, "wb") as f:
        f.write(png_data)
    with open(icon_png_path, "wb") as f:
        f.write(png_data)
    with open(ico_path, "wb") as f:
        f.write(ico_data)

    print(f"Generated icons:\n- {png_path}\n- {icon_png_path}\n- {ico_path}")


if __name__ == "__main__":
    main()
