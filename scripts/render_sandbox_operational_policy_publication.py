from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pygments import lex
from pygments.lexers import PythonLexer
from pygments.token import Comment, Keyword, Name, Number, Operator, String, Token

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "linkedin" / "Sandbox Operational Admission Policy"
DESTINATION = (
    Path.home() / "OneDrive" / "Imagens" / "LinkedIn" / "Sandbox Operational Admission Policy"
)
COVER = (
    Path.home()
    / ".codex"
    / "generated_images"
    / "01a006ab-7fb8-7d62-a90c-f52b746e5d2e"
    / "exec-8e230433-1520-4133-89a5-0dde0fad165e.png"
)

SLIDES = (
    (
        "02-fail-closed-policy.png",
        ROOT / "backend" / "synapse" / "bootstrap" / "adapters" / "sandbox_policy.py",
        15,
        55,
        "Política fail-closed",
        "Admissão exige fatos completos, aprovação, grants exatos e isolamento comprovado.",
    ),
    (
        "03-deferred-runtime.png",
        ROOT / "backend" / "synapse" / "bootstrap" / "adapters" / "sandbox.py",
        15,
        62,
        "Lifecycle explícito",
        "Construção inerte; o runtime nasce somente no startup governado.",
    ),
    (
        "04-global-binding.png",
        ROOT / "backend" / "synapse" / "bootstrap" / "bindings.py",
        100,
        126,
        "Binding global autorizado",
        "Required, available, global, authorized e active continuam fatos separados.",
    ),
    (
        "05-factual-health.png",
        ROOT / "backend" / "synapse" / "health" / "contributors" / "sandbox.py",
        1,
        48,
        "Health sem autoridade",
        "Boundary ready não afirma que execução, supervisão ou driver estejam disponíveis.",
    ),
)


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    family = "CascadiaCode-Bold.ttf" if bold else "CascadiaCode.ttf"
    candidates = (
        Path("C:/Windows/Fonts") / family,
        Path("C:/Windows/Fonts/consola.ttf"),
    )
    return ImageFont.truetype(str(next(path for path in candidates if path.exists())), size)


def token_color(token: Token) -> str:
    if token in Keyword or token in Keyword.Type:
        return "#C586C0"
    if token in Name.Class or token in Name.Function or token in Name.Decorator:
        return "#4EC9B0"
    if token in String:
        return "#CE9178"
    if token in Number:
        return "#B5CEA8"
    if token in Comment:
        return "#6A9955"
    if token in Operator:
        return "#D4D4D4"
    if token in Name.Builtin:
        return "#DCDCAA"
    return "#D4D4D4"


def render_slide(
    output: Path,
    source: Path,
    start: int,
    end: int,
    title: str,
    subtitle: str,
) -> None:
    width, height = 1600, 900
    image = Image.new("RGB", (width, height), "#1E1E1E")
    draw = ImageDraw.Draw(image)
    code_font = font(20)
    small_font = font(16)
    title_font = font(26, bold=True)
    draw.rectangle((0, 0, width, 48), fill="#323233")
    draw.ellipse((80, 16, 96, 32), fill="#FF5F57")
    draw.ellipse((104, 16, 120, 32), fill="#FEBC2E")
    draw.ellipse((128, 16, 144, 32), fill="#28C840")
    draw.text((1125, 15), "Synapse — Visual Studio Code", font=small_font, fill="#CCCCCC")
    draw.rectangle((64, 48, 400, 96), fill="#252526")
    draw.text((88, 63), f"PY  {source.name}", font=small_font, fill="#E7E7E7")
    draw.line((64, 95, 400, 95), fill="#007ACC", width=2)
    draw.rectangle((64, 96, 146, 736), fill="#181818")

    lines = source.read_text(encoding="utf-8").splitlines()
    selected = lines[start - 1 : end]
    line_height = 27
    max_lines = 22
    if len(selected) > max_lines:
        selected = selected[:max_lines]
    y = 118
    for offset, line in enumerate(selected):
        line_number = start + offset
        draw.text((96, y), f"{line_number:>3}", font=code_font, fill="#858585")
        x = 164
        for token, value in lex(line, PythonLexer()):
            value = value.replace("\n", "")
            if not value:
                continue
            draw.text((x, y), value, font=code_font, fill=token_color(token))
            x += draw.textlength(value, font=code_font)
        y += line_height

    draw.rectangle((92, 738, 1544, 842), fill="#111820", outline="#2389C9", width=2)
    draw.text((122, 754), title, font=title_font, fill="#7FDBFF")
    draw.text((122, 798), subtitle, font=small_font, fill="#CDD6E0")
    relative = source.relative_to(ROOT).as_posix().replace("/", "  ›  ")
    draw.text((122, 828), relative, font=font(13), fill="#77818B")
    draw.rectangle((0, 872, width, height), fill="#007ACC")
    draw.text((20, 878), "◫  main*", font=font(13), fill="white")
    draw.text((1285, 878), f"Ln {start}, Col 1    UTF-8    Python", font=font(13), fill="white")
    image.save(output, format="PNG", optimize=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def main() -> None:
    if ARTIFACTS.exists() or DESTINATION.exists():
        raise SystemExit("Refusing to overwrite an existing publication package")
    ARTIFACTS.mkdir(parents=True)
    shutil.copy2(COVER, ARTIFACTS / "01-cover.png")
    for filename, source, start, end, title, subtitle in SLIDES:
        render_slide(ARTIFACTS / filename, source, start, end, title, subtitle)
    DESTINATION.mkdir(parents=True)
    for source in sorted(ARTIFACTS.glob("*.png")):
        target = DESTINATION / source.name
        shutil.copy2(source, target)
        if sha256(source) != sha256(target):
            raise SystemExit(f"Hash mismatch: {source.name}")
        print(f"{source.name} {sha256(source)}")


if __name__ == "__main__":
    main()
