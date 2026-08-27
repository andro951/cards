from pathlib import Path
import json, struct
ROOT=Path(__file__).resolve().parent
files=['derevi_empyrial_tactician.png','cloud_midgar_mercenary.png','enduring_curiosity.png','delney_streetwise_lookout.png']
out=[]
for fn in files:
    b=(ROOT/fn).read_bytes()
    assert b[:8]==b'\x89PNG\r\n\x1a\n'
    w,h=struct.unpack('>II',b[16:24])
    out.append({'file':fn,'width':w,'height':h,'aspect':w/h})
(ROOT/'AUTOFIT_DIMENSIONS.json').write_text(json.dumps(out,indent=2)+'\n')
