"""Draw a title banner and a short title clip when Gemini cannot."""

from __future__ import annotations

import struct
import zlib

_WIDTH = 1200
_HEIGHT = 630
_CLIP_WIDTH = 640
_CLIP_HEIGHT = 360
_FRAMES = 8
# 5-bit rows, top to bottom. Lower case is drawn as capitals.
_FONT: dict[str, tuple[int, ...]] = {
    " ": (0, 0, 0, 0, 0, 0, 0),
    "A": (14, 17, 17, 31, 17, 17, 17),
    "B": (30, 17, 17, 30, 17, 17, 30),
    "C": (14, 17, 16, 16, 16, 17, 14),
    "D": (30, 17, 17, 17, 17, 17, 30),
    "E": (31, 16, 16, 30, 16, 16, 31),
    "F": (31, 16, 16, 30, 16, 16, 16),
    "G": (14, 17, 16, 23, 17, 17, 14),
    "H": (17, 17, 17, 31, 17, 17, 17),
    "I": (14, 4, 4, 4, 4, 4, 14),
    "J": (7, 2, 2, 2, 2, 18, 12),
    "K": (17, 18, 20, 24, 20, 18, 17),
    "L": (16, 16, 16, 16, 16, 16, 31),
    "M": (17, 27, 21, 21, 17, 17, 17),
    "N": (17, 17, 25, 21, 19, 17, 17),
    "O": (14, 17, 17, 17, 17, 17, 14),
    "P": (30, 17, 17, 30, 16, 16, 16),
    "Q": (14, 17, 17, 17, 21, 18, 13),
    "R": (30, 17, 17, 30, 20, 18, 17),
    "S": (14, 17, 16, 14, 1, 17, 14),
    "T": (31, 4, 4, 4, 4, 4, 4),
    "U": (17, 17, 17, 17, 17, 17, 14),
    "V": (17, 17, 17, 17, 17, 10, 4),
    "W": (17, 17, 17, 21, 21, 21, 10),
    "X": (17, 17, 10, 4, 10, 17, 17),
    "Y": (17, 17, 10, 4, 4, 4, 4),
    "Z": (31, 1, 2, 4, 8, 16, 31),
    "0": (14, 17, 19, 21, 25, 17, 14),
    "1": (4, 12, 4, 4, 4, 4, 14),
    "2": (14, 17, 1, 6, 8, 16, 31),
    "3": (14, 17, 1, 6, 1, 17, 14),
    "4": (2, 6, 10, 18, 31, 2, 2),
    "5": (31, 16, 30, 1, 1, 17, 14),
    "6": (6, 8, 16, 30, 17, 17, 14),
    "7": (31, 1, 2, 4, 8, 8, 8),
    "8": (14, 17, 17, 14, 17, 17, 14),
    "9": (14, 17, 17, 15, 1, 2, 12),
    "-": (0, 0, 0, 31, 0, 0, 0),
    ".": (0, 0, 0, 0, 0, 12, 12),
    ",": (0, 0, 0, 0, 0, 4, 8),
    "'": (4, 4, 8, 0, 0, 0, 0),
    ":": (0, 12, 12, 0, 12, 12, 0),
    "/": (1, 2, 4, 4, 4, 8, 16),
    "&": (8, 20, 20, 8, 21, 18, 13),
}


def draw_banner_png(title: str) -> bytes:
    pixels = _canvas(_WIDTH, _HEIGHT, _lines(title, _WIDTH, 8), 8, 0)
    return _png(_WIDTH, _HEIGHT, pixels)


def draw_title_clip(title: str) -> bytes:
    frames = [
        _canvas(_CLIP_WIDTH, _CLIP_HEIGHT, _lines(title, _CLIP_WIDTH, 4), 4, frame)
        for frame in range(_FRAMES)
    ]
    return _gif(_CLIP_WIDTH, _CLIP_HEIGHT, frames)


def _lines(title: str, width: int, scale: int) -> list[str]:
    words = ["".join(ch for ch in word.upper() if ch in _FONT) for word in title.split()]
    words = [word for word in words if word]
    if not words:
        words = ["POST"]
    max_chars = max(8, (width - 80) // (6 * scale))
    lines: list[str] = []
    current = ""
    for word in words:
        while len(word) > max_chars:
            lines.append(word[:max_chars])
            word = word[max_chars:]
        trial = word if not current else f"{current} {word}"
        if len(trial) <= max_chars:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:4]


