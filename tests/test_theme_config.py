"""Guards the shipped theme palettes: valid TOML, valid colours, readable contrast."""
import re
import tomllib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ACTIVE_CONFIG = PROJECT_ROOT / ".streamlit" / "config.toml"
THEME_DIR = PROJECT_ROOT / ".streamlit" / "themes"
THEME_FILES = [ACTIVE_CONFIG] + sorted(THEME_DIR.glob("*.toml"))
HEX = re.compile(r"#[0-9A-Fa-f]{6}")


def relative_luminance(hex_color: str) -> float:
    raw = hex_color.lstrip("#")
    channels = []
    for start in (0, 2, 4):
        value = int(raw[start:start + 2], 16) / 255
        channels.append(value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(foreground: str, background: str) -> float:
    lighter, darker = sorted(
        (relative_luminance(foreground), relative_luminance(background)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def load_theme(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))["theme"]


def test_three_offered_palettes_are_shipped():
    assert {path.stem for path in THEME_DIR.glob("*.toml")} == {
        "seagrass-light",
        "seagrass-dark",
        "field-sunlight",
    }


@pytest.mark.parametrize("path", THEME_FILES, ids=lambda path: path.name)
def test_palette_is_complete_and_readable(path):
    theme = load_theme(path)
    assert theme["base"] in {"light", "dark"}
    for key in ("primaryColor", "backgroundColor", "secondaryBackgroundColor", "textColor"):
        assert HEX.fullmatch(theme[key]), f"{path.name}: {key} must be a #RRGGBB colour"
    # Body text sits on both backgrounds, so both must clear WCAG AAA for normal text.
    assert contrast(theme["textColor"], theme["backgroundColor"]) >= 7
    assert contrast(theme["textColor"], theme["secondaryBackgroundColor"]) >= 7
