from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / "apps" / "frontend-v2" / "assets" / "media" / "icons"
PALETTES = {
    "synapse": ((16, 105, 112), (54, 235, 226), (220, 255, 252)),
    "violet": ((55, 30, 92), (170, 132, 255), (245, 237, 255)),
    "amber": ((105, 58, 12), (245, 180, 92), (255, 244, 210)),
    "blue": ((20, 65, 115), (88, 180, 255), (228, 245, 255)),
    "neutral": ((65, 76, 82), (180, 198, 204), (250, 252, 253)),
}

def derive(source: Path, target: Path, palette: tuple[tuple[int, int, int], ...]) -> None:
    image = Image.open(source).convert("RGBA")
    low, mid, high = palette
    pixels = []
    for r, g, b, a in image.getdata():
        if a == 0:
            pixels.append((r, g, b, a))
            continue
        lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
        if lum < 0.5:
            t = lum / 0.5
            color = tuple(round(low[i] * (1 - t) + mid[i] * t) for i in range(3))
        else:
            t = (lum - 0.5) / 0.5
            color = tuple(round(mid[i] * (1 - t) + high[i] * t) for i in range(3))
        pixels.append((*color, a))
    image.putdata(pixels)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, "PNG", optimize=False)

for group, names in {
    "navigation": ("constellation", "library", "settings"),
    "status": ("notifications-idle", "notifications-active"),
}.items():
    for name in names:
        source = ROOT / group / f"{name}.png"
        for theme, palette in PALETTES.items():
            derive(source, ROOT / group / theme / f"{name}.png", palette)
