"""Generate platform assets from the supplied blue logo; preserve its artwork."""
from pathlib import Path
from PIL import Image,ImageChops
import hashlib,json
root=Path(__file__).resolve().parents[2]
source=root/'native/shared/brand/apexbooks-logo-original.png'
original=Image.open(source).convert('RGBA')
full_bounds=original.getbbox();cropped=original.crop(full_bounds)
wordmark=Image.new('RGBA',cropped.size,'white');wordmark.alpha_composite(cropped)
r,g,b,a=original.split();mask=ImageChops.multiply(ImageChops.subtract(b,r).point(lambda v:255 if v>35 else 0),a)
symbol_bounds=mask.getbbox();symbol=original.crop(symbol_bounds)
assert symbol.width>symbol.height and wordmark.width>wordmark.height

def icon(size):
    canvas=Image.new('RGBA',(size,size),'white')
    inner=symbol.copy();inner.thumbnail((round(size*.84),round(size*.84)),Image.Resampling.LANCZOS)
    canvas.alpha_composite(inner,((size-inner.width)//2,(size-inner.height)//2));return canvas
assets=root/'native/windows/Assets'
for name,size in [('ApexBooksLogo.png',512),('StoreLogo.png',50),('Square150x150Logo.scale-200.png',300),('Square44x44Logo.scale-200.png',88),('LockScreenLogo.scale-200.png',48),('Square44x44Logo.targetsize-24_altform-unplated.png',24),('Square44x44Logo.targetsize-48_altform-lightunplated.png',48)]:icon(size).save(assets/name)
wordmark.save(assets/'ApexBooksWordmark.png')
for name,w,h,logo_w in [('SplashScreen.scale-200.png',1240,600,920),('Wide310x150Logo.scale-200.png',620,300,500)]:
    canvas=Image.new('RGBA',(w,h),'white');fit=wordmark.resize((logo_w,round(logo_w*wordmark.height/wordmark.width)),Image.Resampling.LANCZOS);canvas.alpha_composite(fit,((w-fit.width)//2,(h-fit.height)//2));canvas.save(assets/name)
icon(256).save(assets/'AppIcon.ico',sizes=[(s,s) for s in (16,24,32,48,64,128,256)])
web=root/'frontend/public';web.mkdir(parents=True,exist_ok=True)
icon(512).save(web/'apexbooks-logo.png');wordmark.save(web/'apexbooks-wordmark.png')
icon(256).save(web/'favicon.ico',sizes=[(s,s) for s in (16,24,32,48,64,128,256)]);icon(180).save(web/'apple-touch-icon.png')
android=root/'native/android/app/src/main/res/drawable-nodpi';android.mkdir(parents=True,exist_ok=True)
icon(512).save(android/'apexbooks_logo.png');wordmark.save(android/'apexbooks_wordmark.png')
(source.parent/'manifest.json').write_text(json.dumps({'source':source.name,'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'full_artwork_bounds':full_bounds,'symbol_bounds':symbol_bounds,'treatment':'Empty transparent margins trimmed. Full wordmark on white for UI; blue symbol centered on white for small icons. No stretching or recoloring.'},indent=2))
print('Generated full blue wordmark and matching platform icons.')
