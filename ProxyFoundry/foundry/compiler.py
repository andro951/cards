"""Adapter over unchanged v58 templates. Overrides are opt-in, never automatic guesses."""
from __future__ import annotations
import copy,math,re
from .domain import ValidationError,ORDINARY_GROUPS,GROUP_LABELS,type_group,crop_metrics,render_key,RARITIES,GENERATION_VERSION,PIPELINE_VERSION,stable_hash
from .legacy import compiler as native,ingest
from .images import data_uri
from .credits import resolve_credit

# Sampled from the supplied real MTG red pinline reference image.
# Keep the preserved vendor compiler unchanged; override only the palette used
# by Bulk Proxy Forge's generated dual/multicolor gradients.
PINLINE_RED_HEX='e43c24'
native.DUAL_EASE_SOLID_HEX['R']=PINLINE_RED_HEX
native.DUAL_PALETTE['R']=(PINLINE_RED_HEX,native.DUAL_PALETTE['R'][1])
BUILTINS=[
 {'id':'auto','name':'Card Tools · automatic','description':'Preserves every approved v58 type-specific recipe.','legendary':True,'groups':'all'},
 {'id':'normal','name':'Classic card','description':'Standard card frame, with a crown for legendary cards.','legendary':True,'groups':'ordinary'},
 {'id':'land','name':'Full-art land','description':'Existing nonlegendary land frame. No compatible crown.','legendary':False,'groups':'ordinary'},
 {'id':'legend-land','name':'Crowned full art','description':'Existing legendary-land frame; crown removed for nonlegendary cards.','legendary':True,'groups':'ordinary'}]
SINGLE_SURFACE={'adventure','split','flip','room','prepare'}
NEEDS_CUSTOM={'split','adventure','room','meld','art-series','planar','scheme','vanguard','token','emblem','battle','case','special-land','dungeon','conspiracy'}

# Built-in cache versions are intentionally scoped. For Automatic, bump only the
# affected structural group (for example AUTO_TEMPLATE_VERSIONS['station']=2).
# Version 1 preserves the historical render key, so adding this system does not
# itself invalidate existing finished cards.
AUTO_TEMPLATE_VERSIONS={group:1 for group in GROUP_LABELS}
# Saga rendering uses a persistent native overlay canvas. Version 2 refreshes
# that canvas for each loaded Saga instead of reusing the previous Saga's
# chapter shields/dividers. Scope invalidation to Saga cards only.
AUTO_TEMPLATE_VERSIONS.update({'saga':7,'saga-creature':5,'class':3,'transform-front':5,'transform-back':5})
BUILTIN_TEMPLATE_VERSIONS={'normal':1,'land':1,'legend-land':1}

# The visible M15 type bar centers about six pixels above CardConjurer's
# type-text box center. Keep the symbol centered on the artwork, not the text box.
M15_SET_SYMBOL_VERTICAL_CENTER=0.59142

# Pixel corrections measured from native CardConjurer renders using a 115 px
# square set symbol. Negative values move the symbol upward. These are scoped
# by native recipe so ordinary M15/basic frames keep their already-correct
# placement while the affected land families are centered in their visible bars.
SET_SYMBOL_RECIPE_Y_OFFSET_PX={
    'land_colorless':-5,
    'land_full_single':-5,
    'land_full_dual':-5,
    'land_full_tri':-5,
    'land_five_color':-5,
    'land_full_legendary':-7,
    'land_full_dual_legendary':-7,
    'land_full_tri_legendary':-7,
    'land_five_color_legendary':-7,
    'original_dual_land_textless':-3,
}

def _js_round_positive(value):
    return math.floor(value+0.5)

def _standard_visible_type_bar(data,bounds):
    """Recognize the shared ordinary type-bar geometry, independent of version."""
    box=(data.get('text') or {}).get('type')
    if not isinstance(box,dict):return False
    try:
        return (
            float(box.get('rotation') or 0)%360==0
            and abs(float(box.get('y') or 0)-.5664)<=.001
            and abs(float(box.get('height') or 0)-.0543)<=.001
            and abs(float(bounds.get('x') or 0)-.9213)<=.001
            and abs(float(bounds.get('width') or 0)-.12)<=.001
            and abs(float(bounds.get('height') or 0)-.041)<=.001
        )
    except (TypeError,ValueError):return False


def fit_set_symbol_to_bounds(data,symbol,recipe=None):
    """Fit every generated frame's set symbol like CardConjurer resetSetSymbol().

    This deliberately has no CardConjurer version-name gate. Any generated frame
    that exposes setSymbolBounds gets the same alpha-trimmed asset, aspect-safe
    fit, percentage rounding, and anchor placement. Frames with the shared
    ordinary visible type bar also use the measured visible-bar vertical center;
    frames with different geometry retain their own anchor.
    """
    if not symbol:return
    bounds=data.get('setSymbolBounds')
    if not isinstance(bounds,dict):return
    try:
        card_w=float(data.get('width') or 0);card_h=float(data.get('height') or 0)
        symbol_w=float(symbol.get('width') or 0);symbol_h=float(symbol.get('height') or 0)
        bounds_x=float(bounds.get('x') or 0);bounds_y=float(bounds.get('y') or 0)
        bounds_width=float(bounds.get('width') or 0);bounds_height=float(bounds.get('height') or 0)
        bounds_w=_js_round_positive(bounds_width*card_w)
        bounds_h=_js_round_positive(bounds_height*card_h)
    except (TypeError,ValueError,ZeroDivisionError):return
    values=(card_w,card_h,symbol_w,symbol_h,bounds_w,bounds_h,bounds_x,bounds_y)
    if min(card_w,card_h,symbol_w,symbol_h,bounds_w,bounds_h)<=0 or not all(math.isfinite(x) for x in values):return

    if _standard_visible_type_bar(data,bounds):
        bounds_y=M15_SET_SYMBOL_VERTICAL_CENTER
        bounds['y']=bounds_y
        bounds['vertical']='center'

    anchor_x=_js_round_positive(bounds_x*card_w)
    anchor_y=_js_round_positive(bounds_y*card_h)

    # Mirrors creator-23.js resetSetSymbol(): fit by the limiting dimension,
    # round the percentage to one decimal place, then anchor the rendered image.
    if symbol_w/symbol_h > bounds_w/bounds_h:
        percent=bounds_w/symbol_w*100
    else:
        percent=bounds_h/symbol_h*100
    percent=math.floor(percent*10+0.5)/10
    zoom=percent/100
    if zoom<=0:return
    data['setSymbolZoom']=zoom

    rendered_w=symbol_w*zoom;rendered_h=symbol_h*zoom
    horizontal=str(bounds.get('horizontal') or 'center').lower()
    vertical=str(bounds.get('vertical') or 'center').lower()
    x=anchor_x
    if horizontal=='center':x-=rendered_w/2
    elif horizontal=='right':x-=rendered_w
    y=anchor_y
    if vertical=='center':y-=rendered_h/2
    elif vertical=='bottom':y-=rendered_h
    y+=SET_SYMBOL_RECIPE_Y_OFFSET_PX.get(str(recipe or ''),0)
    x=_js_round_positive(x);y=_js_round_positive(y)
    data['setSymbolX']=x/card_w;data['setSymbolY']=y/card_h

    # Preserve the existing 1%-of-card gap between type text and a right-anchored
    # set symbol. Nonstandard/rotated type boxes keep their native geometry.
    box=(data.get('text') or {}).get('type')
    if horizontal=='right' and isinstance(box,dict) and float(box.get('rotation') or 0)%360==0:
        try:box_x=float(box.get('x') or 0)
        except (TypeError,ValueError):return
        box['width']=max(0,data['setSymbolX']-.01-box_x)

