"""Add Morok's curled sleep and pointer-holding frames without replacing the v3 atlas."""

from build_sitting_atlas import ART, CHARACTER, FRAME_HEIGHT, append_strip
from PIL import Image


def main() -> None:
    previous = Image.open(CHARACTER / "sprites-v3.png").convert("RGBA")
    atlas = Image.new("RGBA", (previous.width, previous.height + 2 * FRAME_HEIGHT))
    atlas.alpha_composite(previous)
    append_strip(atlas, ART / "morok-curl-sleep-source.png", 14, (160, 145, 110, 110))
    append_strip(atlas, ART / "morok-pointer-hold-source.png", 15, (190, 190, 190, 190))
    atlas.save(CHARACTER / "sprites-v4.png", optimize=True)


if __name__ == "__main__":
    main()
