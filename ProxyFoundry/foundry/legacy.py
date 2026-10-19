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

_OLD_SUPERTYPES='SUPERTYPES = {"Basic", "Legendary", "Snow", "World"}'
_NEW_SUPERTYPES='SUPERTYPES = {"Basic", "Legendary", "Snow", "World", "Token"}'

def _token_supertype_source(text):
    if text.count(_OLD_SUPERTYPES)!=1:
        raise RuntimeError('Unexpected v58 supertype schema; refusing to silently alter Card Tools.')
    return text.replace(_OLD_SUPERTYPES,_NEW_SUPERTYPES)

def _token_source(text):
    text=_token_supertype_source(text)
    anchor='    pt["name"] = "Power/Toughness"'
    if text.count(anchor)!=1:
        raise RuntimeError('Unexpected v58 token PT schema; refusing to silently alter Card Tools.')
    # Noncreature donors have no PT text. Native writeText still reads every box.
    return text.replace(anchor,'    pt.setdefault("text", "")\n'+anchor)

def _compiler_source(text):
    if text.count(_MOROPHON_WRAP_RULE)!=1:
        raise RuntimeError('Unexpected v58 Morophon compatibility rule; refusing to silently alter Card Tools.')
    text=text.replace(_MOROPHON_WRAP_RULE,'').replace('if re.match(r"^(?:https?|data):",explicit,re.I):','if re.match(r"^(?:https?|data):",explicit,re.I) or Path(explicit).is_file():')
    anchor='    entry=recipe_data(recipe,card,type_info); entry["key"]=name; data=entry["data"]'
    if text.count(anchor)!=1:raise RuntimeError('Unexpected token seed schema in preserved compiler.')
    text=text.replace(anchor,'''    token_seed=bool(card.pop("_proxy_token_seed",False))
    entry=copy.deepcopy(LAYOUTS[recipe]) if token_seed else recipe_data(recipe,card,type_info)
    entry["key"]=name; data=entry["data"]
    if token_seed:data["frames"]=[]''')
    for call in ('ensure_legend_crown_border_cover(data, recipe)','try_apply_pt_box(data,card,type_info,recipe)','apply_universal_set_symbol_geometry(data,symbol)'):
        anchor='    '+call
        if text.count(anchor)!=1:raise RuntimeError('Unexpected token seed geometry in preserved compiler.')
        text=text.replace(anchor,'    if not token_seed:'+call)
    return text

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
ingest=load('pf_v58_ingest','pipeline/scryfall_to_card_data.py',_token_supertype_source)
# Scryfall uses Emblem as the card type for emblem objects. Extend the loaded
# semantic schema without changing the preserved Card Tools source.
ingest.MAIN_TYPES.add('Emblem')
# Art Series printings use the literal type line "Card" on each image face.
ingest.MAIN_TYPES.add('Card')
deck_parser=load('pf_v58_deck','pipeline/scryfall_deck_to_cardconjurer.py')
tokens=load('pf_v58_tokens','tools/make_copy_tokens.py',_token_source)
image_tools=load('pf_v58_images','tools/download_scryfall_deck_images_zip.py')

# Read original WebP dimensions without converting its pixels.
_original_jpeg_size=compiler.jpeg_size
def _jpeg_or_webp_size(raw):
    size=_original_jpeg_size(raw)
    if size or raw[:4]!=b'RIFF' or raw[8:12]!=b'WEBP':return size
    import io
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as image:return image.size
compiler.jpeg_size=_jpeg_or_webp_size
