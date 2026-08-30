"""Build the packaged Windows icon from the approved branding master PNG."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

from PIL import Image


ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _normalized_canvas(source: Image.Image, canvas_size: int = 1024) -> Image.Image:
    rgba = source.convert("RGBA")
    alpha_box = rgba.getchannel("A").getbbox()
    if alpha_box is None:
        raise ValueError("The source image is fully transparent.")

    left, top, right, bottom = alpha_box
    subject_size = max(right - left, bottom - top)
    padding = max(1, round(subject_size * 0.055))
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(rgba.width, right + padding)
    bottom = min(rgba.height, bottom + padding)
    cropped = rgba.crop((left, top, right, bottom))

    square_size = max(cropped.size)
    square = Image.new("RGBA", (square_size, square_size), (0, 0, 0, 0))
    square.alpha_composite(
        cropped,
        ((square_size - cropped.width) // 2, (square_size - cropped.height) // 2),
    )
    return square.resize((canvas_size, canvas_size), Image.Resampling.LANCZOS)


def _ico_directory_sizes(path: Path) -> tuple[int, ...]:
    data = path.read_bytes()
    reserved, image_type, count = struct.unpack_from("<HHH", data, 0)
    if reserved != 0 or image_type != 1:
        raise ValueError(f"Not an ICO file: {path}")
    sizes: list[int] = []
    for index in range(count):
        width, height = struct.unpack_from("<BB", data, 6 + index * 16)
        width = 256 if width == 0 else width
        height = 256 if height == 0 else height
        if width != height:
            raise ValueError(f"ICO frame is not square: {width}x{height}")
        sizes.append(width)
    return tuple(sizes)


def build_icon(source_path: Path, png_path: Path, ico_path: Path) -> None:
    with Image.open(source_path) as source:
        normalized = _normalized_canvas(source)

    png_path.parent.mkdir(parents=True, exist_ok=True)
    ico_path.parent.mkdir(parents=True, exist_ok=True)
    normalized.save(png_path, format="PNG", optimize=True)
    normalized.save(ico_path, format="ICO", sizes=[(size, size) for size in ICON_SIZES])

    actual_sizes = _ico_directory_sizes(ico_path)
    if actual_sizes != ICON_SIZES:
        raise RuntimeError(f"ICO frames {actual_sizes!r} do not match {ICON_SIZES!r}")


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=project_root / "assets" / "branding" / "colin_tts_icon_master.png",
    )
    parser.add_argument(
        "--png",
        type=Path,
        default=project_root / "src" / "omni_tts_shared" / "assets" / "colin_tts_icon.png",
    )
    parser.add_argument(
        "--ico",
        type=Path,
        default=project_root / "src" / "omni_tts_shared" / "assets" / "colin_tts.ico",
    )
    args = parser.parse_args()
    build_icon(args.source.resolve(), args.png.resolve(), args.ico.resolve())
    print(f"PNG: {args.png.resolve()}")
    print(f"ICO: {args.ico.resolve()}")
    print("Frames: " + ", ".join(f"{size}x{size}" for size in ICON_SIZES))


if __name__ == "__main__":
    main()