# Compatibility name for older tests/importers; behavior is now frame-agnostic.
align_m15_set_symbol_vertical=fit_set_symbol_to_bounds

# Full-art non-land cards use an inset card opening, not the land/full-canvas
# center-crop geometry. The treatment is intentionally pixel-defined so the
# result is stable across frame families: 80 px in from the top/left/right,
# width-fit the source art, and top-align it. Any excess height falls below the
# card and is naturally clipped by the canvas/frame.
FULL_ART_NONLAND_INSET_PX=80
FULL_ART_NONLAND_BOUNDS={
    'x':FULL_ART_NONLAND_INSET_PX/native.CARD_WIDTH,
    'y':FULL_ART_NONLAND_INSET_PX/native.CARD_HEIGHT,
    'width':(native.CARD_WIDTH-2*FULL_ART_NONLAND_INSET_PX)/native.CARD_WIDTH,
    'height':(native.CARD_HEIGHT-2*FULL_ART_NONLAND_INSET_PX)/native.CARD_HEIGHT,
}

def _is_custom_art_origin(art_origin):
    return str(art_origin or '')!='Scryfall selected printing'

def _station_frame_component(frame):
    return (
        isinstance(frame,dict)
        and any(isinstance(mask,dict) and mask.get('name')=='Frame' for mask in frame.get('masks',[]))
        and str(frame.get('src','')).startswith('/img/frames/m15/regular/m15Frame')
    )

def apply_station_underframe_policy(data,sem,art_origin):
    """Expose full/custom art through Station transparency; fill Scryfall color gaps.

    Custom Station art is full-bleed, so the ordinary M15 Frame component must
    not sit behind the transparent portion of the Station overlay. Colorless
    Scryfall Stations intentionally leave that portion transparent too. Colored
    Scryfall Stations use the corresponding normal W/U/B/R/G frame component;
    two or more colors use the normal multicolor frame. Other masked pieces are
    left alone because the Station overlay owns the visible Station treatment.
    """
    frames=data.get('frames',[])
    components=[frame for frame in frames if _station_frame_component(frame)]
    if not components:return False
    colors=[]
    for color in sem.get('colors',[]) or []:
        if color in 'WUBRG' and color not in colors:colors.append(color)
    if _is_custom_art_origin(art_origin) or not colors:
        data['frames']=[frame for frame in frames if not _station_frame_component(frame)]
        return True
    code=colors[0] if len(colors)==1 else 'M'
    for frame in components:
        frame['src']=f'/img/frames/m15/regular/m15Frame{code}.png'
        frame['name']=native.COLOR_NAMES[code]+' Frame'
    return True

def apply_colored_artifact_frame_treatment(data,sem):
    """Use muted color accents while retaining each artifact's structural shell."""
    types=set(sem.get('types',[]))
    if 'Artifact' not in types:return False
    colors=[]
    for color in sem.get('colors',[]) or []:
        if color in 'WUBRG' and color not in colors:colors.append(color)
    if not colors and 'Land' in types:
        for color in sem.get('land_colors',[]) or []:
            if color in 'WUBRG' and color not in colors:colors.append(color)
    if not colors:return False
    code=colors[0] if len(colors)==1 else 'M'

    # Card Tools already owns the artifact/Vehicle pinline behavior: mono cards
    # use their real color, exactly two colors use the existing blended gradient,
    # and 3+ colors use multicolor/gold. Do not flatten that treatment here.
    native.set_title_type_frame_color(data,code)

    # Vehicle and Station/Spacecraft rules areas are structural parts of those
    # dedicated frames. Ordinary colored artifacts instead use the same muted
    # W/U/B/R/G or multicolor/gold texture in the rules box as their label bars.
    if {'Vehicle','Spacecraft'} & set(sem.get('subtypes',[])):
        return True
    cname=native.COLOR_NAMES.get(code,code)
    for frame in data.get('frames',[]):
        if not isinstance(frame,dict):continue
        masks=frame.get('masks',[])
        if not any(isinstance(mask,dict) and mask.get('name')=='Rules' for mask in masks):
            continue
        src=str(frame.get('src',''))
        if '/img/frames/m15/nyx/' in src:
            frame['src']=f'/img/frames/m15/nyx/m15Frame{code}Nyx.png'
        else:
            frame['src']=f'/img/frames/m15/regular/m15Frame{code}.png'
        if 'name' in frame:frame['name']=f'{cname} Rules'
    return True

MIRACLE_FRAME_BOUNDS={'x':0.04,'y':0.0286,'width':0.92,'height':0.5324}

def is_miracle_card(sem):
    """Recognize Miracle from Scryfall keywords, with a strict Oracle fallback."""
    keywords=sem.get('keywords',[]) or []
    if any(str(keyword).strip().lower()=='miracle' for keyword in keywords):
        return True
    return bool(re.search(r'(?im)^\\s*Miracle\\s+\\{',str(sem.get('oracle_text') or '')))

