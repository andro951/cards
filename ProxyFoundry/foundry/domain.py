"""Pure deck, cache, template and art-window rules. No network or file effects."""
from __future__ import annotations
import copy, hashlib, json, math, re, unicodedata, uuid
from typing import Any
from urllib.parse import unquote, urlsplit
DAY=86400
CACHE_NORMAL_SECONDS=365*DAY
CACHE_REFRESH_SECONDS=7*DAY
RARITIES=('common','uncommon','rare','mythic')
IMAGE_EXTENSIONS={'.png','.jpg','.jpeg','.webp','.gif','.svg'}
CC_COMMIT='2fcddba8966156d484cedf54d8214996748dd5e1'
CC_REPO='Investigamer/cardconjurer'
COMPAT_COMMIT='47087b3fc21e2cef61c58b9ebf180968ee991658'
COMPAT_REPO='d1rtyskittl3z/Card-Cipherist'
SCHEMA_VERSION=2
STATION_SCRIPT_URL='https://cardconjurer.app/js/frames/versionStation.js'
STATION_SCRIPT_SHA256='481c2be522fc10089e75aa6281aace9e88e345868330948dd64705edb9314c21'
# Bump PIPELINE_VERSION only when a common compiler/renderer change can alter many card outputs.
PIPELINE_VERSION='card-tools-v58/credits-v1/pipeline-v13'
# Backward-compatible name used by saved compiled faces and older callers.
GENERATION_VERSION=PIPELINE_VERSION
class ValidationError(ValueError): pass
class ConflictError(ValidationError): pass

def uid(): return str(uuid.uuid4())
def stable_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def slug(text):
    text=unicodedata.normalize('NFKD',str(text))
    text=''.join(c for c in text if not unicodedata.combining(c)).replace('Æ','AE').replace('æ','ae').replace('Œ','OE').replace('œ','oe')
    return re.sub(r'[^A-Za-z0-9]+','_',re.sub(r"['’]",'',text)).strip('_').lower()
def quantity(value):
    try: n=int(value)
    except (ValueError,TypeError,OverflowError) as e: raise ValidationError('Quantity must be a whole number.') from e
    if isinstance(value,bool) or str(value).strip()!=str(n) or not 1<=n<=9999:
        raise ValidationError('Quantity must be a whole number between 1 and 9,999.')
    return n

def cache_is_fresh(fetched_at,now,refresh=False):
    return fetched_at is not None and max(0.,now-fetched_at)<(CACHE_REFRESH_SECONDS if refresh else CACHE_NORMAL_SECONDS)

def github_location(raw,branch=None):
    raw=str(raw).strip()
    if not raw or re.match(r'^[A-Za-z]:[\\/]',raw) or raw.startswith(('\\\\','file:')):
        raise ValidationError('Choose Computer folder for local files, or paste a GitHub folder URL.')
    defaulted=False
    if '://' not in raw: raw='https://github.com/'+raw.strip('/')
    u=urlsplit(raw)
    try: bad=u.port is not None
    except ValueError: bad=True
    if u.scheme!='https' or u.username or u.password or bad: raise ValidationError('Use an HTTPS GitHub folder URL.')
    p=[x for x in u.path.strip('/').split('/') if x]
    if u.hostname=='raw.githubusercontent.com' and len(p)>=3:
        owner,repo,ref=map(unquote,p[:3]);folder='/'.join(map(unquote,p[3:]))
    elif u.hostname in {'github.com','www.github.com'} and len(p)>=2:
        owner,repo=map(unquote,p[:2])
        if len(p)>=4 and p[2] in {'tree','blob'}:ref=unquote(p[3]);folder='/'.join(map(unquote,p[4:]))
        else:ref=branch or 'main';folder='/'.join(map(unquote,p[2:]));defaulted=not bool(branch)
    else: raise ValidationError('Use github.com/owner/repository/tree/ref/folder.')
    if branch:ref=str(branch).strip()
    for item in [owner,repo,*ref.split('/'),*folder.split('/')]:
        if item in {'.','..'} or '\\' in item or '\x00' in item: raise ValidationError('Invalid GitHub folder or ref.')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+',owner) or not re.fullmatch(r'[A-Za-z0-9_.-]+',repo):raise ValidationError('Invalid GitHub repository.')
    return {'repo':owner+'/'+repo.removesuffix('.git'),'ref':ref,'folder':folder,'default_ref':defaulted}

