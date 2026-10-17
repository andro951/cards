"""Native Godzilla-style planeswalker and modal nickname packs.

The upstream PNGs stay unchanged. Optional subtitles are hidden with a mask;
all material, crowns, arrows and loyalty pieces come from the pinned library.
"""
import copy
from urllib.parse import quote
from .legacy import compiler as native
from .domain import ValidationError
from .planeswalker_frame import PREFIX as PW_PREFIX,TALL_SHIFT


def subtitle_cutout(top, bottom):
    # An erase mask also removes any later color-overlay layers in this band.
    # It acts on the frame canvas, leaving the artwork behind it intact.
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="2100"><rect y="{top}" width="1500" height="{bottom-top}" fill="white"/></svg>'
    return {'name':'Hide unused true-name strip','src':'data:image/svg+xml;utf8,'+quote(svg),'masks':[],'erase':True}


def names(data, sem, x, y, width, height, true_y):
    text=data['text'];nickname=str(sem.get('nickname') or '').strip()
    main={'name':'Nickname' if nickname else 'Title','text':nickname or sem['name'],
          'x':x,'y':y,'width':width,'height':height,'size':.0381,
          'font':'belerenb','oneLine':True,'color':'white',
          'outlineColor':'black','outlineWidth':.0025,'shadowX':0,'shadowY':0}
    text.pop('nickname',None)
    if nickname:
        text['nickname']=main
        text['title']={'name':'Title','text':sem['name'],'x':.14,'y':true_y,
                       'width':.72,'height':.0243,'size':.0229,'font':'mplantini',
                       'oneLine':True,'align':'center','color':'white',
                       'outlineColor':'black','outlineWidth':.001,'shadowX':0,'shadowY':0}
    else:text['title']=main
    text['mana']['text']=str(sem.get('mana_cost') or '')
    # Both main-title variants reserve the mana cluster, without narrowing the
    # centered true name underneath it.
    main['width']=min(width,native.title_width(str(sem.get('mana_cost') or ''),data['width'])-(x-.0854))
    return bool(nickname)


def apply_planeswalker(data, sem, code):
    code='L' if code=='C' else code
    abilities=native.parse_planeswalker_abilities(sem.get('oracle_text',''))
    if not 1<=len(abilities)<=4:
        raise ValidationError('The Godzilla planeswalker frame supports one to four ability rows.')
    nickname=bool(str(sem.get('nickname') or '').strip())
    tall=len(abilities)==4
    shift=TALL_SHIFT if tall else 0
    frame={'name':'Native planeswalker nickname frame',
           'src':PW_PREFIX+f'FrameTall{code}.png' if tall else f'/img/frames/planeswalker/nickname/planeswalkerNicknameFrame{code}.png',
           'masks':[]}
    data['frames']=([subtitle_cutout(211,300)] if not nickname else [])+[frame]
    if sem.get('legendary'):
        # Nicknames use the joined crown. Without a nickname, the normal crown
        # surrounds a separate Godzilla title; no cropped subtitle shoulders.
        header_cutout=subtitle_cutout(0,310)
        header_cutout['name']='Native planeswalker header cutout'
        if nickname:
            data['frames']=[{'name':'Planeswalker legendary crown',
                'src':f'/img/frames/proxy-foundry/godzilla/CrownJoined{code}.png',
                'masks':[],'bounds':{'x':.024,'y':.0058,'width':.952,'height':.1286}},header_cutout,frame]
        else:
            data['frames']=[{'name':'Normal planeswalker legendary crown',
                'src':f'/img/frames/m15/crowns/m15Crown{code}Floating.png','masks':[],
                'bounds':{'x':.0307,'y':.0077,'width':.9387,'height':.1024}},
                {'name':'Planeswalker Godzilla title',
                 'src':f'/img/frames/proxy-foundry/godzilla/Title{code}.png','masks':[],
                 'bounds':{'x':.0494,'y':.0291,'width':.9014,'height':.069}},
                {'name':'Normal crown outline','src':'/img/frames/m15/crowns/m15CrownFloatingOutline.png','masks':[],
                 'bounds':{'x':.028,'y':.0058,'width':.944,'height':.1062}},header_cutout,frame]
    data['version']='planeswalkerNicknameTall' if tall else 'planeswalkerNickname'
    data['onload']='/js/frames/versionPlaneswalker.js'
    data['setSymbolBounds']={'x':.9227,'y':.5891-shift,'width':.12,'height':.0381,'vertical':'center','horizontal':'right'}
    text=data['text']
    text['mana'].update(y=.0481)
    names(data,sem,.0867,.0408 if sem.get('legendary') else .0372,.8267,.0548,.1015)
    text['type'].update(x=.0867,y=.5625-shift,width=.8267,height=.0548,size=.0324)
    text.pop('rules',None);text.pop('flavor',None);text.pop('pt',None)
    # Geometry and badge positions are assigned once, after frame selection,
    # by planeswalker_frame.layout_planeswalker_abilities.
    for index in range(4):
        cost,oracle=abilities[index] if index<len(abilities) else ('','')
        text[f'ability{index}']={'name':f'Ability {index+1}','text':native.italicize_dash_labels(oracle),
            'color':'black','outlineColor':'black','outlineWidth':0,'shadowX':0,'shadowY':0}
    data['planeswalker']={'abilities':[c for c,_ in abilities]+['']*(4-len(abilities)),
        'count':len(abilities)}
    text['loyalty']={'name':'Loyalty','text':str(sem.get('loyalty') or ''),
        'x':.806,'y':.902,'width':.14,'height':.0372,'size':.0372,
        'font':'belerenbsc','oneLine':True,'align':'center','color':'white'}
    return nickname