def apply_miracle_frame(data,sem):
    """Overlay CardConjurer's genuine M15 Miracle frame on automatic cards."""
    if not is_miracle_card(sem):return False
    if any(isinstance(frame,dict) and 'Miracle Frame' in str(frame.get('name','')) for frame in data.get('frames',[])):
        return False
    colors=[]
    for color in sem.get('colors',[]) or []:
        if color in 'WUBRG' and color not in colors:colors.append(color)
    types=set(sem.get('types',[]))
    code=('A' if 'Artifact' in types else
          'L' if 'Land' in types else
          colors[0] if len(colors)==1 else 'M')
    name=native.COLOR_NAMES.get(code,code)+' Miracle Frame'
    # CardConjurer draws frames in reverse order. Index 0 is therefore drawn
    # last/on top, matching the Miracle pack's intended upper-frame overlay.
    data.setdefault('frames',[]).insert(0,{
        'name':name,
        'src':f'/img/frames/m15/miracle/{code.lower()}.png',
        'masks':[],
        'bounds':copy.deepcopy(MIRACLE_FRAME_BOUNDS),
    })
    return True

def full_art_nonland_placement(art):
    """Cover the 80px-inset full-art area and center only overflowing axes."""
    iw=float(art.get('width') or 0)
    ih=float(art.get('height') or 0)
    if iw<=0 or ih<=0:raise ValidationError('Artwork dimensions are missing.')
    inset=FULL_ART_NONLAND_INSET_PX
    inner_w=native.CARD_WIDTH-2*inset
    inner_h=native.CARD_HEIGHT-2*inset
    zoom=max(inner_w/iw,inner_h/ih)
    scaled_w=iw*zoom
    scaled_h=ih*zoom
    x=inset if scaled_w<=inner_w+1e-9 else (native.CARD_WIDTH-scaled_w)/2
    y=inset if scaled_h<=inner_h+1e-9 else (native.CARD_HEIGHT-scaled_h)/2
    return {
        'artBounds':copy.deepcopy(FULL_ART_NONLAND_BOUNDS),
        'artX':x/native.CARD_WIDTH,
        'artY':y/native.CARD_HEIGHT,
        'artZoom':zoom,
        'artRotate':'0',
    }

def apply_custom_full_art_placement(data,art,recipe,group,art_origin,autofit):
    """Apply the reusable full-art non-land treatment to custom art."""
    if not _is_custom_art_origin(art_origin):return False
    if group!='station' and recipe not in {'colorless_creature','colorless_creature_legendary'}:return False
    data['artBounds']=copy.deepcopy(FULL_ART_NONLAND_BOUNDS)
    if autofit:
        for key,value in full_art_nonland_placement(art).items():data[key]=value
    return True

def intentional_art_window_crop(group,choice,art,options,settings):
    """True when native structural fitting intentionally consumes a landscape art crop.

    Planeswalker and Station source art is commonly the illustration window from
    Scryfall rather than a portrait/full-bleed image. Card Tools deliberately
    places that landscape source into these structural frames, so comparing its
    aspect ratio to the full structural art well produces a false crop warning.
    Manual placement, custom templates/raw cards and disabled autofit must still
    receive the ordinary crop warning.
    """
    fit=options.get('fit') or {}
    return (
        choice=='auto'
        and group in {'planeswalker','station'}
        and int(art.get('width') or 0)>int(art.get('height') or 0)>0
        and not settings.get('disableAutofit',False)
        and not options.get('rawCard')
        and not any(k in fit for k in ('artX','artY','artZoom','artRotate'))
    )


_SCRYFALL_INLINE_ITALIC_RE=re.compile(r'(?<!\*)\*([^*\n]+?)\*(?!\*)')

def normalize_scryfall_inline_italics(value):
    """Translate Scryfall's *inline italics* to CardConjurer's text markup."""
    return _SCRYFALL_INLINE_ITALIC_RE.sub(lambda match:'{i}'+match.group(1)+'{/i}',str(value or ''))

_QUOTED_ORACLE_RE=re.compile(r'“[^”]*”|"[^"]*"')
_ANY_COLOR_OUTPUT_RE=re.compile(r'\b(?:any(?: one)? color|any combination of colors|any type)\b',re.I)

def land_frame_colors(types,face,card,oracle_text):
    """Infer land frame colors from the land's own mana production.

    Scryfall produced_mana is intentionally only a last fallback. It can include
    colors available through conditional/granted effects (The World Tree is the
    canonical example), which should not turn an otherwise green land gold.
    """
    if 'Land' not in types.get('types',[]):return []

    result=[]
    def add(color):
        if isinstance(color,str) and color in 'WUBRG' and color not in result:result.append(color)

    # Printed basic land types are authoritative frame identity.
    for subtype in types.get('subtypes',[]):
        add(getattr(ingest,'BASIC_LAND_COLORS',{}).get(subtype))

    # Ignore quoted abilities granted to lands/other permanents, then inspect
    # activated mana abilities only. Colored symbols before "Add" are costs and
    # therefore never contribute to the frame color.
    clean=_QUOTED_ORACLE_RE.sub('',str(oracle_text or ''))
    has_direct_mana_ability=False
    for line in clean.splitlines():
        for match in re.finditer(r'\bAdd\b([^.;\n]*)',line,re.I):
            if ':' not in line[:match.start()]:continue
            has_direct_mana_ability=True
            clause=match.group(1)
            for token in re.findall(r'\{([^{}]+)\}',clause):
                for part in token.upper().split('/'):
                    add(part)
            if _ANY_COLOR_OUTPUT_RE.search(clause):
                for color in 'WUBRG':add(color)

    # Fetch lands are the deliberate exception: their visual identity follows
    # the basic land types they search for even though they do not make that mana.
    for subtype,color in getattr(ingest,'BASIC_LAND_COLORS',{}).items():
        if re.search(rf'\b{re.escape(subtype)}\b',clean):add(color)

    # Once the printed rules/type line tells us anything useful, do not widen it
    # with produced_mana. This is what keeps The World Tree green and Nykthos
    # colorless rather than treating conditional mana access as intrinsic color.
    if result or has_direct_mana_ability:return result

    produced=ingest.face_value(face,card,'produced_mana',[])
    if isinstance(produced,list):
        for color in produced:add(color)
    return result


