"""Cut static DM Sans instances from the bundled variable font.

Flutter does not map FontWeight to a variable font's weight axis, and it renders the
font at its default optical size (9), which looks light and wide next to the web app.
The web app gets weight and optical size from CSS. These static files give Flutter the
same shapes: "DM Sans" for text up to about 20 px and "DM Sans Display" for headings.

Requires fontTools:  python -m pip install fonttools
Run from native/flutter:  python tool/build_fonts.py
"""
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

FONTS = Path(__file__).resolve().parents[1] / 'assets' / 'fonts'
SOURCE = FONTS / 'dm-sans.ttf'
FAMILIES = {
    'dm-sans': (14, (400, 500, 600, 700, 800)),
    'dm-sans-display': (32, (500, 600, 700, 800)),
}

for prefix, (optical_size, weights) in FAMILIES.items():
    for weight in weights:
        font = instancer.instantiateVariableFont(TTFont(SOURCE), {'wght': weight, 'opsz': optical_size})
        target = FONTS / f'{prefix}-{weight}.ttf'
        font.save(target)
        print(target.name, target.stat().st_size)