def parse_deck_text(text,include_outside=False):
    section='mainboard';rows=[]
    headings={'commander','commanders','deck','mainboard','main deck','lands','nonlands','sideboard','maybeboard','outside the game','outside_the_game','companion'}
    for lineno,line in enumerate(str(text).splitlines(),1):
        line=line.strip().lstrip('\ufeff')
        if not line or line.startswith(('#','//')):continue
        header=line.rstrip(':').strip().lower()
        if header in headings:section=header.replace(' ','_');continue
        if section in {'sideboard','maybeboard'} or section=='outside_the_game' and not include_outside:continue
        line=re.sub(r'\s+\*[A-Z]\*\s*$','',line)
        m=re.match(r'^(\d+)\s*[xX]?\s+(.+)$',line)
        count,name=(quantity(m[1]),m[2].strip()) if m else (1,line)
        printing=re.match(r'^(.*?)\s+\(([A-Za-z0-9]+)\)\s+([A-Za-z0-9★†-]+)(?:\s+.*)?$',name)
        row={'source':name,'name':name,'quantity':count,'section':section,'line':lineno}
        if printing:row.update(name=printing[1],source=printing[2].lower()+':'+printing[3],set=printing[2].lower(),collector_number=printing[3])
        rows.append(row)
    if not rows:raise ValidationError('No cards found. Paste one card per line, for example: 1 Sol Ring (CMM) 396.')
    if sum(x['quantity'] for x in rows)>10000:raise ValidationError('Deck limit is 10,000 physical cards.')
    return rows

GROUP_LABELS={'standard':'Nonlegendary cards','legendary':'Legendary cards','land':'Nonlegendary lands','legendary-land':'Legendary lands','basic-land':'Basic lands','modal-front':'Modal DFC · front','modal-back':'Modal DFC · back','transform-front':'Transform · front','transform-back':'Transform · back','saga':'Sagas','saga-creature':'Saga creatures','planeswalker':'Planeswalkers','prepare':'Prepare cards','battle':'Battles','class':'Classes','case':'Cases','room':'Rooms','special-land':'Special lands','split':'Split / aftermath','flip':'Flip cards','adventure':'Adventure cards','meld':'Meld cards','token':'Tokens','emblem':'Emblems','planar':'Planes / phenomena','scheme':'Schemes','vanguard':'Vanguards','art-series':'Art series','prototype':'Prototype cards','dungeon':'Dungeons','conspiracy':'Conspiracies','station':'Stations / Spacecraft'}
ORDINARY_GROUPS={'standard','legendary','land','legendary-land','basic-land'}
def type_group(face,parent=None,index=0):
    parent=parent or face
    layout=str(parent.get('layout') or face.get('scryfall_layout') or 'normal')
    if layout=='meld' and parent.get('_meld_proxy'):layout='normal'
    tl=str(face.get('type_line') or '').lower()
    if not tl:
        tl=(' '.join(face.get('types',[]))+' — '+' '.join(face.get('subtypes',[]))).lower()
        if face.get('legendary'):tl='legendary '+tl
        if face.get('basic'):tl='basic '+tl
    types,_,subtypes=tl.replace(' - ',' — ').partition(' — ')
    if layout=='modal_dfc':return 'modal-back' if index else 'modal-front'
    if layout in {'transform','double_faced_token','reversible_card'}:return 'transform-back' if index else 'transform-front'
    if 'room' in subtypes.split():return 'room'
    if layout in {'split','flip','adventure','meld','planar','scheme','vanguard','art_series','prototype'}:return layout.replace('_','-')
    if layout=='prepare' or face.get('prepared_spell'):return 'prepare'
    if 'saga' in subtypes:return 'saga-creature' if 'creature' in types else 'saga'
    if 'planeswalker' in types:return 'planeswalker'
    if 'battle' in types:return 'battle'
    if 'spacecraft' in subtypes or re.search(r'\bStation\b',str(face.get('oracle_text',''))):return 'station'
    for special in ('class','case'):
        if special in subtypes.split():return special
    for special in ('dungeon','conspiracy'):
        if special in types:return special
    if 'land' in types:
        # Enchantment lands use the ordinary land frame family; the displayed
        # type line still keeps Enchantment. Creature lands remain structurally
        # special because they need simultaneous land and P/T treatment.
        if 'creature' in types:return 'special-land'
        if 'basic' in types:return 'basic-land'
        return 'legendary-land' if 'legendary' in types else 'land'
    if layout in {'token','emblem'}:return layout
    return 'legendary' if 'legendary' in types else 'standard'