def semantic(sf,face,index=0):
    get=lambda k,default='':ingest.face_value(face,sf,k,default)
    types=ingest.split_type_line(get('type_line'))
    d={**types,'name':get('name'),'mana_cost':get('mana_cost'),'oracle_text':get('oracle_text'),'colors':get('colors',[]),'keywords':get('keywords',[]),'rarity':sf.get('rarity','common'),'flavor_text':normalize_scryfall_inline_italics(get('flavor_text'))}
    for k in ('power','toughness','loyalty','defense'):
        v=get(k,None)
        if v is not None:d[k]=str(v)
    lc=land_frame_colors(types,face,sf,d['oracle_text'])
    # Enchantment lands such as Valgavoth's Lair are still land-frame cards.
    # Its printed ability says "chosen color", so the direct Add-clause parser
    # has no literal mana symbol to collect; use Scryfall produced_mana only for
    # this previously unsupported type combination.
    if not lc and 'Land' in types.get('types',[]) and 'Enchantment' in types.get('types',[]):
        produced=get('produced_mana',[])
        if isinstance(produced,list):
            lc=[color for color in 'WUBRG' if color in produced]
    if lc:d['land_colors']=lc
    if len(sf.get('card_faces',[]))>1:d.update(parent_name=sf['name'],face_index=index,scryfall_layout=sf.get('layout',''))
    if sf.get('layout')=='prepare':
        faces=sf.get('card_faces',[])
        if len(faces)!=2:raise ValidationError('Prepare cards need the host and prepared spell.')
        d['prepared_spell']=semantic({**sf,'layout':'normal','card_faces':[]},faces[1]);d['scryfall_layout']='prepare'
    if sf.get('layout')=='flip':
        faces=sf.get('card_faces',[])
        if len(faces)!=2:raise ValidationError('Flip cards need the upright and rotated lower face.')
        d['flip_face']=ingest.build_nested_face_semantic(sf,faces[1],faces[1],{})
        d['scryfall_layout']='flip'
    return d


def choose_builtin(d,choice):
    if choice=='auto':return d
    if type_group(d) not in ORDINARY_GROUPS:raise ValidationError('Use the automatic recipe or a compatible structural template.')
    if choice=='land' and d.get('legendary'):raise ValidationError('Full-art land has no compatible legendary crown. Choose Classic or Crowned full art.')
    d=copy.deepcopy(d)
    if choice=='normal':
        pt='Creature' in d['types'] or bool({'Vehicle','Spacecraft'} & set(d['subtypes']))
        d['layout']=('creature_legendary' if d['legendary'] else 'creature') if pt else ('card_legendary' if d['legendary'] else 'card_noncreature')
        if 'Land' not in d['types']:
            d['layout']=native.infer_layout(d if 'layout' not in d else {k:v for k,v in d.items() if k!='layout'},native.get_type_info(d))
        if not d.get('colors') and 'Artifact' not in d['types']:
            d['frame_color']='M';d['_neutral_classic']=True
    elif choice in {'land','legend-land'}:
        d['layout']='land_full_single' if choice=='land' else 'land_full_legendary'
        if 'Land' not in d['types']:d['land_colors']=d.get('colors',[])
    else:raise ValidationError('Unknown built-in template.')
    return d



_TRANSFORM_FRONT_MASKS={
    'Pinline':'/img/frames/m15/transform/regular/maskPinlineFront.png',
    'Title':'/img/frames/m15/transform/regular/maskTitle.png',
    'Type':'/img/frames/m15/regular/m15MaskType.png',
    'Rules':'/img/frames/m15/transform/regular/maskRulesFront.png',
    'Frame':'/img/frames/m15/transform/regular/maskFrameFront.png',
    'Border':'/img/frames/m15/transform/regular/maskBorderFront.png',
}
_TRANSFORM_BACK_MASKS={
    'Pinline':'/img/frames/m15/transform/regular/new/maskPinlineBack.png',
    'Title':'/img/frames/m15/transform/regular/new/maskTitle.png',
    'Type':'/img/frames/m15/regular/m15MaskType.png',
    'Rules':'/img/frames/m15/regular/m15MaskRules.png',
    'Frame':'/img/frames/m15/transform/regular/new/maskFrameBack.png',
    'Border':'/img/frames/m15/regular/m15MaskBorder.png',
}
_TRANSFORM_ICON={
    'name':'Transform Icon',
    'src':'/img/frames/m15/transform/icons/default.png',
    'masks':[],
    'bounds':{'x':0.0594,'y':0.0505,'width':0.0734,'height':0.0524},
}

def _transform_color_code(sem):
    colors=[c for c in sem.get('colors',[]) if c in 'WUBRG']
    if len(colors)>1:return 'M'
    if colors:return colors[0]
    return 'L'


def _transform_frame_codes(sem):
    """Pick the transform shell from the face's standalone card identity."""
    types=set(sem.get('types',[]))
    color=_transform_color_code(sem)
    if 'Land' in types:
        return 'L','L'
    if 'Artifact' in types:
        return 'A',(color if sem.get('colors') else 'A')
    return color,color


_TRANSFORM_EFFECT_ICONS={
    'compasslanddfc':('Compass','/img/frames/m15/transform/icons/compass.svg','Land','/img/frames/m15/transform/icons/land.svg'),
    'sunmoondfc':('Sun','/img/frames/m15/transform/icons/sun.svg','Crescent Moon','/img/frames/m15/transform/icons/moon.svg'),
    'mooneldrazidfc':('Crescent Moon','/img/frames/m15/transform/icons/moon.svg','Emrakul','/img/frames/m15/transform/icons/emrakul.svg'),
    'originpwdfc':('Planeswalker Ember','/img/frames/m15/transform/icons/spark.svg','Planeswalker Spark','/img/frames/m15/transform/icons/planeswalker.svg'),
    'fandfc':('Closed Fan','/img/frames/m15/transform/icons/fanClosed.svg','Open Fan','/img/frames/m15/transform/icons/fanOpen.svg'),
}


