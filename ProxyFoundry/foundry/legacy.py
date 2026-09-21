"""Load preserved Card Tools, removing only obsolete compatibility workarounds."""
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'vendor/card_tools'

_MOROPHON_WRAP_RULE='''    if name=="Morophon, the Boundless":
        morophon_symbols="{W}{U}{B}{R}{G}"
        pos=oracle.find(morophon_symbols)
        if pos>0 and oracle[pos-1]!="\\n":
            if oracle[pos-1]==" ":
                oracle=oracle[:pos-1]+"\\n"+oracle[pos:]
            else:
                oracle=oracle[:pos]+"\\n"+oracle[pos:]

'''

def _compiler_source(text):
    if text.count(_MOROPHON_WRAP_RULE)!=1:
        raise RuntimeError('Unexpected v58 Morophon compatibility rule; refusing to silently alter Card Tools.')
    return text.replace(_MOROPHON_WRAP_RULE,'')

def load(name,relative,adapter=None):
    path=ROOT/relative
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    if adapter is None:
        spec.loader.exec_module(module)
    else:
        source=adapter(path.read_text(encoding='utf-8'))
        exec(compile(source,str(path),'exec'),module.__dict__)
    return module
compiler=load('pf_v58_compiler','pipeline/card_data_to_cardconjurer.py',_compiler_source)
ingest=load('pf_v58_ingest','pipeline/scryfall_to_card_data.py')
deck_parser=load('pf_v58_deck','pipeline/scryfall_deck_to_cardconjurer.py')
tokens=load('pf_v58_tokens','tools/make_copy_tokens.py')
image_tools=load('pf_v58_images','tools/download_scryfall_deck_images_zip.py')
