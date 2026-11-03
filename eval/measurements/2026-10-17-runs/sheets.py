"""Contact sheets: the PNGs in a folder, 2 x 2 to a sheet, each labelled with its file name."""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

src, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(exist_ok=True)
files = sorted(src.glob("*.png"), key=lambda p: [int(x) for x in p.stem.split("__")[1].split("-")[0].split(".")])
W = 640
for i in range(0, len(files), 4):
    tiles = []
    for f in files[i:i + 4]:
        im = Image.open(f).convert("RGB")
        im = im.resize((W, int(im.height * W / im.width)))
        tiles.append((f.stem.split("__")[1], im))
    h = max(t[1].height for t in tiles) + 28
    sheet = Image.new("RGB", (W * 2, h * 2), "white")
    d = ImageDraw.Draw(sheet)
    for j, (name, im) in enumerate(tiles):
        x, y = (j % 2) * W, (j // 2) * h
        d.text((x + 6, y + 6), name, fill="red")
        sheet.paste(im, (x, y + 28))
    sheet.save(out / f"sheet{i // 4 + 1}.png")
    print(out / f"sheet{i // 4 + 1}.png", [t[0] for t in tiles])
