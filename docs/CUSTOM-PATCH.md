# Your own faction patch

The faction you found in Factions of the Zone has a patch. Sidorovich sells it, your members wear
it and leave one behind when they fall, and it's your faction's emblem at the top of the Factions
page. The mod ships a placeholder, an oval patch with its banner. This page shows how to put your
own emblem in its place.

![The placeholder patch on Wearable Devices' bracer](../media/patch-bracer.jpg)

## What you replace

Two pictures, in a small mod of your own. Factions itself stays untouched, so updating it never
overwrites your art.

| File | Size | Where it shows |
|---|---|---|
| `gamedata\textures\ui\fotz_your_faction.dds` | exactly 100x100 | the patch in your inventory, and your emblem on the Factions page |
| `gamedata\textures\fotz\fotz_bracer_patch.dds` | exactly 512x512 | the patch on Wearable Devices' bracer (skip it without Wearable Devices) |

The sizes have to be exact: the game reads each picture by its pixels, so a 128x128 icon would
show only its top-left corner.

## The quick way: one picture, one command

You need Python 3 with Pillow (`pip install pillow`), and the repo's `_tools` folder.

1. Make your emblem as a PNG. Anything outside the patch's shape should be transparent. Any size
   works; 512x512 or larger looks best.
2. In the `_tools` folder, run:

   ```
   python make_patch.py my_emblem.png "My faction patch"
   ```

   It writes both pictures, sized and placed as Factions needs them, into a `My faction patch`
   folder with the mod's layout already in it, and a `preview.png` to look at first.
3. Install it (below).

## By hand

Any editor that saves DDS works: GIMP 2.10 or later and Paint.NET can both save it, and Photoshop
can with NVIDIA's Texture Tools Exporter. Start from the templates in
[custom-patch/](custom-patch/), which are the placeholder's own pictures.

**The icon.** Open `icon-template.png` (100x100) and paint your emblem over it, keeping the size and
the transparent background. Save it as `fotz_your_faction.dds`: uncompressed with alpha (GIMP:
compression "None", format "RGBA8"; Paint.NET: "R8G8B8A8"), without mipmaps.

**The bracer** (with Wearable Devices). Open `bracer-template.png` (512x512). Your patch goes where
the placeholder is: inside the tilted square, turned the same way, with everything around it
transparent. `bracer-guide.png` is that square as an outline, to lay over your work as a layer and
hide before you save.

![Where the patch sits on the bracer's picture](custom-patch/bracer-layout.png)

Save it as `fotz_bracer_patch.dds`: BC3 (DXT5) or uncompressed, with mipmaps.

## Install it in MO2

1. In MO2's mod list, right-click and choose "Create empty mod". Call it "My faction patch".
2. Right-click it, "Open in Explorer", and put the files in:
   - `gamedata\textures\ui\fotz_your_faction.dds`
   - `gamedata\textures\fotz\fotz_bracer_patch.dds` (with Wearable Devices)

   From the quick way, copy the `gamedata` folder from `My faction patch` in as it is.
3. Tick the mod, and drag it **below Factions of the Zone** in the list. When two mods have the
   same file, MO2 uses the one lower down.
4. Start the game from MO2. Close MO2 and the game first if they were running when you added the
   files: MO2 only sees new files when it starts, and the game loads textures when it starts.

## See it in game

- **The emblem:** found your faction in MCM (Factions of the Zone, then Your faction) and open the
  Factions page. Your emblem is at the top.
- **The patch:** buy one from Sidorovich in Cordon ("Can you get patches sewn for my faction?").
  It shows your art in your inventory.
- **The bracer:** with Wearable Devices, put the patch in the bracer's accessories slot.

## Good to know

- The item keeps its name, "Patch (Your faction)".
- To go back to the placeholder, untick your mod.
- Your art mod can come and go at any time. The patches themselves are items, though: before
  removing Factions of the Zone, set MCM's "Remove your faction's patches" and save, because a save
  that holds one can't load without the mod.
- Without an HD icon framework, the patch takes 2x2 inventory cells instead of one; the picture is
  the same.
