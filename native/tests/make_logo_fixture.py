"""Deterministic dense transparent PNG for the published Windows converter check."""
import random
import sys
from pathlib import Path
from PIL import Image, ImageDraw

target = Path(sys.argv[1])
target.parent.mkdir(parents=True, exist_ok=True)
rng = random.Random(71)
image = Image.frombytes('RGBA', (1600, 900), rng.randbytes(1600 * 900 * 4))
draw = ImageDraw.Draw(image)
draw.rectangle((0, 0, 63, 899), fill=(0, 0, 0, 0))
draw.rectangle((0, 0, 1599, 63), fill=(0, 0, 0, 0))
draw.rectangle((250, 260, 1350, 640), fill=(18, 124, 102, 255))
draw.text((600, 430), 'NATIVE LOGO QA', fill='white')
image.save(target, format='PNG')
print('Native transparent logo fixture generated.')
