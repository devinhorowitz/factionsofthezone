"""Your own faction patch from one picture: the two files Factions of the Zone draws your faction's
patch from, laid out as it needs them, ready to go in an MO2 mod (docs/CUSTOM-PATCH.md).

    python make_patch.py PICTURE [OUT]

PICTURE is any image Pillow opens (a PNG with transparency is best): your emblem as you want it on
the patch. Its transparent parts stay see-through; it's centered in a square, keeping its shape.
OUT (default "My faction patch") gets:

    OUT/gamedata/textures/ui/fotz_your_faction.dds     100x100: the patch's icon and your emblem on
                                                       the Factions page
    OUT/gamedata/textures/fotz/fotz_bracer_patch.dds   512x512 with mipmaps: the patch on Wearable
                                                       Devices' bracer, placed and tilted as WD's own
    OUT/preview.png                                    both, to look at first

Then in MO2: create an empty mod, copy OUT's gamedata folder into it, enable it, and drag it below
Factions of the Zone.
"""
import os
import sys

from PIL import Image

from make_art import BRACER, PATCH, on_bracer, write_mipped_dds
from make_tile import write_dds


def square(img):
    """The picture centered in a transparent square as large as its longer side."""
    img = img.convert("RGBA")
    side = max(img.size)
    out = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    out.alpha_composite(img, ((side - img.width) // 2, (side - img.height) // 2))
    return out


def make(picture, out):
    """Both files and the preview from one picture; returns their paths."""
    pic = square(Image.open(picture))
    icon = pic.resize((PATCH, PATCH), Image.LANCZOS)
    bracer = on_bracer(pic)
    icon_path = os.path.join(out, "gamedata", "textures", "ui", "fotz_your_faction.dds")
    bracer_path = os.path.join(out, "gamedata", "textures", "fotz", "fotz_bracer_patch.dds")
    write_dds(icon, icon_path)
    write_mipped_dds(bracer, bracer_path)
    preview = Image.new("RGBA", (PATCH * 4 + BRACER, BRACER), (24, 26, 28, 255))
    preview.alpha_composite(icon.resize((PATCH * 4, PATCH * 4), Image.NEAREST), (0, 0))
    preview.alpha_composite(bracer, (PATCH * 4, 0))
    preview_path = os.path.join(out, "preview.png")
    preview.save(preview_path)
    return icon_path, bracer_path, preview_path


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 2
    out = sys.argv[2] if len(sys.argv) > 2 else "My faction patch"
    for path in make(sys.argv[1], out):
        print("wrote", os.path.normpath(path))
    print('In MO2: create an empty mod, copy the "gamedata" folder from "%s" into it, enable it,' % out)
    print("and drag it below Factions of the Zone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
