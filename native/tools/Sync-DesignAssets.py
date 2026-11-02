"""Bundle the same DM Sans identity used by the web workspace, with its OFL licence."""
import hashlib
import io
import json
from pathlib import Path
import httpx
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

root=Path(__file__).resolve().parents[2]
client=httpx.Client(timeout=60,follow_redirects=True)
response=client.get('https://api.github.com/repos/google/fonts/commits',params={'path':'ofl/dmsans','per_page':1});response.raise_for_status()
commit=response.json()[0]['sha']
base=f'https://raw.githubusercontent.com/google/fonts/{commit}/ofl/dmsans/'
response=client.get(base+'DMSans%5Bopsz,wght%5D.ttf');response.raise_for_status();raw=response.content
font=TTFont(io.BytesIO(raw));assert 'DM Sans' in font['name'].getDebugName(1)
windows=root/'native/windows/Assets/Fonts';windows.mkdir(parents=True,exist_ok=True)
(windows/'DMSans.ttf').write_bytes(raw)
android=root/'native/android/app/src/main/res/font';android.mkdir(parents=True,exist_ok=True)
for weight,name in [(400,'regular'),(500,'medium'),(600,'semibold'),(700,'bold')]:
    instance=instantiateVariableFont(font,{'opsz':14,'wght':weight},inplace=False,updateFontNames=True)
    instance.save(android/f'dm_sans_{name}.ttf')
licence=client.get(base+'OFL.txt');licence.raise_for_status()
shared=root/'native/shared/licenses';shared.mkdir(parents=True,exist_ok=True)
(shared/'DM-Sans-OFL.txt').write_text(licence.text,encoding='utf-8')
manifest={'family':'DM Sans','source':base,'commit':commit,'source_sha256':hashlib.sha256(raw).hexdigest(),'licence':'SIL Open Font License 1.1','android_static_weights':[400,500,600,700]}
(root/'native/shared/design-assets.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('Bundled DM Sans and OFL licence from Google Fonts commit '+commit)