def is_legendary(face):return bool(face.get('legendary') or 'Legendary' in str(face.get('type_line','')).split(' — ')[0].split())

def crop_metrics(iw,ih,data,threshold=.20):
    if min(iw,ih)<=0:raise ValidationError('Artwork has invalid dimensions.')
    b=data.get('artBounds') or {'x':0,'y':0,'width':1,'height':1}
    cw,ch=int(data.get('width',2010)),int(data.get('height',2814));bw,bh=float(b['width'])*cw,float(b['height'])*ch
    if min(bw,bh)<=0:raise ValidationError('The template has an invalid art window.')
    zoom=max(bw/iw,bh/ih)
    lost_x=max(0.,min(1.,1-bw/(iw*zoom)));lost_y=max(0.,min(1.,1-bh/(ih*zoom)))
    # Report the actual placement as well as the ratio-based auto-fit warning.
    if float(data.get('artRotate',0) or 0)%360==0 and float(data.get('artZoom',0) or 0)>0:
        z=float(data['artZoom']);ax=float(data.get('artX',0))*cw;ay=float(data.get('artY',0))*ch
        wx=float(b.get('x',0))*cw;wy=float(b.get('y',0))*ch
        vx=max(0.,min(ax+iw*z,wx+bw)-max(ax,wx));vy=max(0.,min(ay+ih*z,wy+bh)-max(ay,wy))
        lost_x=max(lost_x,1-vx/(iw*z));lost_y=max(lost_y,1-vy/(ih*z))
    return {'width':iw,'height':ih,'windowWidth':round(bw),'windowHeight':round(bh),'cropX':round(lost_x,6),'cropY':round(lost_y,6),'warning':max(lost_x,lost_y)>threshold+1e-9,'threshold':threshold}
def render_key(data,art_digest='',template_version=1):
    payload={'renderer':CC_COMMIT,'compiler':PIPELINE_VERSION,'adapter':4,'art':art_digest,'data':data}
    # Version 1 is the pre-versioning baseline, so existing valid render-cache keys
    # remain usable. Bumping only one template to 2+ salts only that template's cards.
    if template_version!=1:payload['template']=template_version
    return stable_hash(payload)

def validate_template(entry):
    if isinstance(entry,list):
        if len(entry)!=1:raise ValidationError('Choose one template face at a time.')
        entry=entry[0]
    if not isinstance(entry,dict):raise ValidationError('A template must be a CardConjurer object.')
    d=copy.deepcopy(entry.get('data',entry))
    if not isinstance(d.get('frames'),list) or not isinstance(d.get('text'),dict):raise ValidationError('The template needs frames[] and text{}.')
    if len(d['frames'])>200 or len(d['text'])>100:raise ValidationError('Too many template layers or text boxes.')
    for k in ('width','height'):
        n=d.get(k)
        if isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n) or not 100<=n<=8192:raise ValidationError('Template dimensions must be 100–8,192 pixels.')
    if not all(k in d['text'] for k in ('title','type')):raise ValidationError('Templates need title and type text boxes.')
    for p in [d.get('onload'),*(d.get('manaSymbols') or [])]:
        if p and (not re.fullmatch(r'/js/(?:frames|manaSymbols)/[A-Za-z0-9_./-]+\.js',str(p)) or '..' in p.split('/')):raise ValidationError('Template scripts must be paths in the pinned CardConjurer runtime.')
    def walk(v):
        if isinstance(v,float) and not math.isfinite(v):raise ValidationError('Template numbers must be finite.')
        if isinstance(v,dict):
            for k,x in v.items():
                if k in {'__proto__','constructor','prototype'}:raise ValidationError('Unsupported template property.')
                if k in {'src','artSource','setSymbolSource','watermarkSource'} and isinstance(x,str) and x.lower().startswith(('javascript:','file:','blob:','data:text/')):raise ValidationError('Templates may contain images, not executable or local-file URLs.')
                walk(x)
        elif isinstance(v,list):
            for x in v:walk(x)
    walk(d)
    return d