def _transform_icon_for(card,side):
    effects=set(card.get('frame_effects') or [])
    for effect,(front_name,front_src,back_name,back_src) in _TRANSFORM_EFFECT_ICONS.items():
        if effect in effects:
            name,src=(front_name,front_src) if side=='front' else (back_name,back_src)
            return {'name':name,'src':src,'masks':[],'bounds':copy.deepcopy(_TRANSFORM_ICON['bounds'])}
    # Preserve the existing fallback for transform families whose Scryfall frame
    # effect is absent/unknown. Do not invent a reverse icon in that case.
    return copy.deepcopy(_TRANSFORM_ICON) if side=='front' else None


def _transform_classic_semantic(sem):
    """Build classic M15 text geometry while keeping the face's own semantics."""
    d=copy.deepcopy(sem)
    for key in ('parent_name','face_index','scryfall_layout'):
        d.pop(key,None)
    card_types=set(d.get('types',[]));subtypes=set(d.get('subtypes',[]))
    if not card_types or not card_types <= {'Creature','Artifact','Enchantment','Land'}:
        raise ValidationError('This transform face needs a compatible custom template; its card type is not supported by the built-in M15 transform frame.')
    if 'Land' in card_types and 'Creature' in card_types:
        raise ValidationError('This transform face needs a compatible custom template; simultaneous land and creature treatment is not supported by the built-in M15 transform frame.')
    if {'Saga','Class','Case','Room','Vehicle','Spacecraft'} & subtypes:
        raise ValidationError('This transform face needs a compatible custom template; its structural subtype is not supported by the built-in M15 transform frame.')

    # Resolve the face as itself, but explicitly choose classic M15 geometry so
    # Enchantments do not become Nyx and Lands do not become full-art showcase
    # frames before the transform shell is applied.
    pt='Creature' in card_types
    d['layout']=('creature_legendary' if d.get('legendary') else 'creature') if pt else ('card_legendary' if d.get('legendary') else 'card_noncreature')
    if 'Land' in card_types:
        # Native normal M15 needs a seed color before the transform shell replaces
        # only structural body pieces with CardConjurer's real L land frame.
        land_colors=[c for c in d.get('land_colors',[]) if c in 'WUBRG']
        d['frame_color']=land_colors[0] if len(land_colors)==1 else 'M'
    elif not d.get('colors') and 'Artifact' not in card_types:
        d['frame_color']='M'
    return d


def _convert_frame_masks(frame,mapping):
    for mask in frame.get('masks',[]) if isinstance(frame.get('masks'),list) else []:
        if isinstance(mask,dict) and mask.get('name') in mapping:
            mask['src']=mapping[mask['name']]


def _apply_transform_frame(data,side,sem,card):
    """Convert classic M15 geometry to CardConjurer's genuine transform assets."""
    if side not in {'front','back'}:raise ValidationError('Invalid transform side.')
    mapping=_TRANSFORM_FRONT_MASKS if side=='front' else _TRANSFORM_BACK_MASKS
    body_code,crown_code=_transform_frame_codes(sem)
    allowed=set('WUBRGMAL') if side=='front' else set('WUBRGMALV')
    if body_code not in allowed:
        raise ValidationError('This transform face resolves to a CardConjurer frame color that the built-in transform pack does not provide.')
    converted=0
    for frame in data.get('frames',[]):
        if not isinstance(frame,dict):continue
        # Convert mask geometry for every layer, including generated dual-color
        # gradient pinlines whose src is a data URI rather than an M15 PNG.
        _convert_frame_masks(frame,mapping)
        src=str(frame.get('src') or '')
        m=re.fullmatch(r'/img/frames/m15/regular/m15Frame([WUBRGMALCV])\.png',src)
        if m:
            mask_names={
                mask.get('name') for mask in frame.get('masks',[])
                if isinstance(mask,dict)
            }
            # Structural shell pieces stay Artifact/Land/etc. Accent pieces keep
            # the semantic color already chosen by the ordinary M15 compiler.
            layer_code=m.group(1) if mask_names & {'Pinline','Title','Type','Rules'} else body_code
            frame['src']=(f'/img/frames/m15/transform/regular/front{layer_code}.png' if side=='front'
                          else f'/img/frames/m15/transform/regular/new/back{layer_code}.png')
            converted+=1
            continue
        pt=re.fullmatch(r'/img/frames/m15/regular/m15PT([WUBRGMACV])\.png',src)
        if pt and side=='back':
            pt_code=body_code if body_code in set('WUBRGMAV') else pt.group(1)
            if pt_code not in set('WUBRGMAV'):
                raise ValidationError('This transform back uses an unsupported power/toughness frame color.')
            frame['src']=f'/img/frames/m15/transform/regular/pt{pt_code}.png'
            continue
        crown=re.fullmatch(r'/img/frames/m15/crowns/m15Crown([WUBRGMALC])(?:(Floating)(?:Alt)?)?\.png',src)
        if crown:
            _,floating=crown.groups()
            if crown_code not in set('WUBRGMAL'):
                raise ValidationError('This legendary transform face uses an unsupported crown color.')
            if floating:
                frame['src']=f'/img/frames/m15/transform/crowns/floating/{crown_code.lower()}.png'
            else:
                frame['src']=(f'/img/frames/m15/transform/crowns/regular/{crown_code.lower()}.png' if side=='front'
                              else f'/img/frames/m15/transform/crowns/regular/new/{crown_code.lower()}.png')
            continue
        if frame.get('name')=='Legend Crown Lower Cutout':
            frame['bounds']={'x':0.0767,'y':0.1096,'width':0.8467,'height':0.0143}
    if not converted:
        raise ValidationError('This transform face does not resolve to CardConjurer’s supported M15 transform frame.')

    data['version']='m15TransformFront'
    text=data.setdefault('text',{})
    title=text.get('title')
    if isinstance(title,dict):
        title['x']=0.16 if side=='front' else 0.0854
        title['width']=0.7547
        if side=='back':title['color']='white'
    icon=_transform_icon_for(card,side)
    if icon:data['frames'].insert(0,icon)
    if side=='front':
        text.setdefault('reminder',{'name':'Reverse PT','text':'','x':0.086,'y':0.842,'width':0.838,'height':0.0362,
                                    'size':0.0291,'oneLine':True,'color':'#666','align':'right','font':'belerenbsc'})
    else:
        for key in ('type','pt'):
            if isinstance(text.get(key),dict):text[key]['color']='white'
    return data



