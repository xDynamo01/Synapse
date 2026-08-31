from hashlib import sha256
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).parents[1] / "apps" / "frontend-v2" / "assets" / "media" / "icons"
THEMES = ("synapse", "violet", "amber", "blue", "neutral")
ASSETS = {
    "navigation": ("constellation", "library", "settings"),
    "status": ("notifications-idle", "notifications-active"),
}


def test_theme_icon_families_are_complete_and_distinct() -> None:
    for group, names in ASSETS.items():
        for name in names:
            files = [ROOT / group / theme / f"{name}.png" for theme in THEMES]
            assert all(path.is_file() for path in files)
            assert len({sha256(path.read_bytes()).hexdigest() for path in files}) == 5
            with Image.open(files[0]) as reference:
                size = reference.size
                assert "A" in reference.getbands()
            for path in files[1:]:
                with Image.open(path) as image:
                    assert image.size == size
                    assert "A" in image.getbands()
