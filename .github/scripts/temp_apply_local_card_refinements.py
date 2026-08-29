from pathlib import Path
import json, copy

ROOT=Path('.')
DOC=ROOT/'doctor_who/doctor_who_cards.cardconjurer'
DER=ROOT/'derevi/derevi_cards.cardconjurer'
WHITE_OPACITY=85
GENERIC_ART_BOUNDS={'x':0,'y':0,'width':1,'height':0.9224}
GENERIC_ART=(0.0,-0.0745142857142857,1.962890625,'0')
GENERIC_SET_BOUNDS={'x':0.9213,'y':0.591,'width':0.12,'height':0.041,'vertical':'center','horizontal':'right'}
GENERIC_SET_Y=0.5692963752665245
COMPACT_SET_BOUNDS={'x':0.9213,'y':0.6343,'width':0.12,'height':0.041,'vertical':'center','horizontal':'right'}
COMPACT_SET_Y=0.6125963752665246
GENERIC_WATERMARK={'x':0.5,'y':0.7762,'width':0.75,'height':0.2305}
color_src={c:f'/img/frames/m15/genericShowcase/m15GenericShowcaseFrame{c}.png' for c in 'WUBRGM'}
short_land_src={'W':'/img/frames/m15/boxTopper/short/wl.png','U':'/img/frames/m15/boxTopper/short/ul.png','B':'/img/frames/m15/boxTopper/short/bl.png','R':'/img/frames/m15/boxTopper/short/rl.png','G':'/img/frames/m15/boxTopper/short/gl.png','M':'/img/frames/m15/boxTopper/short/ml.png'}
land_neutral='/img/frames/m15/genericShowcase/m15GenericShowcaseFrameL.png'
short_neutral='/img/frames/m15/boxTopper/short/l.png'
RIGHT={'src':'/img/frames/maskRightHalf.png','name':'Right Half'}

def mask(src,name): return {'src':src,'name':name}

def set_generic_layout(c):
    c['version']='genericShowcase'; c['artBounds']=copy.deepcopy(GENERIC_ART_BOUNDS)
    c['artX'],c['artY'],c['artZoom'],c['artRotate']=GENERIC_ART
    c['setSymbolBounds']=copy.deepcopy(GENERIC_SET_BOUNDS); c['setSymbolY']=GENERIC_SET_Y
    c['watermarkBounds']=copy.deepcopy(GENERIC_WATERMARK); c['watermarkY']=0.7762
    t=c['text']; title=t['title']; typ=t['type']; r=t['rules']
    title.update(x=0.0854,y=0.0522,width=0.8292,height=0.0543,color='white')
    typ.update(x=0.0854,y=0.5664,width=0.8292,height=0.0543,color='white'); typ.pop('shadowX',None); typ.pop('shadowY',None)
    r.update(x=0.105,y=0.6303,width=0.79,height=0.2875,color='white'); r.pop('noVerticalCenter',None)

def make_generic_frames(colors,legendary=False):
    frames=[]
    if legendary:
        frames += [
            {'name':'Legend Crown Outline','src':'/img/frames/m15/crowns/m15CrownFloatingOutline.png','masks':[],'bounds':{'x':0.028,'y':0.0172,'width':0.944,'height':0.1062}},
            {'name':'Land Legend Crown','src':'/img/frames/m15/crowns/m15CrownLFloating.png','masks':[],'bounds':{'x':0.0307,'y':0.0191,'width':0.9387,'height':0.1024}},
            {'name':'Legend Crown Lower Cutout','src':'/img/black.png','masks':[],'bounds':{'x':0.0734,'y':0.1096,'width':0.8532,'height':0.0143},'erase':True},
        ]
    if len(colors)==1:
        a=colors[0]; frames.append({'name':f'{a} Pinline','src':color_src[a],'masks':[mask('/img/frames/m15/genericShowcase/m15GenericShowcaseMaskPinline.png','Pinline')]})
    else:
        a,b=colors; frames += [
            {'name':f'{a} Pinline','src':color_src[a],'masks':[mask('/img/frames/m15/genericShowcase/m15GenericShowcaseMaskPinline.png','Pinline')]},
            {'name':f'{b} Pinline','src':color_src[b],'masks':[mask('/img/frames/m15/genericShowcase/m15GenericShowcaseMaskPinline.png','Pinline'),copy.deepcopy(RIGHT)]},
        ]
    frames += [
        {'name':'Neutral Land Title','src':land_neutral,'masks':[mask('/img/frames/m15/regular/m15MaskTitle.png','Title')]},
        {'name':'Neutral Land Type','src':land_neutral,'masks':[mask('/img/frames/m15/regular/m15MaskType.png','Type')]},
    ]
    if len(colors)==1:
        a=colors[0]; f={'name':f'{a} Rules','src':color_src[a],'masks':[mask('/img/frames/m15/regular/m15MaskRules.png','Rules')]}
        if a=='W': f['opacity']=WHITE_OPACITY
        frames.append(f)
    else:
        a,b=colors
        fa={'name':f'{a} Rules','src':color_src[a],'masks':[mask('/img/frames/m15/regular/m15MaskRules.png','Rules')]}
        fb={'name':f'{b} Rules','src':color_src[b],'masks':[mask('/img/frames/m15/regular/m15MaskRules.png','Rules'),copy.deepcopy(RIGHT)]}
        if a=='W': fa['opacity']=WHITE_OPACITY
        if b=='W': fb['opacity']=WHITE_OPACITY
        frames += [fa,fb]
    frames.append({'name':'Land Frame','src':land_neutral,'masks':[mask('/img/frames/m15/regular/m15MaskBorder.png','Border')]})
    return frames

