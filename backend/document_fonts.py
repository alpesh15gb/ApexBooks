"""Bundled document typography; avoid viewer-dependent Base14 substitution."""
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

REGULAR_FONT = 'ApexDocument'
BOLD_FONT = 'ApexDocumentBold'
_font_dir = Path(__file__).with_name('assets') / 'fonts'
pdfmetrics.registerFont(TTFont(REGULAR_FONT, str(_font_dir / 'DejaVuSans.ttf')))
pdfmetrics.registerFont(TTFont(BOLD_FONT, str(_font_dir / 'DejaVuSans-Bold.ttf')))
pdfmetrics.registerFontFamily(REGULAR_FONT, normal=REGULAR_FONT, bold=BOLD_FONT,
                              italic=REGULAR_FONT, boldItalic=BOLD_FONT)
