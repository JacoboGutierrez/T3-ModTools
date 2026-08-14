#!/usr/bin/env python3
"""Small standard-library texture converters used by T3-ModTools glTF export.

Supported input variants:
- DDS BC1 / DXT1
- DDS BC2 / DXT3
- DDS BC3 / DXT5
- uncompressed true-color TGA (24/32-bit)
- RLE true-color TGA (24/32-bit)
- uncompressed or RLE grayscale TGA (8-bit)

The output is an RGBA PNG written with the Python standard library only.
"""
from __future__ import annotations

import binascii
import struct
import zlib
from pathlib import Path
from typing import Optional


class TextureConversionError(ValueError):
    pass


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)
    )


def write_png_rgba(path: Path, width: int, height: int, rgba: bytes) -> None:
    if width <= 0 or height <= 0:
        raise TextureConversionError("Invalid image dimensions")
    expected = width * height * 4
    if len(rgba) != expected:
        raise TextureConversionError(f"Invalid RGBA payload length: expected {expected}, got {len(rgba)}")
    scanlines = bytearray()
    stride = width * 4
    for y in range(height):
        scanlines.append(0)  # PNG filter type: None
        start = y * stride
        scanlines.extend(rgba[start : start + stride])
    png = bytearray(b"\x89PNG\r\n\x1a\n")
    png.extend(_png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)))
    png.extend(_png_chunk(b"IDAT", zlib.compress(bytes(scanlines), level=9)))
    png.extend(_png_chunk(b"IEND", b""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(png))


def _rgb565(value: int) -> tuple[int, int, int]:
    r = (value >> 11) & 0x1F
    g = (value >> 5) & 0x3F
    b = value & 0x1F
    return (
        (r << 3) | (r >> 2),
        (g << 2) | (g >> 4),
        (b << 3) | (b >> 2),
    )


def _dxt_color_palette(c0: int, c1: int, force_four_color: bool) -> list[tuple[int, int, int, int]]:
    r0, g0, b0 = _rgb565(c0)
    r1, g1, b1 = _rgb565(c1)
    colors = [(r0, g0, b0, 255), (r1, g1, b1, 255)]
    if c0 > c1 or force_four_color:
        colors.extend([
            ((2 * r0 + r1) // 3, (2 * g0 + g1) // 3, (2 * b0 + b1) // 3, 255),
            ((r0 + 2 * r1) // 3, (g0 + 2 * g1) // 3, (b0 + 2 * b1) // 3, 255),
        ])
    else:
        colors.extend([
            ((r0 + r1) // 2, (g0 + g1) // 2, (b0 + b1) // 2, 255),
            (0, 0, 0, 0),
        ])
    return colors


def _dxt5_alpha_palette(a0: int, a1: int) -> list[int]:
    values = [a0, a1]
    if a0 > a1:
        values.extend([
            (6 * a0 + 1 * a1) // 7,
            (5 * a0 + 2 * a1) // 7,
            (4 * a0 + 3 * a1) // 7,
            (3 * a0 + 4 * a1) // 7,
            (2 * a0 + 5 * a1) // 7,
            (1 * a0 + 6 * a1) // 7,
        ])
    else:
        values.extend([
            (4 * a0 + 1 * a1) // 5,
            (3 * a0 + 2 * a1) // 5,
            (2 * a0 + 3 * a1) // 5,
            (1 * a0 + 4 * a1) // 5,
            0,
            255,
        ])
    return values


def decode_dds(data: bytes) -> tuple[int, int, bytes]:
    if len(data) < 128 or data[:4] != b"DDS ":
        raise TextureConversionError("Not a DDS file")
    header_size = struct.unpack_from("<I", data, 4)[0]
    if header_size != 124:
        raise TextureConversionError(f"Unsupported DDS header size: {header_size}")
    height = struct.unpack_from("<I", data, 12)[0]
    width = struct.unpack_from("<I", data, 16)[0]
    pixel_format_size = struct.unpack_from("<I", data, 76)[0]
    if pixel_format_size != 32:
        raise TextureConversionError(f"Unsupported DDS pixel format header size: {pixel_format_size}")
    pixel_format_flags = struct.unpack_from("<I", data, 80)[0]
    fourcc = data[84:88]
    rgb_bits = struct.unpack_from("<I", data, 88)[0]
    r_mask, g_mask, b_mask, a_mask = struct.unpack_from("<IIII", data, 92)

    if fourcc == b"DX10":
        raise TextureConversionError("DDS DX10 headers are not supported")

    output = bytearray(width * height * 4)

    if fourcc in {b"DXT1", b"DXT3", b"DXT5"}:
        block_size = 8 if fourcc == b"DXT1" else 16
        blocks_x = (width + 3) // 4
        blocks_y = (height + 3) // 4
        offset = 128
        required = blocks_x * blocks_y * block_size
        if len(data) < offset + required:
            raise TextureConversionError("DDS file is truncated")

        for block_y in range(blocks_y):
            for block_x in range(blocks_x):
                block = data[offset : offset + block_size]
                offset += block_size
                alpha_values = [255] * 16
                color_offset = 0
                force_four = False

                if fourcc == b"DXT3":
                    alpha_bits = int.from_bytes(block[:8], "little")
                    alpha_values = [((alpha_bits >> (4 * i)) & 0xF) * 17 for i in range(16)]
                    color_offset = 8
                    force_four = True
                elif fourcc == b"DXT5":
                    a0, a1 = block[0], block[1]
                    palette = _dxt5_alpha_palette(a0, a1)
                    alpha_indices = int.from_bytes(block[2:8], "little")
                    alpha_values = [palette[(alpha_indices >> (3 * i)) & 0x7] for i in range(16)]
                    color_offset = 8
                    force_four = True

                c0, c1, color_indices = struct.unpack_from("<HHI", block, color_offset)
                palette = _dxt_color_palette(c0, c1, force_four)
                for local_y in range(4):
                    y = block_y * 4 + local_y
                    if y >= height:
                        continue
                    for local_x in range(4):
                        x = block_x * 4 + local_x
                        if x >= width:
                            continue
                        pixel_index = local_y * 4 + local_x
                        color_index = (color_indices >> (2 * pixel_index)) & 0x3
                        r, g, b, color_alpha = palette[color_index]
                        alpha = (alpha_values[pixel_index] * color_alpha) // 255
                        dst = (y * width + x) * 4
                        output[dst : dst + 4] = bytes((r, g, b, alpha))
        return width, height, bytes(output)

    # Legacy uncompressed RGB(A) DDS.
    DDPF_RGB = 0x40
    if not (pixel_format_flags & DDPF_RGB) or rgb_bits not in {24, 32}:
        fourcc_text = fourcc.decode("ascii", errors="replace")
        raise TextureConversionError(f"Unsupported DDS format: {fourcc_text!r}, {rgb_bits}-bit")

    def mask_value(pixel: int, mask: int, default: int) -> int:
        if not mask:
            return default
        shift = (mask & -mask).bit_length() - 1
        maximum = mask >> shift
        raw = (pixel & mask) >> shift
        return (raw * 255 + maximum // 2) // maximum if maximum else default

    bytes_per_pixel = rgb_bits // 8
    pitch = struct.unpack_from("<I", data, 20)[0]
    row_size = pitch if pitch >= width * bytes_per_pixel else width * bytes_per_pixel
    offset = 128
    if len(data) < offset + row_size * height:
        raise TextureConversionError("Uncompressed DDS file is truncated")
    for y in range(height):
        row = data[offset + y * row_size : offset + y * row_size + width * bytes_per_pixel]
        for x in range(width):
            raw = int.from_bytes(row[x * bytes_per_pixel : (x + 1) * bytes_per_pixel], "little")
            dst = (y * width + x) * 4
            output[dst : dst + 4] = bytes((
                mask_value(raw, r_mask, 0),
                mask_value(raw, g_mask, 0),
                mask_value(raw, b_mask, 0),
                mask_value(raw, a_mask, 255),
            ))
    return width, height, bytes(output)


def decode_tga(data: bytes) -> tuple[int, int, bytes]:
    if len(data) < 18:
        raise TextureConversionError("TGA file is too short")
    id_length = data[0]
    color_map_type = data[1]
    image_type = data[2]
    width = struct.unpack_from("<H", data, 12)[0]
    height = struct.unpack_from("<H", data, 14)[0]
    pixel_depth = data[16]
    descriptor = data[17]
    if width <= 0 or height <= 0:
        raise TextureConversionError("Invalid TGA dimensions")
    if color_map_type != 0:
        raise TextureConversionError("Color-mapped TGA files are not supported")
    if image_type not in {2, 3, 10, 11}:
        raise TextureConversionError(f"Unsupported TGA image type: {image_type}")
    grayscale = image_type in {3, 11}
    rle = image_type in {10, 11}
    if grayscale and pixel_depth != 8:
        raise TextureConversionError(f"Unsupported grayscale TGA depth: {pixel_depth}")
    if not grayscale and pixel_depth not in {24, 32}:
        raise TextureConversionError(f"Unsupported true-color TGA depth: {pixel_depth}")

    bytes_per_pixel = pixel_depth // 8
    offset = 18 + id_length
    total_pixels = width * height
    raw_pixels: list[bytes] = []

    def read_pixel() -> bytes:
        nonlocal offset
        if offset + bytes_per_pixel > len(data):
            raise TextureConversionError("TGA file is truncated")
        pixel = data[offset : offset + bytes_per_pixel]
        offset += bytes_per_pixel
        return pixel

    if not rle:
        for _ in range(total_pixels):
            raw_pixels.append(read_pixel())
    else:
        while len(raw_pixels) < total_pixels:
            if offset >= len(data):
                raise TextureConversionError("TGA RLE data is truncated")
            packet = data[offset]
            offset += 1
            count = (packet & 0x7F) + 1
            if packet & 0x80:
                pixel = read_pixel()
                raw_pixels.extend([pixel] * count)
            else:
                raw_pixels.extend(read_pixel() for _ in range(count))
        raw_pixels = raw_pixels[:total_pixels]

    top_origin = bool(descriptor & 0x20)
    right_origin = bool(descriptor & 0x10)
    output = bytearray(total_pixels * 4)
    for source_index, pixel in enumerate(raw_pixels):
        source_y, source_x = divmod(source_index, width)
        y = source_y if top_origin else height - 1 - source_y
        x = width - 1 - source_x if right_origin else source_x
        if grayscale:
            r = g = b = pixel[0]
            a = 255
        else:
            b, g, r = pixel[:3]
            a = pixel[3] if bytes_per_pixel == 4 else 255
        dst = (y * width + x) * 4
        output[dst : dst + 4] = bytes((r, g, b, a))
    return width, height, bytes(output)


def convert_texture_bytes_to_png(data: bytes, suffix: str, destination: Path) -> Path:
    extension = suffix.lower()
    if extension == ".dds":
        width, height, rgba = decode_dds(data)
    elif extension == ".tga":
        width, height, rgba = decode_tga(data)
    else:
        raise TextureConversionError(f"Unsupported source extension: {suffix}")
    write_png_rgba(destination, width, height, rgba)
    return destination


def convert_texture_file_to_png(source: Path, destination: Optional[Path] = None) -> Path:
    destination = destination or source.with_suffix(".png")

    # Pillow is optional. When it is already installed, use its native decoder as
    # a faster path. T3-ModTools does not require Pillow because the standard-
    # library DDS/TGA fallback below supports the formats used by the tested game.
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        Image = None  # type: ignore
    if Image is not None:
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(source) as image:
                image.convert("RGBA").save(destination, format="PNG", optimize=True)
            return destination
        except Exception:
            # Fall through to the self-contained decoder for portability.
            pass

    return convert_texture_bytes_to_png(source.read_bytes(), source.suffix, destination)
