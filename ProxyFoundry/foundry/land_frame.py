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

def fit_compact_land_rules(data):
    """Bound native text fitting by the visible panel, including flavor text."""
    rules=(data.get('text') or {}).get('rules')
    panel=next((frame.get('bounds') for frame in data.get('frames',[])
                if frame.get('name')=='50% Black Transparent Rules Fill'),None)
    if not isinstance(rules,dict) or not isinstance(panel,dict):return
    padding=max(.005,rules['y']-panel['y'])
    height=max(.01,panel['y']+panel['height']-padding-rules['y'])
    rules.update(height=min(rules['height'],height),bounded=True,oneLine=False)

def apply_compact_land_header(data,sem,bar_layers):
    """Four independent legendary/nickname combinations, on this family only."""
    fit_compact_land_rules(data)
    frames=data['frames'];nickname=bool(str(sem.get('nickname') or '').strip())
    # Restore native pinline opacity instead of the compact recipe's 60%.
    for frame in frames:
        if any(mask.get('name')=='Pinline' for mask in frame.get('masks',[])):
            frame.pop('opacity',None)
            # A flat gradient has no native PNG transparency of its own.
            # Restore that material alpha on every recolored rim, including
            # dual/tri/five-color and both legendary header branches.
            if str(frame.get('src','')).startswith('data:image/svg+xml') and not any(
                    mask.get('src')==PREFIX+'PinlineFade.png' for mask in frame['masks']):
                frame['masks'].append({'name':'Native compact pinline fade','src':PREFIX+'PinlineFade.png'})
    # Nonlegendary headers use the complete native Godzilla object below.
    for index,frame in enumerate(frames):
        if 'Generic Showcase Title' in str(frame.get('name','')):
            if sem.get('legendary'):
                code=frame['src'].rsplit('Frame',1)[-1][0]
                frames[index]=part('TitleBlack'+code,'Compact land black title')
            else:
                frames[index]={'name':'Compact land native Godzilla title',
                    'src':'/img/frames/proxy-foundry/godzilla/TitleL.png','masks':[],
                    'bounds':{'x':.0494,'y':.0405,'width':.9014,'height':.069}}
    if sem.get('legendary'):
        if nickname:
            # The native joined crown owns both bars and their single outline.
            frames[:]=[frame for frame in frames if not (
                'crown' in str(frame.get('name','')).lower()
                or frame.get('name')=='Compact land black title'
                or '/nickname/addons/' in str(frame.get('src','')))]
            joined={'name':'Compact land joined legendary crown',
                    'src':'/img/frames/proxy-foundry/godzilla/CrownJoinedL.png','masks':[],
                    'bounds':{'x':.024,'y':.0172,'width':.952,'height':.1286}}
            frames[0:0]=bar_layers(joined,sem)
            for frame in frames:
                if '/proxy-foundry/godzilla/CrownJoined' in str(frame.get('src','')):
                    code=frame['src'].rsplit('CrownJoined',1)[1][0]
                    frame['src']=PREFIX+'CrownJoinedBlack'+code+'.png'
        else:
            title_index=next(i for i,frame in enumerate(frames) if frame.get('name')=='Compact land black title')
            frames[title_index:title_index+1]=bar_layers({
                'name':'Compact land native Godzilla title',
                'src':'/img/frames/proxy-foundry/godzilla/TitleL.png','masks':[],
                'bounds':{'x':.0494,'y':.0405,'width':.9014,'height':.069}},sem)
            index=next(i for i,frame in enumerate(frames) if 'Floating.png' in str(frame.get('src','')))
            frames.insert(index,part('CrownOutline','Compact land crown black outline'))
        return

    # The original compact pinline also contains a separate title ring.
    # Its lower type/rules contours stay intact; the title owns its own outline.
    for frame in frames:
        for mask in frame.get('masks',[]):
            if mask.get('src')=='/img/frames/m15/boxTopper/short/pinline.svg':
                mask['src']=PREFIX+'lower-pinline.svg'
                # Preserve exactly the legendary recipe's native paint/alpha.
                # This mask removes only its now-redundant upper title ring.
    frames[:]=[frame for frame in frames if not (
        frame.get('name')=='Compact land native Godzilla title'
        or '/nickname/addons/' in str(frame.get('src','')))]
    joined={'name':'Compact land native Godzilla joined title' if nickname else 'Compact land native Godzilla title',
            'src':'/img/frames/proxy-foundry/godzilla/'+('TitleJoinedL.png' if nickname else 'TitleL.png'),
            'masks':[],'bounds':{'x':.0494,'y':.0405,'width':.9014,'height':.1053 if nickname else .069}}
    frames[0:0]=bar_layers(joined,sem)
