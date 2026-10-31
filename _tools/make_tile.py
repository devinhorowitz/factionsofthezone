"""The Factions page's tile for Mod App Creator's launcher: a banner on a pole, drawn here, as flat
art in the PDA's colors like the tiles beside it (Arsenal's, Seasons'): light gray (enabled), amber
(highlighted), white (touched), dim gray (disabled). A 512x512 four-state atlas: e top-left,
h top-right, t bottom-left, d bottom-right, described by configs/ui/textures_descr/ui_fotz_app.xml.

The art is this mod's own, so no texture pack can move it.

    python make_tile.py [OUT.dds] [PREVIEW.png]
"""
import os
import struct
import sys

from PIL import Image, ImageChops, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "gamedata", "textures", "ui", "fotz_app.dds")
STATES = {                            # quadrant origin -> color
    "e": ((0, 0), (200, 200, 200)),
    "h": ((256, 0), (238, 196, 112)),
    "t": ((0, 256), (255, 255, 255)),
    "d": ((256, 256), (110, 110, 110)),
}
SS = 4                                # supersampling for smooth edges


def shape():
    """The banner's mask, 256x256: a pole with a knob, a swallowtail flag, a ring cut through it."""
    n = 256 * SS
    m = Image.new("L", (n, n), 0)
    d = ImageDraw.Draw(m)

    def s(*v):
        return [x * SS for x in v]

    d.rectangle(s(62, 34, 74, 226), fill=255)                         # the pole
    d.ellipse(s(56, 18, 80, 42), fill=255)                            # its knob
    d.rectangle(s(52, 220, 84, 232), fill=255)                        # its foot
    d.polygon(s(74, 46, 214, 46, 182, 96, 214, 146, 74, 146), fill=255)  # the flag, swallowtailed
    ring = Image.new("L", (n, n), 0)
    r = ImageDraw.Draw(ring)
    r.ellipse(s(110, 70, 162, 122), fill=255)
    r.ellipse(s(122, 82, 150, 110), fill=0)
    m = ImageChops.subtract(m, ring)                                  # a ring cut through the flag
    return m.resize((256, 256), Image.LANCZOS)


def atlas(mask):
    out = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    for (x, y), color in STATES.values():
        t = Image.new("RGBA", (256, 256), color + (0,))
        t.putalpha(mask)
        out.paste(t, (x, y))
    return out


def write_dds(img, path):
    """Uncompressed A8R8G8B8 DDS, no mipmaps (as Arsenal's tile)."""
    w, h = img.size
    head = struct.pack("<4s7I44x9I12x4x", b"DDS ", 124, 0x100F, h, w, w * 4, 0, 1,
                       32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000, 0x1000)
    assert len(head) == 128
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(head + img.convert("RGBA").tobytes("raw", "BGRA"))


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else OUT
    img = atlas(shape())
    write_dds(img, out)
    print("wrote", os.path.normpath(out))
    if len(sys.argv) > 2:
        bg = Image.new("RGBA", img.size, (24, 26, 28, 255))
        bg.alpha_composite(img)
        bg.save(sys.argv[2])
        print("preview", sys.argv[2])


if __name__ == "__main__":
    main()
