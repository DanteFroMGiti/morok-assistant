"""Append Morok's side-facing video-watching frames to the v4 sprite atlas."""

from build_sitting_atlas import ART, CHARACTER, FRAME_HEIGHT, append_strip
from PIL import Image


def main() -> None:
    previous = Image.open(CHARACTER / "sprites-v4.png").convert("RGBA")
    atlas = Image.new("RGBA", (previous.width, previous.height + FRAME_HEIGHT))
    atlas.alpha_composite(previous)
    append_strip(
        atlas,
        ART / "morok-video-watching-source.png",
        16,
        (164, 164, 164, 164),
    )
    atlas.save(CHARACTER / "sprites-v5.png", optimize=True)


if __name__ == "__main__":
    main()
