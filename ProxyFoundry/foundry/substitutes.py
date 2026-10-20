"""Derived substitute fronts; never imported cards or additional Scryfall faces."""
import copy
from pathlib import Path
from .domain import ORDINARY_GROUPS,render_key,stable_hash,type_group,uid
from .token_assignments import is_token

VERSION=3
SIGN=Path(__file__).resolve().parents[1]/'assets'/'substitutes'/'double-sided-substitute-sign.png'
WALL=SIGN.with_name('double-sided-substitute-wall.png')
# Battle's ordinary artBounds extend behind its title and rules frame. Keep
# the complete instruction sign between the bars instead, with a small inset.
BATTLE_SIGN_BOUNDS={'x':268/2100,'y':225/1500,'width':1700/2100,'height':605/1500}


def required(card,settings):
    if not settings.get('createDfcSubstitutes',True):return False
    if not (len(card.get('faces',[]))==2 or card.get('meldBackAsset') or (card.get('scryfall') or {}).get('_meld_result')):return False
    sf=card.get('scryfall') or {}
    if not sf or is_token(card,settings):return False
    front=(sf.get('card_faces') or [sf])[0]
    return bool(set(str(front.get('type_line') or sf.get('type_line') or '').split()) & {'Creature','Artifact','Enchantment','Land','Planeswalker','Battle','Instant','Sorcery'})


def stored_faces(card):
    faces=card.get('faces',[])
    return [*faces,card['substitute']] if card.get('substitute') else faces


def render_faces(card,settings):
    return stored_faces(card) if required(card,settings) else card.get('faces',[])


def face_count(card,settings):
    return len(card.get('faces',[]))+int(required(card,settings))


def current(card):
    source=((card.get('faces') or [{}])[0].get('compiled') or {}).get('renderKey')
    substitute=card.get('substitute') or {}
    return bool(source and substitute.get('sourceRenderKey')==source and substitute.get('substituteVersion')==VERSION and substitute.get('compiled'))


def full_art(compiled):
    data=compiled['data'];bounds=data.get('artBounds') or {}
    if data.get('version')=='battle':return False
    return data.get('version')=='m15Nickname' or float(bounds.get('height',0))>.6 or float(bounds.get('y',1))<.08


def build(workspace,deck,card,settings):
    if not required(card,settings):
        return card.pop('substitute',None) is not None
    front=card['faces'][0];source=front.get('compiled')
    if not source or front.get('error'):
        card.pop('substitute',None);return False
    if current(card):return False
    from .images import ingest_image
    sign=getattr(workspace,'_substitute_sign',None)
    if not sign or not workspace.store.asset(sign['id']):
        sign=ingest_image(workspace.store,SIGN.read_bytes());workspace._substitute_sign=sign
    wall=getattr(workspace,'_substitute_wall',None)
    if not wall or not workspace.store.asset(wall['id']):
        wall=ingest_image(workspace.store,WALL.read_bytes());workspace._substitute_wall=wall
    if full_art(source):
        sf=card['scryfall'];face=(sf.get('card_faces') or [sf])[0]
        standalone={**sf,**face,'layout':'normal'}
        standalone.pop('card_faces',None);standalone.pop('_meld_result',None)
        group=type_group(standalone,standalone,0)
        options=copy.deepcopy(front)
        for key in ('compiled','lastRender','fit','rawCard'):options.pop(key,None)
        options['templateOverride']='normal' if group in ORDINARY_GROUPS else 'auto'
        compiled=workspace.compiler.compile_face(standalone,standalone,0,options,settings,sign['id'],art_origin='Scryfall selected printing')
        # Preserve the already-resolved rules, nickname and flavor overrides.
        for name in ('title','nickname','mana','type','rules','flavor','pt'):
            field=(compiled['data'].get('text') or {}).get(name)
            original=(source['data'].get('text') or {}).get(name)
            if isinstance(field,dict) and isinstance(original,dict):field['text']=original.get('text','')
    else:compiled=copy.deepcopy(source)
    data=compiled['data']
    if data.get('version')=='battle':data['artBounds']=copy.deepcopy(BATTLE_SIGN_BOUNDS)
    bounds=data['artBounds']
    width=data['width'];height=data['height']
    # Contain, never cover: every word of the instructions must survive fitting.
    scale=min(bounds['width']*width/sign['width'],bounds['height']*height/sign['height'])
    # Native frames draw last-to-first. The sign sits over the wall art and
    # below the original frame, without changing any normal frame geometry.
    data['frames'].append({'name':'Substitute instruction sign','src':'/api/assets/'+sign['id'],'masks':[],
        'bounds':{'x':bounds['x']+(bounds['width']-scale*sign['width']/width)/2,
            'y':bounds['y']+(bounds['height']-scale*sign['height']/height)/2,
            'width':scale*sign['width']/width,'height':scale*sign['height']/height}})
    wall_scale=height/wall['height']
    data.update(artSource='/api/assets/'+wall['id'],artZoom=wall_scale,artRotate='0',
        artX=(width-wall['width']*wall_scale)/width/2,artY=0,
        infoArtist='OpenAI image generation')
    ident=(card.get('substitute') or {}).get('id') or uid()
    content=render_key(data,wall['id'],VERSION)
    key=stable_hash({'content':content,'deck':deck['id'],'face':ident})
    compiled.update(data=data,artId=wall['id'],artOrigin='Bundled substitute sign and wall',exportArtUrl=None,
        artist='OpenAI image generation',recipe='DFC substitute',renderKey=key,contentRenderKey=content,
        render=workspace.store.render_get(key),crop={'warning':False,'intentionalArtWindow':True},flags=[])
    card['substitute']={'id':ident,'name':front['name']+' — substitute','index':0,'compiled':compiled,
        'sourceRenderKey':source['renderKey'],'substituteVersion':VERSION}
    return True
