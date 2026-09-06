"""packaging/generate_icons.py — Generate PWA app icons for SKY.

Creates crisp PNG icons in web/static/icons/:
  - icon-180.png (Apple touch icon 180x180)
  - icon-192.png (Android / PWA 192x192)
  - icon-512.png (PWA standard / splash 512x512)
  - icon-maskable-512.png (Adaptive maskable icon 512x512 with safe margin)
"""

import math
import struct
import zlib
from pathlib import Path

OUT_DIR = Path(__file__).parent.parent / "web" / "static" / "icons"


def _write_png(path: Path, width: int, height: int, rgba_pixels: bytes) -> None:
    """Write an uncompressed or zlib-compressed 32-bit RGBA PNG."""

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        content = chunk_type + data
        crc = zlib.crc32(content) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + content + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw_lines = bytearray()
    stride = width * 4
    for y in range(height):
        raw_lines.append(0)  # filter type 0
        raw_lines.extend(rgba_pixels[y * stride : (y + 1) * stride])

    compressed = zlib.compress(bytes(raw_lines), 9)

    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", compressed)
        + _chunk(b"IEND", b"")
    )

    path.write_bytes(png_bytes)


def render_sky_icon(size: int, maskable: bool = False) -> bytes:
    """Render a high-quality RGBA icon buffer for SKY."""
    pixels = bytearray(size * size * 4)

    center = size / 2.0
    radius = size * 0.48 if not maskable else size * 0.40  # safe margin for maskable

    # Palette
    bg_r, bg_g, bg_b = 0x07, 0x0B, 0x14  # Deep navy #070b14
    bg2_r, bg2_g, bg2_b = 0x0E, 0x18, 0x2E  # Slate blue #0e182e
    cyan_r, cyan_g, cyan_b = 0x38, 0xBD, 0xF8  # Cyan #38bdf8
    emerald_r, emerald_g, emerald_b = 0x34, 0xD3, 0x99  # Emerald #34d399
    white_r, white_g, white_b = 0xF8, 0xFA, 0xFC

    for y in range(size):
        for x in range(size):
            idx = (y * size + x) * 4
            dx = x - center
            dy = y - center
            dist = math.sqrt(dx * dx + dy * dy)

            if maskable:
                # Full square fill for maskable icon
                r, g, b, a = bg_r, bg_g, bg_b, 255
            else:
                # Rounded square mask
                corner_radius = size * 0.22
                qx = abs(dx) - (center - corner_radius)
                qy = abs(dy) - (center - corner_radius)
                q_dist = (
                    math.sqrt(max(0, qx) ** 2 + max(0, qy) ** 2)
                    if qx > 0 and qy > 0
                    else max(qx, qy)
                )
                if q_dist > corner_radius:
                    pixels[idx : idx + 4] = bytes([0, 0, 0, 0])
                    continue
                r, g, b, a = bg_r, bg_g, bg_b, 255

            # Subtle radial background glow from top center
            top_dist = math.sqrt((x - center) ** 2 + (y - center * 0.4) ** 2)
            glow = max(0.0, 1.0 - top_dist / (size * 0.8))
            r = int(r + glow * 15)
            g = int(g + glow * 25)
            b = int(b + glow * 45)

            # Draw stylized candlestick chart bars
            # Candle 1: x in [0.28..0.38], y in [0.45..0.72] (emerald)
            # Candle 2: x in [0.44..0.54], y in [0.32..0.65] (cyan)
            # Candle 3: x in [0.60..0.70], y in [0.22..0.52] (emerald)
            norm_x = x / float(size)
            norm_y = y / float(size)

            # Wicks
            in_wick = False
            if 0.325 <= norm_x <= 0.335 and 0.38 <= norm_y <= 0.78:
                in_wick = True
                wr, wg, wb = emerald_r, emerald_g, emerald_b
            elif 0.485 <= norm_x <= 0.495 and 0.25 <= norm_y <= 0.70:
                in_wick = True
                wr, wg, wb = cyan_r, cyan_g, cyan_b
            elif 0.645 <= norm_x <= 0.655 and 0.16 <= norm_y <= 0.58:
                in_wick = True
                wr, wg, wb = emerald_r, emerald_g, emerald_b

            if in_wick:
                r = wr
                g = wg
                b = wb

            # Candle bodies
            in_body = False
            if 0.30 <= norm_x <= 0.36 and 0.46 <= norm_y <= 0.70:
                in_body = True
                br, bg_c, bb = emerald_r, emerald_g, emerald_b
            elif 0.46 <= norm_x <= 0.52 and 0.32 <= norm_y <= 0.62:
                in_body = True
                br, bg_c, bb = cyan_r, cyan_g, cyan_b
            elif 0.62 <= norm_x <= 0.68 and 0.22 <= norm_y <= 0.50:
                in_body = True
                br, bg_c, bb = emerald_r, emerald_g, emerald_b

            if in_body:
                r, g, b = br, bg_c, bb

            # Overlay glowing sky arch at top
            arch_dy = norm_y - (0.35 + 0.15 * math.sin((norm_x - 0.2) * math.pi / 0.6))
            if 0.20 <= norm_x <= 0.80 and abs(arch_dy) < 0.015:
                r, g, b = cyan_r, cyan_g, cyan_b

            pixels[idx : idx + 4] = bytes([min(255, r), min(255, g), min(255, b), a])

    return bytes(pixels)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sizes = [
        ("icon-180.png", 180, False),
        ("icon-192.png", 192, False),
        ("icon-512.png", 512, False),
        ("icon-maskable-512.png", 512, True),
    ]

    for fname, size, maskable in sizes:
        path = OUT_DIR / fname
        buf = render_sky_icon(size, maskable=maskable)
        _write_png(path, size, size, buf)
        print(f"Generated {fname} ({size}x{size}, {len(buf)} bytes)")


if __name__ == "__main__":
    main()
