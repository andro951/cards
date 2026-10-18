"""Build pinned reflected headers once; browsers reuse bundled PNGs."""
import io,sys
from pathlib import Path
from PIL import Image,ImageChops,ImageFilter,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from foundry.werewolf_frame import reflect_title_pinline

ROOT=Path(__file__).resolve().parents[1]

def build(fetch,destination):
    destination.mkdir(parents=True,exist_ok=True)
    def load(path):return Image.open(io.BytesIO(fetch(path)[0])).convert('RGBA')
    mask=load('/img/frames/m15/transform/regular/maskPinlineFront.png').getchannel('A')
    for code in 'WUBRGMAL':
        source=load('/img/frames/m15/transform/regular/front'+code+'.png')
        source.putalpha(ImageChops.multiply(source.getchannel('A'),mask))
        reflected=reflect_title_pinline(source.resize((2010,2814),Image.Resampling.LANCZOS))
        reflected.save(destination/('TitlePinline'+code+'.png'))
        if code=='R':
            outline=Image.new('RGBA',reflected.size,(0,0,0,0))
            outline.putalpha(reflected.getchannel('A').filter(ImageFilter.MaxFilter(9)))
            outline.save(destination/'TitleOutline.png')
    lower=Image.new('RGBA',(2010,2814))
    ImageDraw.Draw(lower).rectangle((0,round(.545*2814),2010,2814),fill='white')
    lower.save(destination/'LowerMask.png')

if __name__=='__main__':
    from foundry.server import App
    from foundry.storage import Store
    app=App(Store(ROOT/'test-results/land-title-black-workspace'))
    build(app.runtime.fetch,ROOT/'assets/werewolf')
    print('Built bundled Werewolf headers',flush=True)