def make_compact_frames(colors):
    frames=[]
    if len(colors)==1:
        a=colors[0]; frames.append({'name':f'{a} Compact Pinline','src':short_land_src[a],'masks':[mask('/img/frames/m15/boxTopper/short/pinline.svg','Pinline')]})
    else:
        a,b=colors; frames += [
            {'name':f'{a} Compact Pinline','src':short_land_src[a],'masks':[mask('/img/frames/m15/boxTopper/short/pinline.svg','Pinline')]},
            {'name':f'{b} Compact Pinline','src':short_land_src[b],'masks':[mask('/img/frames/m15/boxTopper/short/pinline.svg','Pinline'),copy.deepcopy(RIGHT)]},
        ]
    frames += [
        {'name':'Neutral Land Title','src':land_neutral,'masks':[mask('/img/frames/m15/regular/m15MaskTitle.png','Title')]},
        {'name':'Neutral Compact Land Type','src':short_neutral,'masks':[mask('/img/frames/m15/boxTopper/short/type.png','Type')]},
    ]
    if len(colors)==1:
        a=colors[0]; f={'name':f'{a} Compact Rules','src':short_land_src[a],'masks':[mask('/img/frames/m15/boxTopper/short/text.svg','Rules')]}
        if a=='W': f['opacity']=WHITE_OPACITY
        frames.append(f)
    else:
        a,b=colors
        fa={'name':f'{a} Compact Rules','src':short_land_src[a],'masks':[mask('/img/frames/m15/boxTopper/short/text.svg','Rules')]}
        fb={'name':f'{b} Compact Rules','src':short_land_src[b],'masks':[mask('/img/frames/m15/boxTopper/short/text.svg','Rules'),copy.deepcopy(RIGHT)]}
        if a=='W': fa['opacity']=WHITE_OPACITY
        if b=='W': fb['opacity']=WHITE_OPACITY
        frames += [fa,fb]
    frames.append({'name':'Land Frame','src':land_neutral,'masks':[mask('/img/frames/m15/regular/m15MaskBorder.png','Border')]})
    return frames

def set_compact(c,colors):
    c['version']='genericShowcase'; c['frames']=make_compact_frames(colors)
    c['artBounds']=copy.deepcopy(GENERIC_ART_BOUNDS); c['artX'],c['artY'],c['artZoom'],c['artRotate']=GENERIC_ART
    c['setSymbolBounds']=copy.deepcopy(COMPACT_SET_BOUNDS); c['setSymbolY']=COMPACT_SET_Y
    c['watermarkBounds']=copy.deepcopy(GENERIC_WATERMARK); c['watermarkY']=0.7762
    t=c['text']; t['title'].update(x=0.0854,y=0.0522,width=0.8292,height=0.0543,color='white')
    t['type'].update(x=0.0854,y=0.61,width=0.8292,height=0.0543,color='white',shadowX=0.0014,shadowY=0.001)
    r=t['rules']; r.update(x=0.105,y=0.6743,width=0.79,height=0.2448,color='white',align='center'); r.pop('noVerticalCenter',None)

def tune_white(cards):
    for e in cards:
        for f in e['data'].get('frames',[]):
            if not any(m.get('name')=='Rules' for m in f.get('masks',[])): continue
            src=f.get('src','')
            if src.endswith('m15GenericShowcaseFrameW.png') or src.endswith('/boxTopper/short/wl.png'): f['opacity']=WHITE_OPACITY

