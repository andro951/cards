"""The approved compact full-art land family; other land families stay native."""
from pathlib import Path
import copy,json

ASSET_ROOT=Path(__file__).resolve().parents[1]/'assets/compact-land'
GEOMETRY=json.loads((ASSET_ROOT/'geometry.json').read_text(encoding='utf-8'))
PREFIX='/img/frames/proxy-foundry/compact-land/'
ADDON_PREFIX='/img/frames/proxy-foundry/land-addons/'
BASIC_NICKNAME_RAISE=24/2814

def apply_textless_land_adjustments(data,recipe,nickname):
    """Keep native basic/dual families, correcting only their masks/addons."""
    if recipe=='land_full_basic' and nickname:
        offset=1/2100
        for frame in data['frames']:
            source=str(frame.get('src',''))
            if '/nickname/addons/m15NicknameTitle' in source:
                code=source.rsplit('Title',1)[-1][0]
                frame.update(src=ADDON_PREFIX+'BasicTrueName'+code+'.png',masks=[])
                frame['bounds']={'x':0,'y':-BASIC_NICKNAME_RAISE,'width':1,'height':1}
            elif source.startswith('/img/frames/textless/eoe/') and not any(
                str(mask.get('src','')).endswith('/maskBorder.png') for mask in frame.get('masks',[])):
                # Move the title, its pinline, and mana symbol together. The
                # native opaque bottom card border stays in its original place.
                bounds=frame.setdefault('bounds',{'x':0,'y':0,'width':1,'height':1})
                if frame.get('masks'):frame.setdefault('ogBounds',copy.deepcopy(bounds))
                bounds['y']=bounds.get('y',0)-BASIC_NICKNAME_RAISE
        data['text']['title']['y']+=offset-BASIC_NICKNAME_RAISE
        data['text']['nickname']['y']-=BASIC_NICKNAME_RAISE
        if 'setSymbolY' in data:data['setSymbolY']-=BASIC_NICKNAME_RAISE
        if 'setSymbolBounds' in data:data['setSymbolBounds']['y']-=BASIC_NICKNAME_RAISE
    elif recipe=='original_dual_land_textless':
        for frame in data['frames']:
            for mask in frame.get('masks',[]):
                if mask.get('src')=='/img/frames/textless/basics/type.svg':
                    mask['src']=ADDON_PREFIX+'original-dual-type.svg'
            source=str(frame.get('src',''))
            if nickname and source.startswith('/img/frames/m15/nickname/addons/m15NicknameTitle'):
                frame['src']=ADDON_PREFIX+'TrueNameNoOuter'+source.rsplit('Title',1)[-1]

def part(name,label):
    return {'name':label,'src':PREFIX+name+'.png','masks':[],
            'bounds':copy.deepcopy(GEOMETRY['parts'][name])}

def apply_compact_land_header(data,sem,bar_layers):
    """Four independent legendary/nickname combinations, on this family only."""
    frames=data['frames'];nickname=bool(str(sem.get('nickname') or '').strip())
    if sem.get('legendary'):
        if nickname:
            # The native joined crown owns both bars and their single outline.
            frames[:]=[frame for frame in frames if not (
                'crown' in str(frame.get('name','')).lower()
                or 'Generic Showcase Title' in str(frame.get('name',''))
                or '/nickname/addons/' in str(frame.get('src','')))]
            joined={'name':'Compact land joined legendary crown',
                    'src':'/img/frames/proxy-foundry/godzilla/CrownJoinedL.png','masks':[],
                    'bounds':{'x':.024,'y':.0172,'width':.952,'height':.1286}}
            frames[0:0]=bar_layers(joined,sem)
        else:
            index=next(i for i,frame in enumerate(frames) if 'Floating.png' in str(frame.get('src','')))
            frames.insert(index,part('CrownOutline','Compact land crown black outline'))
        return

    # The original compact pinline also contains a separate title ring.
    # Its lower type/rules contours stay intact; the title owns its own outline.
    for frame in frames:
        for mask in frame.get('masks',[]):
            if mask.get('src')=='/img/frames/m15/boxTopper/short/pinline.svg':
                mask['src']=PREFIX+'lower-pinline.svg'
    if not nickname:return
    title=next(frame for frame in frames if 'Generic Showcase Title' in str(frame.get('name','')))
    title_code=title['src'].rsplit('Frame',1)[-1][0]
    frames[:]=[frame for frame in frames if not (
        'Generic Showcase Title' in str(frame.get('name',''))
        or '/nickname/addons/' in str(frame.get('src','')))]
    # Native frame order is reversed: title above subtitle, then lower frame.
    frames[0:0]=[part('Title'+title_code,'Compact land native title'),
                 *bar_layers(part('TrueNameL','Compact land cropped true-name bar'),sem)]
    data['text']['title']['y']-=GEOMETRY['textShift']