_SAGA_PINLINE_MASKS={
    'saga':'/img/frames/saga/sagaMaskPinline.png',
    'saga-creature':'/img/frames/saga/creature/masks/sagaMaskPinline.png',
}
_SAGA_TASSEL_MASKS={
    'saga':(
        '/img/frames/saga/sagaMaskBanner.png',
        '/img/frames/saga/sagaMaskBannerRight.png',
    ),
    'saga-creature':(
        '/img/frames/saga/creature/masks/sagaMaskBanner.png',
        '/img/frames/saga/creature/masks/sagaMaskBannerRight.png',
    ),
}


def _saga_color_frame_src(group,code):
    if group=='saga':return f'/img/frames/saga/regular/sagaFrame{code}.png'
    if group=='saga-creature':return f'/img/frames/saga/creature/{code.lower()}.png'
    raise ValidationError('Unsupported Saga frame group.')


def apply_dual_saga_gradient(data,sem,group):
    """Give two-color Sagas an eased pinline and one color per left tassel."""
    if group not in _SAGA_PINLINE_MASKS:return False
    colors=[]
    for color in sem.get('colors',[]) or []:
        if color in 'WUBRG' and color not in colors:colors.append(color)
    if len(colors)!=2:return False
    first,second=native.canonical_dual_color_order(colors)
    frames=data.setdefault('frames',[])
    if any(
        isinstance(frame,dict)
        and any(isinstance(mask,dict) and mask.get('name') in {'Saga Tassel 1','Saga Tassel 2'} for mask in frame.get('masks',[]))
        for frame in frames
    ):return False
    prefix='/img/frames/saga/regular/' if group=='saga' else '/img/frames/saga/creature/'
    target=next((i for i,frame in enumerate(frames)
                 if isinstance(frame,dict) and str(frame.get('src','')).startswith(prefix)
                 and not frame.get('masks')),None)
    if target is None:
        raise ValidationError('Two-color Saga did not contain its complete Saga frame layer.')
    tassel1,tassel2=_SAGA_TASSEL_MASKS[group]
    # CardConjurer draws card.frames in reverse order. Banner is the broad/base
    # banner mask; BannerRight is the second/right piece. Put the right overlay
    # earlier in the array so it is drawn after the broad first-color banner.
    overlays=[
        {
            'name':f"{native.COLOR_NAMES[first]}/{native.COLOR_NAMES[second]} Gradient Saga Pinline",
            'src':native.dual_gradient_fill_src(first,second),
            'masks':[{'src':_SAGA_PINLINE_MASKS[group],'name':'Pinline'}],
        },
        {
            'name':f"{native.COLOR_NAMES[second]} Saga Tassel 2",
            'src':_saga_color_frame_src(group,second),
            'masks':[{'src':tassel2,'name':'Saga Tassel 2'}],
        },
        {
            'name':f"{native.COLOR_NAMES[first]} Saga Tassel 1",
            'src':_saga_color_frame_src(group,first),
            'masks':[{'src':tassel1,'name':'Saga Tassel 1'}],
        },
    ]
    frames[target:target]=overlays
    return True

def build_transform_data(sem,group,card,artist,autofit,flags):
    """Treat each DFC face normally, then replace only its shell with transform."""
    d0=_transform_classic_semantic(sem)
    try:
        data=native.build_one(copy.deepcopy(d0),{'artist':artist},autofit,flagged_sagas=flags)['data']
    except native.BuildError as exc:
        raise ValidationError(str(exc)) from exc
    # Color treatment is semantic, not single-sided-card-specific. Apply it
    # before replacing the structural shell so DFCs preserve the same accents.
    apply_colored_artifact_frame_treatment(data,sem)
    side='front' if group=='transform-front' else 'back'
    _apply_transform_frame(data,side,sem,card)
    return d0,data,'m15_transform_'+side


_CLASS_FRAME_NAMES={'w':'White','u':'Blue','b':'Black','r':'Red','g':'Green','m':'Multicolored','a':'Artifact','l':'Land'}


def _class_parts(oracle_text):
    lines=str(oracle_text or '').splitlines()
    initial=[];levels=[];current=None
    marker=re.compile(r'^(.*?):\s*Level\s+(\d+)\s*$',re.I)
    for raw in lines:
        line=raw.strip()
        if not line:continue
        found=marker.match(line)
        if found:
            if current:levels.append(current)
            current={'cost':found.group(1).strip()+':','name':'Level '+found.group(2),'text':[]}
        elif current:
            current['text'].append(line)
        else:
            initial.append(line)
    if current:levels.append(current)
    if not levels or len(levels)>3:
        raise ValidationError('This Class card does not resolve to CardConjurer’s supported 2–4 level Class frame.')
    # Scryfall Oracle text normally omits the printed Class reminder, while
    # CardConjurer's native Class frame includes it. Preserve an explicit
    # reminder if one was supplied; otherwise restore the standard reminder.
    reminder='(Gain the next level as a sorcery to add its ability.)'
    if initial and initial[0].startswith('(') and initial[0].endswith(')'):
        reminder=initial.pop(0)
    base_text='{i}'+reminder+'{/i}{lns}{bar}{lns}'+'\n'.join(initial)
    return base_text,[{'cost':x['cost'],'name':x['name'],'text':'\n'.join(x['text'])} for x in levels]