def _canvas(width: int, height: int, lines: list[str], scale: int, frame: int) -> bytearray:
    pixels = bytearray([16, 23, 34] * width * height)
    _fill(pixels, width, 0, height - 18, width, 18, (153, 165, 255))
    bar_w = width // _FRAMES
    _fill(pixels, width, frame * bar_w, height - 18, bar_w, 18, (238, 242, 250))
    line_h = 9 * scale
    block_h = line_h * len(lines)
    top = max(36, (height - 18 - block_h) // 2)
    for index, line in enumerate(lines):
        text_w = len(line) * 6 * scale
        _text(pixels, width, line, max(24, (width - text_w) // 2), top + index * line_h, scale)
    return pixels


def _fill(pixels: bytearray, width: int, x: int, y: int, w: int, h: int, color: tuple[int, int, int]) -> None:
    height = len(pixels) // (width * 3)
    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(width, x + w)
    y1 = min(height, y + h)
    for row in range(y0, y1):
        start = (row * width + x0) * 3
        for col in range(x1 - x0):
            pixels[start + col * 3 : start + col * 3 + 3] = bytes(color)


def _text(pixels: bytearray, width: int, text: str, x: int, y: int, scale: int) -> None:
    cursor = x
    for char in text:
        rows = _FONT.get(char, _FONT[" "])
        for row, bits in enumerate(rows):
            for col in range(5):
                if bits & (1 << (4 - col)):
                    _fill(pixels, width, cursor + col * scale, y + row * scale, scale, scale, (238, 242, 250))
        cursor += 6 * scale


def _png(width: int, height: int, pixels: bytearray) -> bytes:
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)
        raw.extend(pixels[y * stride : (y + 1) * stride])

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")


def _gif(width: int, height: int, frames: list[bytearray]) -> bytes:
    palette = bytes(
        [
            16, 23, 34,
            238, 242, 250,
            153, 165, 255,
            0, 0, 0,
        ]
        + [0] * (16 * 3 - 12)
    )
    out = bytearray(b"GIF89a")
    out.extend(struct.pack("<HHBBB", width, height, 0x83, 0, 0))
    out.extend(palette)
    out.extend(b"\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00")
    for frame in frames:
        indexes = _indexes(frame)
        out.extend(b"\x21\xf9\x04\x04\x19\x00\x00\x00")
        out.extend(struct.pack("<BHHHHB", 0x2C, 0, 0, width, height, 0))
        packed = _lzw(indexes, 4)
        out.append(4)
        for start in range(0, len(packed), 255):
            block = packed[start : start + 255]
            out.append(len(block))
            out.extend(block)
        out.append(0)
    out.append(0x3B)
    return bytes(out)


def _indexes(pixels: bytearray) -> bytes:
    indexes = bytearray(len(pixels) // 3)
    for index in range(len(indexes)):
        red, green, blue = pixels[index * 3 : index * 3 + 3]
        if red > 200 and green > 200:
            indexes[index] = 1
        elif blue > 150 and red > 100:
            indexes[index] = 2
        else:
            indexes[index] = 0
    return bytes(indexes)


def _lzw(indexes: bytes, min_code_size: int) -> bytes:
    clear = 1 << min_code_size
    end = clear + 1
    code_size = min_code_size + 1
    next_code = end + 1
    table = {bytes([i]): i for i in range(clear)}
    bit_buf = 0
    bit_len = 0
    out = bytearray()

    def write(code: int) -> None:
        nonlocal bit_buf, bit_len
        bit_buf |= code << bit_len
        bit_len += code_size
        while bit_len >= 8:
            out.append(bit_buf & 0xFF)
            bit_buf >>= 8
            bit_len -= 8

    def reset() -> None:
        nonlocal code_size, next_code, table
        write(clear)
        table = {bytes([i]): i for i in range(clear)}
        code_size = min_code_size + 1
        next_code = end + 1

    reset()
    prefix = b""
    for value in indexes:
        candidate = prefix + bytes([value])
        if candidate in table:
            prefix = candidate
            continue
        write(table[prefix])
        if next_code < 4096:
            table[candidate] = next_code
            next_code += 1
            if code_size < 12 and next_code > (1 << code_size):
                code_size += 1
        else:
            reset()
        prefix = bytes([value])
    if prefix:
        write(table[prefix])
    write(end)
    if bit_len:
        out.append(bit_buf & 0xFF)
    return bytes(out)