def fix_modal(cards):
    es=next(e['data'] for e in cards if e['key']=='Esika, God of the Tree'); br=next(e['data'] for e in cards if e['key']=='The Prismatic Bridge')
    for c in (es,br):
        c['text']['rules'].update(height=0.24,size=0.0315,x=0.086,width=0.828); c['text']['rules'].pop('noVerticalCenter',None)
        c['text']['flipsideType'].update(x=0.068,y=0.892,width=0.364)
        c['text']['flipSideReminder'].update(x=0.068,y=0.892,width=0.364)
    es['text']['flipsideType']['text']='Enchantment'; es['text']['flipSideReminder']['text']='{W}{U}{B}{R}{G}'
    br['text']['flipsideType']['text']='Creature'; br['text']['flipSideReminder']['text']='{1}{G}{G}'
    old=br['frames']; pick=lambda pred:[f for f in old if pred(f)]
    crown=pick(lambda f:f['name']=='Multicolored Legend Crown'); cover=pick(lambda f:f['name']=='Legend Crown Border Cover')
    reminder=pick(lambda f:any(m.get('name')=='Flipside' for m in f.get('masks',[]))); arrow=pick(lambda f:any(m.get('name')=='MDFC Arrow' for m in f.get('masks',[])))
    nyx_pin=pick(lambda f:'Nyx' in f['name'] and any(m.get('name')=='Pinline' for m in f.get('masks',[])))
    nyx_type=pick(lambda f:'Nyx' in f['name'] and any(m.get('name')=='Type' for m in f.get('masks',[])))
    nyx_rules=pick(lambda f:'Nyx' in f['name'] and any(m.get('name')=='Rules' for m in f.get('masks',[])))
    back='/img/frames/modal/regular/mb.png'
    br['frames']=crown+cover+reminder+arrow+nyx_pin+[{'name':'Multicolored Frame (Back)','src':back,'masks':[mask('/img/frames/modal/regular/title.svg','Title')]}]+nyx_type+nyx_rules+[
        {'name':'Multicolored Frame (Back)','src':back,'masks':[mask('/img/frames/modal/regular/frame.svg','Frame')]},
        {'name':'Multicolored Frame (Back)','src':back,'masks':[mask('/img/frames/modal/regular/border.svg','Border')]},]

def get(cards,key): return next(e['data'] for e in cards if e['key']==key)
def masks(c): return [m.get('src') for f in c.get('frames',[]) for m in f.get('masks',[])]
def rules_frames(c): return [f for f in c.get('frames',[]) if any(m.get('name')=='Rules' for m in f.get('masks',[]))]

def main():
    doc=json.loads(DOC.read_text()); der=json.loads(DER.read_text())
    sparse={'Forest':['G'],'Mountain':['R'],'Swamp':['B'],'Plains':['W'],'Island':['U'],'Savannah':['G','W'],'Tropical Island':['G','U'],'Tundra':['W','U']}
    for e in doc:
        if e['key'] in sparse: set_compact(e['data'],sparse[e['key']])
    for k,(colors,legendary) in {"Gaea's Cradle":(['G'],True),'Reflecting Pool':(['M'],False),'Mana Confluence':(['M'],False)}.items():
        c=get(doc,k); set_generic_layout(c); c['frames']=make_generic_frames(colors,legendary); c['text']['rules']['align']='left'
    tune_white(doc); fix_modal(doc)
    for k,colors in {'Savannah':['G','W'],'Tropical Island':['G','U'],'Tundra':['W','U']}.items(): set_compact(get(der,k),colors)
    tune_white(der)
    assert len(doc)==51 and len({e['key'] for e in doc})==51
    for k in sparse:
        c=get(doc,k); assert c['version']=='genericShowcase'; assert '/img/frames/m15/boxTopper/short/text.svg' in masks(c); assert '/img/frames/m15/boxTopper/short/frame.svg' not in masks(c)
    for k in ["Gaea's Cradle",'Reflecting Pool','Mana Confluence']:
        c=get(doc,k); assert '/img/frames/m15/boxTopper/short/text.svg' not in masks(c)
    for cards in (doc,der):
        for e in cards:
            for f in rules_frames(e['data']):
                src=f.get('src','')
                if src.endswith('m15GenericShowcaseFrameW.png') or src.endswith('/boxTopper/short/wl.png'): assert f.get('opacity')==85
    for k in ['Esika, God of the Tree','The Prismatic Bridge']:
        c=get(doc,k); assert c['text']['rules']['y']+c['text']['rules']['height'] < c['text']['flipsideType']['y']
    DOC.write_text(json.dumps(doc,separators=(',',':'))); DER.write_text(json.dumps(der,separators=(',',':')))
    print('refinements applied and validated')

if __name__=='__main__': main()