def build_class_data(sem,artist,autofit,flags):
    """Build the pinned CardConjurer Class layout with its complete frame image."""
    if sem.get('legendary'):
        raise ValidationError('Legendary Class cards need a compatible custom template; CardConjurer’s Class pack has no legendary crown treatment.')
    base=copy.deepcopy(sem)
    base['subtypes']=[x for x in base.get('subtypes',[]) if x!='Class']
    try:
        data=native.build_one(copy.deepcopy(base),{'artist':artist},False,flagged_sagas=flags)['data']
    except native.BuildError as exc:
        raise ValidationError(str(exc)) from exc

    colors=[c for c in sem.get('colors',[]) if c in 'WUBRG']
    code=('a' if 'Artifact' in sem.get('types',[]) else
          'l' if 'Land' in sem.get('types',[]) else
          'm' if len(colors)>1 else colors[0].lower() if colors else 'm')
    base_text,levels=_class_parts(sem.get('oracle_text',''))
    level_count=1+len(levels)
    heights={2:[.31,.20,0,0],3:[.2096,.2091,.2091,0],4:[.15,.15,.15,.10]}[level_count]

    data['version']='class';data['onload']='/js/frames/versionClass.js'
    data['frames']=[{'name':_CLASS_FRAME_NAMES[code]+' Frame','src':f'/img/frames/class/{code}.png','masks':[]}]
    data['artBounds']={'x':0.0753,'y':0.1124,'width':0.4247,'height':0.7253}
    data['setSymbolBounds']={'x':0.9227,'y':0.8739,'width':0.12,'height':0.0381,'vertical':'center','horizontal':'right'}
    data['watermarkBounds']={'x':0.5214,'y':0.4748,'width':0.38,'height':0.6767}
    data['class']={'x':0.5014,'width':0.422,'count':len(levels)}
    data['showsFlavorBar']=False
    text={
        'mana':{'name':'Mana Cost','text':sem.get('mana_cost',''),'y':0.0613,'width':0.9292,'height':71/2100,'oneLine':True,'size':71/1638,'align':'right','shadowX':-0.001,'shadowY':0.0029,'manaCost':True,'manaSpacing':0},
        'title':{'name':'Title','text':sem['name'],'x':0.0854,'y':0.0522,'width':0.8292,'height':0.0543,'oneLine':True,'font':'belerenb','size':0.0381},
        'type':{'name':'Type','text':native.get_type_info(sem)['normalized'].replace(' - ',' — '),'x':0.0854,'y':0.8481,'width':0.8292,'height':0.0543,'oneLine':True,'font':'belerenb','size':0.0324},
        'level0c':{'name':'1 - Text','text':base_text,'x':0.5093,'y':0.1129,'width':0.404,'height':heights[0],'size':0.0305},
    }
    last_y=0.1129+heights[0]+0.0481
    for i in range(1,4):
        active=i<=len(levels)
        height=heights[i] if active else 0
        y=last_y if active else 2
        info=levels[i-1] if active else {'cost':'','name':'','text':''}
        text[f'level{i}a']={'name':f'{i+1} - Cost','text':info['cost'],'x':0.5093,'y':y-0.0361 if active else 2,'width':0.3967,'height':0.0277,'size':0.0277}
        text[f'level{i}b']={'name':f'{i+1} - Name','text':info['name'],'x':0.5093,'y':y-0.0361 if active else 2,'width':0.3967,'height':0.0281,'size':0.0281,'align':'right'}
        text[f'level{i}c']={'name':f'{i+1} - Text','text':info['text'],'x':0.5093,'y':y,'width':0.404,'height':height,'size':0.0305}
        if active:last_y+=height+0.0481
    data['text']=text
    if autofit:native.auto_fit(data,sem['art_local_path'])
    return base,data,'class'


def build_enchantment_land_data(sem,artist,autofit,flags):
    """Use the ordinary land family while preserving the Enchantment Land type."""
    base=copy.deepcopy(sem)
    base['types']=[x for x in base.get('types',[]) if x!='Enchantment']
    try:
        data=native.build_one(copy.deepcopy(base),{'artist':artist},autofit,flagged_sagas=flags)['data']
    except native.BuildError as exc:
        raise ValidationError(str(exc)) from exc
    if isinstance((data.get('text') or {}).get('type'),dict):
        data['text']['type']['text']=native.get_type_info(sem)['normalized']
    recipe=native.infer_layout(base,native.get_type_info(base))
    return base,data,recipe


def custom_data(template,sem,other_faces=None):
    d=copy.deepcopy(template['data'])
    values={'title':sem['name'],'type':native.get_type_info(sem)['normalized'],'mana':sem.get('mana_cost',''),
      'rules':native.italicize_dash_labels(sem.get('oracle_text',''))+('{flavor}'+sem['flavor_text'] if sem.get('flavor_text') else ''),
      'flavor':sem.get('flavor_text',''),'pt':str(sem['power'])+'/'+str(sem['toughness']) if sem.get('power') is not None and sem.get('toughness') is not None else '',
      'loyalty':sem.get('loyalty',''),'defense':sem.get('defense','')}
    for i,line in enumerate(sem.get('oracle_text','').splitlines(),1):values['line'+str(i)]=line
    for slot,field in (template.get('mapping') or {k:k for k in values}).items():
        if slot not in d['text']:continue
        if field in values:d['text'][slot]['text']=str(values[field])
        elif field.startswith('face2.') and other_faces:
            key=field.split('.',1)[1];d['text'][slot]['text']=str(other_faces[0].get({'title':'name','mana':'mana_cost','rules':'oracle_text','type':'type_line'}.get(key,key),'') or '')
    if 'pt' in d['text'] and not values['pt']:d['text']['pt']['text']=''
    return d


