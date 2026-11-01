"""This mod's small art besides the tile (make_tile.py), drawn here so no texture pack can move it.

- fotz_px.dds: one white 8x8 block. The Factions page draws its frame and rules with it,
  stretched and tinted (X-Ray has no fill-rect), as Seasons' pages do with theirs.
- fotz_your_faction.dds: your faction's patch, a placeholder for a player's own, 100x100: the
  item's icon is 2x2 cells of the 50 px inventory grid at scale 2, as the HD faction patches are,
  and the Factions page shows the same square as your faction's emblem. An oval patch, stitched at
  the edge, with the mod's banner on it.
- fotz\\fotz_bracer_patch.dds: the same patch for Wearable Devices' bracer, which shows the patch
  you put on it: 512x512 like WD's own patch textures, the patch left of center and tilted as
  theirs are, with mipmaps (it's a model's texture).

The UI art is described by configs/ui/textures_descr/ui_fotz_art.xml; the bracer's is named by
the item's wd_bracer_patch (mod_system_fotz_patch.ltx).

    python make_art.py [PREVIEW.png]      the preview: the patch on the PDA's color, 4x
"""
import os
import struct
import sys

from PIL import Image, ImageDraw

from make_tile import shape, write_dds

HERE = os.path.dirname(os.path.abspath(__file__))
TEXTURES = os.path.join(HERE, "..", "gamedata", "textures")
UI = os.path.join(TEXTURES, "ui")
SS = 4                                # supersampling for smooth edges
PATCH = 100                           # the item's 2x2 cells of 50 px, and the whole texture
BRACER, BRACER_PATCH = 512, 380       # WD's bracer texture, and the patch's height on it
BRACER_CENTER, BRACER_TILT = (214, 252), -8   # where WD's own patches sit, turned clockwise
BORDER = (200, 190, 152)              # the edge's thread
CLOTH = (62, 68, 50)                  # olive drab
STITCH = (120, 112, 84)
MARK = (214, 200, 150)                # the banner


def patch(size=PATCH):
    """The placeholder patch, size x size: an upright oval, stitched at the edge, the banner on it."""
    n = size * SS
    k = n / 100.0                     # drawn in hundredths of the square
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def box(inset_x, inset_y):
        return [inset_x * k, inset_y * k, n - inset_x * k, n - inset_y * k]

    d.ellipse(box(9, 3), fill=BORDER + (255,))                  # the oval's edge
    d.ellipse(box(14, 8), fill=CLOTH + (255,))                  # and the cloth inside
    for a in range(0, 360, 10):                                 # a running stitch along the edge
        d.arc(box(11.5, 5.5), a, a + 5, fill=STITCH + (255,), width=max(1, round(k)))
    side = round(50 * k)
    mark = shape().resize((side, side), Image.LANCZOS)          # the mod's banner on it
    layer = Image.new("RGBA", mark.size, MARK + (255,))
    layer.putalpha(mark)
    img.alpha_composite(layer, ((n - side) // 2, (n - side) // 2 + round(2 * k)))
    return img.resize((size, size), Image.LANCZOS)


def bracer():
    """The patch for WD's bracer: BRACER square, the patch BRACER_PATCH high, placed and tilted as
    WD's own patch textures have theirs."""
    p = patch(BRACER_PATCH).rotate(BRACER_TILT, resample=Image.BICUBIC, expand=True)
    out = Image.new("RGBA", (BRACER, BRACER), (0, 0, 0, 0))
    out.alpha_composite(p, (BRACER_CENTER[0] - p.width // 2, BRACER_CENTER[1] - p.height // 2))
    return out


def write_mipped_dds(img, path):
    """Uncompressed A8R8G8B8 DDS with every mipmap down to 1x1, for a model's texture."""
    w, h = img.size
    levels = []
    level = img.convert("RGBA")
    while True:
        levels.append(level)
        if level.size == (1, 1):
            break
        level = level.resize((max(1, level.width // 2), max(1, level.height // 2)), Image.LANCZOS)
    head = struct.pack("<4s7I44x9I12x4x", b"DDS ", 124, 0x2100F, h, w, w * 4, 0, len(levels),
                       32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000, 0x401008)
    assert len(head) == 128
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(head)
        for lv in levels:
            f.write(lv.tobytes("raw", "BGRA"))


def main():
    px = os.path.join(UI, "fotz_px.dds")
    write_dds(Image.new("RGBA", (8, 8), (255, 255, 255, 255)), px)
    print("wrote", os.path.normpath(px))
    img = patch()
    path = os.path.join(UI, "fotz_your_faction.dds")
    write_dds(img, path)
    print("wrote", os.path.normpath(path))
    br = bracer()
    path = os.path.join(TEXTURES, "fotz", "fotz_bracer_patch.dds")
    write_mipped_dds(br, path)
    print("wrote", os.path.normpath(path))
    if len(sys.argv) > 1:
        sheet = Image.new("RGBA", (PATCH * 4 + BRACER, BRACER), (24, 26, 28, 255))
        sheet.alpha_composite(img.resize((PATCH * 4, PATCH * 4), Image.NEAREST), (0, 0))
        sheet.alpha_composite(br, (PATCH * 4, 0))
        sheet.save(sys.argv[1])
        print("preview", sys.argv[1])


if __name__ == "__main__":
    main()
