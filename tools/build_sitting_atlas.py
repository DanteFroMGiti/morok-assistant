"""Append generated sitting and watching frames to Morok's original sprite atlas.

Run with a Python environment containing Pillow after updating the source strips in art/.
"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "art"
CHARACTER = ROOT / "src" / "morok_assistant" / "assets" / "characters" / "morok"
FRAME_WIDTH = 192
FRAME_HEIGHT = 208


def append_strip(atlas: Image.Image, source: Path, row: int, heights: tuple[int, ...]) -> None:
    strip = Image.open(source).convert("RGBA")
    segment_width = strip.width // len(heights)
    for column, target_height in enumerate(heights):
        segment = strip.crop(
            (column * segment_width, 0, (column + 1) * segment_width, strip.height)
        )
        alpha = segment.getchannel("A")
        bounds = alpha.point(lambda value: 255 if value > 16 else 0).getbbox()
        if bounds is None:
            raise ValueError(f"No visible sprite in {source.name}, frame {column}")
        left, top, right, bottom = bounds
        segment = segment.crop(
            (
                max(0, left - 4),
                max(0, top - 4),
                min(segment.width, right + 4),
                min(segment.height, bottom + 4),
            )
        )
        scale = min(175 / segment.width, target_height / segment.height)
        size = (round(segment.width * scale), round(segment.height * scale))
        segment = segment.resize(size, Image.Resampling.LANCZOS)
        clean_alpha = segment.getchannel("A").point(lambda value: 0 if value <= 2 else value)
        segment.putalpha(clean_alpha)
        x = column * FRAME_WIDTH + (FRAME_WIDTH - segment.width) // 2
        y = row * FRAME_HEIGHT + 200 - segment.height
        atlas.alpha_composite(segment, (x, y))


def main() -> None:
    original = Image.open(CHARACTER / "sprites.png").convert("RGBA")
    atlas = Image.new("RGBA", (original.width, original.height + 3 * FRAME_HEIGHT))
    atlas.alpha_composite(original)
    append_strip(atlas, ART / "morok-sit-down-source.png", 11, (188, 180, 165, 160))
    append_strip(atlas, ART / "morok-sitting-source.png", 12, (160, 160, 160, 160))
    append_strip(atlas, ART / "morok-sitting-watch-source.png", 13, (160, 160, 160, 160))
    atlas.save(CHARACTER / "sprites-v3.png", optimize=True)


if __name__ == "__main__":
    main()