def apply_modal(data, sem, group, code, other_code, pt_src):
    code='A' if code=='C' else code
    other_code='A' if other_code=='C' else other_code
    side='b' if group=='modal-back' else 'f'
    src=f'/img/frames/modal/nickname/{code.lower()}{side}.png'
    other_src=f'/img/frames/modal/nickname/{other_code.lower()}{side}.png'
    nickname=bool(str(sem.get('nickname') or '').strip())
    frame={'name':'Native modal nickname '+('back' if side=='b' else 'front'),
           'src':src,'masks':[]}
    frames=[{'name':'Opposite-face reminder material','src':other_src,
             'masks':[{'name':'Flipside','src':'/img/frames/modal/regular/reminder.svg'}]},frame]
    if not nickname:frames.insert(0,subtitle_cutout(236,315))
    if sem.get('legendary'):
        crown={'name':'Modal legendary nickname crown' if nickname else 'Modal legendary crown',
               'src':f'/img/frames/modal/crowns/{"nickname" if nickname else "floating"}/{code.lower()}.png',
               'masks':[], 'bounds':({'x':.0234,'y':.0167,'width':.952,'height':.1286} if nickname
                                   else {'x':.0307,'y':.0191,'width':.9387,'height':.1024})}
        frames[0:0]=[crown,{'name':'Native modal crown cutout',
            'src':'/img/frames/modal/nickname/cutout.svg' if nickname else '/img/frames/modal/crowns/cutout.svg',
            'masks':[],'erase':True}]
    pt=str((data['text'].get('pt') or {}).get('text') or '')
    if pt:
        frames.insert(0,{'name':'Power/Toughness','src':pt_src,'masks':[],
                        'bounds':{'x':.7573,'y':.8848,'width':.188,'height':.0733}})
    data['frames']=frames;data['version']='modalNickname';data['onload']=None
    data['setSymbolBounds']={'x':.9213,'y':.591,'width':.12,'height':.041,'vertical':'center','horizontal':'right'}
    text=data['text']
    names(data,sem,.1614,.0522,.7534,.0543,.1129)
    text['type'].update(x=.0854,y=.5664,width=.8292,height=.0543,size=.0324)
    text['rules'].update(x=.086,y=.6303,width=.828,height=.249,size=.0362,fontSize=0)
    # The native footer has two separate fields so its mana symbols stay native.
    template=native.LAYOUTS['modal_dfc_front']['data']['text']
    for key in ('flipsideType','flipSideReminder'):text[key]=copy.deepcopy(template[key])
    text.setdefault('pt',{'name':'Power/Toughness','text':pt,'font':'belerenbsc','oneLine':True,'align':'center'}).update(x=.7928,y=.902,width=.1367,height=.0372,size=.0372,
                      outlineWidth=0,shadowX=0,shadowY=0,color='black' if code in 'WAC' else 'white')
    return nickname