class Compiler:
    def __init__(self,store):self.store=store
    def template_identity(self,group,choice):
        if choice=='auto':return 'auto:'+group,AUTO_TEMPLATE_VERSIONS.get(group,1),AUTO_TEMPLATE_VERSIONS.get(group,1)
        if choice in BUILTIN_TEMPLATE_VERSIONS:
            version=BUILTIN_TEMPLATE_VERSIONS[choice];return 'builtin:'+choice,version,version
        t=self.store.get('templates',choice)
        if not t:raise ValidationError('The selected template was deleted.')
        # Custom template data is already embedded in compiled CardConjurer data,
        # so its fingerprint is for stale-template detection; render-key salting
        # stays at baseline v1 to avoid redundant cache invalidation.
        fingerprint=stable_hash({'data':t.get('data'),'mapping':t.get('mapping',{}),'groups':t.get('groups',[]),'legendary':bool(t.get('legendary'))})
        return 'custom:'+choice,fingerprint,1
    def compile_face(self,sf,face,index,options,settings,art_id,*,art_origin='custom artwork'):
        sem=semantic(sf,face,index)
        for k in ('flavor_text','rarity','oracle_text','mana_cost','power','toughness','loyalty','defense'):
            if k in options.get('semanticOverrides',{}):sem[k]=options['semanticOverrides'][k]
        sem['flavor_text']=normalize_scryfall_inline_italics(sem.get('flavor_text'))
        for nested in ('flip_face','prepared_spell'):
            if nested in sem:
                if nested in options.get('nestedFlavorTexts',{}):
                    sem[nested]['flavor_text']=options['nestedFlavorTexts'][nested]
                sem[nested]['flavor_text']=normalize_scryfall_inline_italics(sem[nested].get('flavor_text'))
        symbols=settings.get('symbols',{})
        if any(not symbols.get(r) or not self.store.asset(symbols[r]) for r in RARITIES):raise ValidationError('Provide four rarity symbols, or generate four treatments from one symbol.')
        symbol_id=symbols.get(sem.get('rarity','common'))
        if not symbol_id:raise ValidationError('Unsupported rarity. Set a common/uncommon/rare/mythic override.')
        art=self.store.asset(art_id)
        if not art:raise ValidationError('Artwork is missing.')
        sem['art']=data_uri(self.store,art_id);sem['art_local_path']=str(self.store.asset_path(art_id));sem['set_symbol_source']=data_uri(self.store,symbol_id)
        credit=resolve_credit(sf,face,options,settings,art_origin)
        artist=credit['display']
        sem['artist']=artist
        group=type_group(face,sf,index);choice=options.get('templateOverride') or settings.get('templateRules',{}).get(group,'auto');flags=[]
        template_key,template_version,template_cache_version=self.template_identity(group,choice)
        if choice in {x['id'] for x in BUILTINS}:
            if group not in ORDINARY_GROUPS and choice!='auto':raise ValidationError('Choose automatic or a custom template for '+group+'.')
            if group in NEEDS_CUSTOM:raise ValidationError('Recognized '+group+' needs a compatible custom template; no incorrect frame will be substituted.')
            if group in {'modal-front','modal-back'}:
                pair=[x.get('name') for x in sf.get('card_faces',[])]
                if pair!=['Esika, God of the Tree','The Prismatic Bridge']:
                    raise ValidationError('This modal DFC needs a compatible custom template. The approved built-in pair is Esika / The Prismatic Bridge; its colors and reminder strip must not be reused for another card.')
            if group in {'transform-front','transform-back'}:
                d0,data,recipe=build_transform_data(sem,group,sf,artist,not settings.get('disableAutofit',False),flags)
                fit_set_symbol_to_bounds(data,self.store.asset(symbol_id),recipe)
            elif group=='class':
                d0,data,recipe=build_class_data(sem,artist,not settings.get('disableAutofit',False),flags)
                fit_set_symbol_to_bounds(data,self.store.asset(symbol_id),recipe)
            elif choice=='auto' and group in {'land','legendary-land','basic-land'} and 'Land' in sem.get('types',[]) and 'Enchantment' in sem.get('types',[]):
                d0,data,recipe=build_enchantment_land_data(sem,artist,not settings.get('disableAutofit',False),flags)
                fit_set_symbol_to_bounds(data,self.store.asset(symbol_id),recipe)
            else:
                d0=choose_builtin(sem,choice)
                # Saga is the highest-priority structural card treatment. Do not
                # let another type on the same line (notably Land on Urza's Saga)
                # win inside the preserved native recipe classifier.
                if choice=='auto' and group in {'saga','saga-creature'}:
                    d0=copy.deepcopy(d0)
                    d0['layout']='saga' if group=='saga' else 'saga_creature'
                try:
                    data=native.build_one(copy.deepcopy(d0),{'artist':artist},not settings.get('disableAutofit',False),flagged_sagas=flags)['data']
                    if group in {'standard','legendary'}:
                        apply_colored_artifact_frame_treatment(data,sem)
                        if choice=='auto':apply_miracle_frame(data,sem)
                    if choice=='legend-land' and not sem['legendary']:native.remove_crown(data)
                    if d0.get('_neutral_classic'):native.recolor_m15(data,'L')
                    recipe=native.infer_layout(d0,native.get_type_info(d0))
                    if choice=='auto' and group in {'saga','saga-creature'}:
                        apply_dual_saga_gradient(data,sem,group)
                    if choice=='auto' and group=='station':
                        apply_station_underframe_policy(data,sem,art_origin)
                    apply_custom_full_art_placement(
                        data,art,recipe,group,art_origin,not settings.get('disableAutofit',False)
                    )
                    fit_set_symbol_to_bounds(data,self.store.asset(symbol_id),recipe)
                except native.BuildError as e:raise ValidationError(str(e)) from e
        else:
            t=self.store.get('templates',choice)
            if not t:raise ValidationError('The selected template was deleted.')
            if group not in t.get('groups',[]):raise ValidationError('The template is not approved for '+group+'.')
            if sem['legendary'] and not t.get('legendary',False):raise ValidationError('This template does not support legendary cards.')
            if sem.get('power') is not None and not ('pt' in t['data']['text'] or 'pt' in (t.get('mapping') or {}).values()):raise ValidationError('A creature template needs a P/T text slot.')
            data=custom_data(t,sem,sf.get('card_faces',[])[1:]);data.update(artSource=sem['art'],setSymbolSource=sem['set_symbol_source'],infoArtist=str(artist))
            if not settings.get('disableAutofit',False):native.auto_fit(data,sem['art_local_path'])
            recipe='custom:'+choice
        for k in ('artX','artY','artZoom','artRotate'):
            if k in options.get('fit',{}):
                v=float(options['fit'][k])
                if not math.isfinite(v) or (k=='artZoom' and v<=0):raise ValidationError('Invalid artwork placement.')
                data[k]=v
        if options.get('rawCard'):
            data=copy.deepcopy(options['rawCard']);data['artSource']=sem['art'];data['setSymbolSource']=sem['set_symbol_source'];data['infoArtist']=str(artist)
        data['artSource']='/api/assets/'+art_id;data['setSymbolSource']='/api/assets/'+symbol_id
        key=render_key(data,art_id,template_cache_version);warning=crop_metrics(art['width'],art['height'],data)
        if intentional_art_window_crop(group,choice,art,options,settings):
            warning={**warning,'warning':False,'intentionalArtWindow':True}
        return {'name':sem['name'],'data':data,'renderKey':key,'render':self.store.render_get(key),'group':group,'recipe':recipe,'crop':warning,'flags':flags,'artId':art_id,'symbolId':symbol_id,'artist':str(artist),'credit':credit,'generationVersion':PIPELINE_VERSION,'templateKey':template_key,'templateVersion':template_version,'templateCacheVersion':template_cache_version}
