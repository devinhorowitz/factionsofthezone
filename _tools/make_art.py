"""This mod's small art besides the tile (make_tile.py), drawn here so no texture pack can move it.

- fotz_px.dds: one white 8x8 block. The Factions page draws its frame and rules with it,
  stretched and tinted (X-Ray has no fill-rect), as Seasons' pages do with theirs.
- fotz_your_faction.dds: your faction's patch, a placeholder for a player's own, 100x100: the
  item's icon is 2x2 cells of the 50 px inventory grid at scale 2, as the HD faction patches are,
  and the Factions page shows the same square as your faction's emblem. An oval patch, stitched at
  the edge, with the mod's banner on it.

Described by configs/ui/textures_descr/ui_fotz_art.xml.

    python make_art.py [PREVIEW.png]      the preview: the patch on the PDA's color, 4x
"""
import os
import sys

from PIL import Image, ImageDraw

from make_tile import shape, write_dds

HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(HERE, "..", "gamedata", "textures", "ui")
SS = 4                                # supersampling for smooth edges
PATCH = CANVAS = 100                  # the item's 2x2 cells of 50 px, and the whole texture
BORDER = (200, 190, 152)              # the edge's thread
CLOTH = (62, 68, 50)                  # olive drab
STITCH = (120, 112, 84)
MARK = (214, 200, 150)                # the banner


def patch():
    """The placeholder patch, PATCH x PATCH."""
    n = PATCH * SS
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def box(inset_x, inset_y):
        return [inset_x * SS, inset_y * SS, n - inset_x * SS, n - inset_y * SS]

    d.ellipse(box(9, 3), fill=BORDER + (255,))                  # an upright oval, its edge
    d.ellipse(box(14, 8), fill=CLOTH + (255,))                  # and the cloth inside
    for a in range(0, 360, 10):                                 # a running stitch along the edge
        d.arc(box(11.5, 5.5), a, a + 5, fill=STITCH + (255,), width=SS)
    mark = shape().resize((50 * SS, 50 * SS), Image.LANCZOS)    # the mod's banner on it
    layer = Image.new("RGBA", mark.size, MARK + (255,))
    layer.putalpha(mark)
    img.alpha_composite(layer, ((n - mark.width) // 2, (n - mark.height) // 2 + 2 * SS))
    out = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    out.paste(img.resize((PATCH, PATCH), Image.LANCZOS), (0, 0))
    return out


def main():
    px = os.path.join(UI, "fotz_px.dds")
    write_dds(Image.new("RGBA", (8, 8), (255, 255, 255, 255)), px)
    print("wrote", os.path.normpath(px))
    img = patch()
    path = os.path.join(UI, "fotz_your_faction.dds")
    write_dds(img, path)
    print("wrote", os.path.normpath(path))
    if len(sys.argv) > 1:
        bg = Image.new("RGBA", img.size, (24, 26, 28, 255))
        bg.alpha_composite(img)
        bg.resize((CANVAS * 4, CANVAS * 4), Image.NEAREST).save(sys.argv[1])
        print("preview", sys.argv[1])


if __name__ == "__main__":
    main()
