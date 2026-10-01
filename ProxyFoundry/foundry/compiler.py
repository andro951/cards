"""Adapter over unchanged v58 templates. Overrides are opt-in, never automatic guesses."""
from __future__ import annotations
import copy,math,re
from PIL import Image
from .domain import ValidationError,ORDINARY_GROUPS,GROUP_LABELS,type_group,crop_metrics,render_key,RARITIES,GENERATION_VERSION,PIPELINE_VERSION,stable_hash
from .legacy import compiler as native,ingest
from .images import data_uri
from .credits import resolve_credit
from .template_model import apply_regions

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
BUILTINS.extend([
 {'id':'token-classic','name':'Classic arched token','description':'Classic token frame; larger art for short keywords, a rules box for longer text.','legendary':True,'groups':['token']},
 {'id':'token-full-art','name':'Modern full-art token','description':'Modern token frame; larger art for short keywords, a rules box for longer text.','legendary':True,'groups':['token']},
 {'id':'token-borderless','name':'Modern borderless token','description':'Edge-to-edge artwork with outlined rules text and the modern token bars.','legendary':True,'groups':['token']},
 {'id':'godzilla-card','name':'Godzilla full art · non-land','description':'Complete alternate-name frame for cards and tokens.','legendary':True,'groups':['standard','legendary','token']},
 {'id':'godzilla-land','name':'Godzilla full art · land','description':'Complete alternate-name frame for lands.','legendary':True,'groups':['land','legendary-land','basic-land']},
])
SINGLE_SURFACE={'adventure','split','flip','room','prepare'}
APPROVED_MODAL_DFC_PAIRS={
    ('Esika, God of the Tree','The Prismatic Bridge'),
    ('Bruce Banner','The Incredible Hulk'),
}
NEEDS_CUSTOM={'split','adventure','room','planar','scheme','vanguard','case','special-land','dungeon','conspiracy'}
CARD_FOOTER_NOTE='BulkProxyForge • Unofficial Proxy'
_MODAL_MANA_TOKEN_RE=re.compile(r'\{[^{}]+\}')

# Built-in cache versions are intentionally scoped. For Automatic, bump only the
# affected structural group (for example AUTO_TEMPLATE_VERSIONS['station']=2).
# Version 1 preserves the historical render key, so adding this system does not
# itself invalidate existing finished cards.
AUTO_TEMPLATE_VERSIONS={group:1 for group in GROUP_LABELS}
# Saga rendering uses a persistent native overlay canvas. Version 2 refreshes
# that canvas for each loaded Saga instead of reusing the previous Saga's
# chapter shields/dividers. Scope invalidation to Saga cards only.
AUTO_TEMPLATE_VERSIONS.update({'standard':6,'legendary':6,'land':3,'legendary-land':3,'basic-land':2,'saga':8,'saga-creature':11,'class':4,'transform-front':12,'transform-back':12,'modal-front':2,'modal-back':2,'station':5,'planeswalker':7,'meld':4,'battle':3,'token':3,'emblem':1,'prepare':2})
BUILTIN_TEMPLATE_VERSIONS={'normal':2,'land':2,'legend-land':2,'godzilla-card':3,'godzilla-land':3,'token-classic':1,'token-full-art':1,'token-borderless':1}
AUTO_TEMPLATE_VERSIONS['token']=4
AUTO_TEMPLATE_VERSIONS['station']=6

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
    """Use the matching underframe for Scryfall Stations; expose custom full art.

    Custom Station art is full-bleed, so the ordinary M15 Frame component must
    not sit behind the transparent portion of the Station overlay. Scryfall art
    keeps the complete artifact underframe used by the native Station recipe.
    """
    frames=data.get('frames',[])
    components=[frame for frame in frames if _station_frame_component(frame)]
    if not components:return False
    if _is_custom_art_origin(art_origin):
        data['frames']=[frame for frame in frames if not _station_frame_component(frame)]
        return True
    for frame in components:
        frame['src']='/img/frames/m15/regular/m15FrameA.png'
        frame['name']='Artifact Frame'
    return True


def build_station_land_data(sem,artist,autofit,flags,art_origin):
    """Reuse the normal native Station frame and geometry for Station lands."""
    donor=copy.deepcopy(sem)
    # The preserved Spacecraft recipe requires donor PT, cleared below for lands.
    donor.update(types=['Artifact'],subtypes=['Spacecraft'],layout='station',
                 power='0',toughness='0',colors=sem.get('land_colors',[]))
    try:
        data=native.build_one(donor,{'artist':artist},False,flagged_sagas=flags)['data']
    except native.BuildError as exc:
        raise ValidationError(str(exc)) from exc
    data['text']['type']['text']=sem['printed_type_line']
    data['text']['pt']['text']=''
    apply_station_underframe_policy(data,sem,art_origin)
    if autofit:native.auto_fit(data,sem['art_local_path'])
    return sem,data,'station'


def apply_prepare_frame_color(data,sem):
    """Color the approved Prepare geometry using the host card's frame color."""
    if data.get('version')!='prepare':return False
    color=frame_treatment_code(sem)
    body='A' if 'Artifact' in sem.get('types',[]) else (color if color and color in 'WUBRGM' else 'A')
    for frame in data.get('frames',[]):
        if not isinstance(frame,dict):continue
        src=str(frame.get('src',''))
        if src=='/img/frames/m15/regular/m15PTB.png':
            frame['src']=f'/img/frames/m15/regular/m15PT{body}.png'
            frame['name']=f'{native.COLOR_NAMES[body]} Power/Toughness'
        elif src=='/img/frames/prepare/regular/b.png':
            frame['src']=f'/img/frames/prepare/regular/{body.lower()}.png'
            frame['name']=f'{native.COLOR_NAMES[body]} Prepare Frame'
    return True

_FRAME_BOX_MASKS={'Title','Type','Rules','Text','Text (Right)'}
_FRAME_PINLINE_MASK='Pinline'

def frame_treatment_colors(sem):
    """Return the semantic colors that own the universal frame effects."""
    types=set(sem.get('types',[]))
    source=sem.get('land_colors',[]) if 'Land' in types else sem.get('colors',[])
    result=[]
    for color in source or []:
        if color in 'WUBRG' and color not in result:result.append(color)
    return result

def frame_treatment_code(sem):
    """Resolve title/type/rules/crown color independently of card structure."""
    colors=frame_treatment_colors(sem)
    if len(colors)>=2:return 'M'
    if colors:return colors[0]
    types=set(sem.get('types',[]))
    if 'Land' in types:return 'L'
    if 'Artifact' in types:return 'A'
    return None

def _frame_effect_source(src,code):
    """Switch an effect layer to the requested color in the same asset family."""
    if not code:return src
    match=re.fullmatch(r'/img/frames/token/m15/(regular|textless)/[wubrgmal]\.png',src)
    if match:return f'/img/frames/token/m15/{match.group(1)}/{(code if code in "WUBRGMAL" else "A").lower()}.png'
    match=re.fullmatch(r'/img/frames/token/(regular|textless|textless-borderless)/(?:tokenFrame[WUBRGMAL](?:Regular|Textless)|frameC)\.png',src)
    if match:
        family=match.group(1)
        filename='frameC.png' if code=='C' else f'tokenFrame{code}{"Regular" if family=="regular" else "Textless"}.png'
        return f'/img/frames/token/{family}/{filename}'

    # Prepare uses one native color image with different masks for its bars,
    # rules, and body. The body remains owned by the structural recipe.
    if re.fullmatch(r'/img/frames/prepare/regular/[wubrgma]\.png',src):
        return f'/img/frames/prepare/regular/{code.lower()}.png' if code in 'WUBRGMA' else src

    # Ordinary M15 families.
    if re.fullmatch(r'/img/frames/m15/regular/m15Frame[WUBRGMALCV]\.png',src):
        return f'/img/frames/m15/regular/m15Frame{code}.png' if code in 'WUBRGMALC' else src
    if re.fullmatch(r'/img/frames/m15/nyx/m15Frame[WUBRGMALC]Nyx\.png',src):
        return f'/img/frames/m15/nyx/m15Frame{code}Nyx.png' if code in 'WUBRGMALC' else src

    # Transform/Meld families.
    if re.fullmatch(r'/img/frames/m15/transform/regular/front[WUBRGMALV]\.png',src):
        return f'/img/frames/m15/transform/regular/front{code}.png' if code in 'WUBRGMAL' else src
    if re.fullmatch(r'/img/frames/m15/transform/regular/new/back[WUBRGMALV]\.png',src):
        return f'/img/frames/m15/transform/regular/new/back{code}.png' if code in 'WUBRGMALV' else src
    if re.fullmatch(r'/img/frames/m15/transform/regular/back[WUBRGMALV]\.png',src):
        return f'/img/frames/m15/transform/regular/back{code}.png' if code in 'WUBRGMAL' else src

    # Battle family.
    if re.fullmatch(r'/img/frames/m15/battle/[wubrgmalc]\.png',src):
        return f'/img/frames/m15/battle/{code.lower()}.png' if code in 'WUBRGMALC' else src

    # Saga families.
    if re.fullmatch(r'/img/frames/saga/regular/sagaFrame[WUBRGMA]\.png',src) or src=='/img/frames/saga/regular/l.png':
        if code=='L':return '/img/frames/saga/regular/l.png'
        return f'/img/frames/saga/regular/sagaFrame{code}.png' if code in 'WUBRGMA' else src
    if re.fullmatch(r'/img/frames/saga/creature/[wubrgmal]\.png',src):
        return f'/img/frames/saga/creature/{code.lower()}.png' if code in 'WUBRGMAL' else src

    # Full-art land and planeswalker families.
    if re.fullmatch(r'/img/frames/m15/genericShowcase/m15GenericShowcaseFrame[WUBRGMALC]\.png',src):
        return f'/img/frames/m15/genericShowcase/m15GenericShowcaseFrame{code}.png' if code in 'WUBRGMALC' else src
    if re.fullmatch(r'/img/frames/planeswalker/regular/planeswalkerFrame[WUBRGMA]\.png',src):
        return f'/img/frames/planeswalker/regular/planeswalkerFrame{code}.png' if code in 'WUBRGMA' else src

    # Compact full-art-land accents.
    m=re.fullmatch(r'/img/frames/m15/boxTopper/short/([wubrgmal]{1,2})\.png',src)
    if m:
        if code=='L':stem='l'
        elif code in 'WUBRGM':stem=code.lower()+('l' if m.group(1).endswith('l') else '')
        elif code=='A':stem='a'
        else:return src
        return f'/img/frames/m15/boxTopper/short/{stem}.png'

    # Class is already a full-frame semantic color, but support masked derivatives too.
    if re.fullmatch(r'/img/frames/class/[wubrgmal]\.png',src):
        return f'/img/frames/class/{code.lower()}.png' if code in 'WUBRGMAL' else src
    return src

def _crown_color_variant(src,code):
    """Return the same native legendary-crown asset in another color.

    Do not infer this from card type or from a vague "crown" substring. Card
    Conjurer has several complete W/U/B/R/G crown families with different
    filename conventions, plus unrelated inner crowns, masks, outlines and
    one-off decorative crowns. Only complete legendary-crown color families
    belong here.
    """
    if code not in 'WUBRGMALC':return None
    src=str(src or '')
    lower=code.lower()
    lowered=src.lower()

    # Never treat supporting/decorative crown assets as color-bearing crown
    # components. Inner crowns are visible Nyx/Companion crown components and
    # intentionally receive the same universal treatment as the outer crown.
    if any(token in lowered for token in (
        'thumb','mask','outline','bordercover','border_cover','cutout','pinline',
    )):
        return None

    # Standard M15 crown family, including floating/alternate floating crowns.
    m=re.fullmatch(
        r'(.*?/m15/crowns/m15Crown)([WUBRGMALC])(Floating(?:Alt)?\.png|\.png)',
        src,
    )
    if m:return m.group(1)+code+m.group(3)

    # Universes Beyond M15-style crown filenames.
    m=re.fullmatch(r'(.*?/m15/ub/crowns/m15Crown)([WUBRGMALC])(\.png)',src)
    if m:return m.group(1)+code+m.group(3)

    # Complete families where the color is embedded in a longer crown filename.
    for pattern in (
        r'(.*?/m15/nickname/m15NicknameCrown)([WUBRGMALC])(\.png)',
        r'(.*?/m15/zendikarRising/m15ZendikarRisingCrown)([WUBRGMALC])(\.png)',
    ):
        m=re.fullmatch(pattern,src)
        if m:return m.group(1)+code+m.group(3)

    # Older M15 Nyx/Companion inner crowns embed the color before the style.
    m=re.fullmatch(
        r'(.*?/m15/innerCrowns/m15InnerCrown)([WUBRGMALC])(Nyx|Companion)(\.png)',
        src,
    )
    if m:return m.group(1)+code+m.group(3)+m.group(4)

    # Complete families that use a lower-case color prefix before "Crown".
    m=re.fullmatch(r'(.*?/m15/(?:oilslick|praetors)/)([wubrgmalc])(Crown\.png)',src)
    if m:return m.group(1)+lower+m.group(3)

    # Modal, transform, crystal, dossier, etched, LOTR, custom and similar
    # packs put the colored crown in a literal crown/crowns directory and use a
    # one-letter filename. Requiring the directory segment prevents accidental
    # matches on unrelated files such as m15/mid/bCrown.png.
    m=re.fullmatch(r'(.*?/(?:crown|crowns|innerCrowns)(?:/[^/]+)*/)([wubrgmalc])(\.png)',src)
    if m:return m.group(1)+lower+m.group(3)

    return None

def _universal_crown_source(src,code):
    """Recolor any recognized native crown without changing its frame family."""
    return _crown_color_variant(src,code) or src

def _is_crown_source(src):
    """True only for native color-variant crown assets, never masks/outlines."""
    return _crown_color_variant(src,'M') is not None

def _is_pinline_mask(mask):
    return isinstance(mask,dict) and 'pinline' in str(mask.get('name','')).lower()

def _crown_family_key(src):
    """Stable identity for one native crown component's color-variant family."""
    return _crown_color_variant(src,'M')

def _old_dual_crown_families(frames):
    """Return only crown families that already contain the approved old blend."""
    families={}
    for frame in frames:
        if not isinstance(frame,dict):continue
        key=_crown_family_key(str(frame.get('src','')))
        if not key:continue
        families.setdefault(key,[]).append(frame)
    return {
        key for key,layers in families.items()
        if len(layers)>=2 and any(
            any(isinstance(mask,dict) and mask.get('name')=='Right Blend'
                for mask in frame.get('masks',[]))
            for frame in layers
        )
    }

def _dual_crown_layers_like(frame,dual):
    """Restore the old native-PNG crown blend in the reference crown family."""
    first,second=dual
    src=str(frame.get('src',''))

    # Ordinary M15 regular crown: use the exact old helper that produced the
    # approved look before universal post-processing existed.
    if re.fullmatch(r'/img/frames/m15/crowns/m15Crown[WUBRGMALC]\.png',src):
        return native.build_dual_standard_crown_layers(first,second,include_border_cover=False)

    # Academy-Ruins/full-art floating crown: use the exact old floating helper.
    if re.fullmatch(r'/img/frames/m15/crowns/m15Crown[WUBRGMALC]Floating\.png',src):
        return native.build_floating_land_crown_layers([first,second])

    # Preserve the alternate floating geometry/assets if a custom frame uses it.
    m=re.fullmatch(r'/img/frames/m15/crowns/m15Crown([WUBRGMALC])FloatingAlt\.png',src)
    if m:
        bounds=copy.deepcopy(frame.get('bounds') or {'x':0.0307,'y':0.0191,'width':0.9387,'height':0.1024})
        opacity=frame.get('opacity')
        def layer(code,name,masks=None):
            out={'name':name,'src':f'/img/frames/m15/crowns/m15Crown{code}FloatingAlt.png',
                 'masks':masks or [],'bounds':copy.deepcopy(bounds)}
            if opacity is not None:out['opacity']=opacity
            return out
        return [
            layer(second,f"{native.COLOR_NAMES[second]} Legend Crown (Right Blend)",
                  [{'src':native.dual_crown_right_blend_mask_src(),'name':'Right Blend'}]),
            layer(first,f"{native.COLOR_NAMES[first]} Legend Crown"),
        ]

    # Every other CardConjurer crown family gets the same approved construction:
    # two genuine native crown PNGs, with only the second/right color faded in by
    # the old full-card smooth blend mask. This preserves each family's own
    # texture, shading, alpha, bounds and opacity instead of painting an SVG over it.
    first_src=_crown_color_variant(src,first)
    second_src=_crown_color_variant(src,second)
    if first_src and second_src:
        base=copy.deepcopy(frame)
        base['src']=first_src
        base['name']=f"{native.COLOR_NAMES[first]} Legend Crown"
        base['masks']=[]

        right=copy.deepcopy(frame)
        right['src']=second_src
        right['name']=f"{native.COLOR_NAMES[second]} Legend Crown (Right Blend)"
        right['masks']=[{'src':native.dual_crown_right_blend_mask_src(),'name':'Right Blend'}]
        # Earlier entries render later in CardConjurer, matching the preserved
        # old helper's right-blend-over-left ordering.
        return [right,base]

    return [copy.deepcopy(frame)]

def apply_universal_frame_color_treatment(data,sem):
    """Apply the five shared color effects once, after structural frame selection.

    Pinline, title bar, type bar, rules/text box, and legendary crown all use
    the same semantic color decision regardless of whether the card is an
    Artifact, Vehicle, Saga, Station, Transform/Meld card, land, planeswalker,
    or another structural family. Structural masks are split away first so the
    card's body/frame remains whatever its recipe selected.

    Exactly two colors use the same approved left-to-right color transition on
    pinlines and legendary crowns. Pinlines use the flat gradient fill; crowns
    retain the old two-native-PNG construction with a full-card smooth fade mask
    so their texture, shading, geometry and alpha are preserved. Title/type/rules
    use multicolor/gold for two or more colors. Lands use only land_colors.
    """
    colors=frame_treatment_colors(sem)
    code=frame_treatment_code(sem)
    dual=native.canonical_dual_color_order(colors) if len(colors)==2 else []
    if not code and not dual:return False

    source_frames=data.get('frames',[])
    preserved_dual_crown_families=_old_dual_crown_families(source_frames) if dual else set()
    rebuilt=[];changed=False;dualized_crown_families=set()
    for frame in source_frames:
        if not isinstance(frame,dict):
            rebuilt.append(frame);continue

        old_src=str(frame.get('src',''))

        # A card can contain multiple independent crown components. Process
        # each native color family independently, just as pinlines are handled
        # independently by their masks.
        crown_family=_crown_family_key(old_src)
        if crown_family:
            if dual:
                if crown_family in preserved_dual_crown_families:
                    rebuilt.append(copy.deepcopy(frame))
                elif crown_family not in dualized_crown_families:
                    rebuilt.extend(_dual_crown_layers_like(frame,dual))
                    dualized_crown_families.add(crown_family);changed=True
            else:
                copied=copy.deepcopy(frame)
                new=_universal_crown_source(old_src,code)
                if new!=old_src:
                    copied['src']=new;changed=True
                rebuilt.append(copied)
            continue

        masks=frame.get('masks',[])
        if not isinstance(masks,list) or not masks:
            copied=copy.deepcopy(frame)
            # Standalone pinline layers are uncommon, but if a frame explicitly
            # identifies itself as one, give it the same universal gradient rule
            # instead of silently skipping it.
            if 'pinline' in str(copied.get('name','')).lower():
                if dual and not old_src.startswith('data:image'):
                    copied['src']=native.dual_gradient_fill_src(*dual)
                    copied['masks']=[{'src':old_src,'name':'Pinline'}]
                    if isinstance(copied.get('bounds'),dict):
                        copied['ogBounds']={'x':0,'y':0,'width':1,'height':1}
                    changed=True
                elif not dual:
                    new=_frame_effect_source(old_src,code)
                    if new!=old_src:
                        copied['src']=new;changed=True
            rebuilt.append(copied);continue

        pin=[copy.deepcopy(m) for m in masks if _is_pinline_mask(m)]
        boxes=[copy.deepcopy(m) for m in masks if isinstance(m,dict) and m.get('name') in _FRAME_BOX_MASKS]
        other=[copy.deepcopy(m) for m in masks if not (
            isinstance(m,dict) and (
                _is_pinline_mask(m) or m.get('name') in _FRAME_BOX_MASKS
            )
        )]

        # The structural portion keeps its exact original source.
        if other:
            structural=copy.deepcopy(frame)
            structural['masks']=other
            rebuilt.append(structural)

        # Title/type/rules all share the same semantic single/gold color.
        if boxes:
            layer=copy.deepcopy(frame)
            layer['masks']=boxes
            old=str(layer.get('src',''))
            layer['src']=_frame_effect_source(old,code)
            if layer['src']!=old:changed=True
            rebuilt.append(layer)

        # Pinline uses the same two-color gradient source as the crown.
        if pin:
            layer=copy.deepcopy(frame)
            layer['masks']=pin
            old=str(layer.get('src',''))
            if dual:
                first,second=dual
                layer['src']=native.dual_gradient_fill_src(first,second)
                saga=any('/saga/' in str(mask.get('src','')) for mask in pin)
                layer['name']=f"{native.COLOR_NAMES[first]}/{native.COLOR_NAMES[second]} Gradient "+('Saga Pinline' if saga else 'Pinline')
            else:
                layer['src']=_frame_effect_source(old,code)
            if layer['src']!=old:changed=True
            rebuilt.append(layer)

        if not other and not boxes and not pin:
            rebuilt.append(copy.deepcopy(frame))

    data['frames']=rebuilt
    return changed

MIRACLE_FRAME_BOUNDS={'x':0.04,'y':0.0286,'width':0.92,'height':0.5324}

def is_miracle_card(sem):
    """Recognize Miracle from Scryfall keywords, with a strict Oracle fallback."""
    keywords=sem.get('keywords',[]) or []
    if any(str(keyword).strip().lower()=='miracle' for keyword in keywords):
        return True
    return bool(re.search(r'(?im)^\s*Miracle\s+\{',str(sem.get('oracle_text') or '')))

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

_SOURCE_AWARE_FULL_ART_RECIPES={'colorless_creature','colorless_creature_legendary'}

def source_aware_art_family(sem,recipe,group):
    """Cards that use an art-window Scryfall image but a full-art custom image."""
    return bool(
        sem.get('devoid')
        or group in {'station','planeswalker'}
        or recipe in _SOURCE_AWARE_FULL_ART_RECIPES
    )

def apply_source_aware_art_placement(data,art,sem,recipe,group,art_origin,autofit,raw_card=False):
    """Apply one provenance-based art policy across colorless/Devoid/Station/PW frames.

    Scryfall selected-printing artwork keeps the native printed art window and
    its native CardConjurer placement for every supported family, including
    tall-textbox Planeswalkers.

    Custom artwork uses the common 80px-inset full-art region and the same
    centered-overflow placement math across all supported frame families.
    """
    if raw_card or not source_aware_art_family(sem,recipe,group):return None

    if art_origin=='Scryfall selected printing':
        return {'mode':'art-window','suppressCropWarning':bool(autofit)}

    data['artBounds']=copy.deepcopy(FULL_ART_NONLAND_BOUNDS)
    if autofit:
        for key,value in full_art_nonland_placement(art).items():data[key]=value
    return {'mode':'full-art','suppressCropWarning':False}


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
    # what their search ability can find even though they do not make that mana.
    # "a basic land card" is unrestricted across all five basic land types, so
    # cards such as Prismatic Vista use the gold/five-color land treatment.
    if re.search(r'\bbasic\s+land\s+cards?\b',clean,re.I):
        for color in 'WUBRG':add(color)
    else:
        # Typed fetches such as "Swamp or Forest card" keep only those colors.
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
    type_line=get('type_line')
    types=ingest.split_type_line(type_line)
    d={**types,'name':get('name'),'nickname':str(get('flavor_name','') or '').strip(),'mana_cost':get('mana_cost'),'oracle_text':get('oracle_text'),'colors':get('colors',[]),'keywords':get('keywords',[]),'rarity':sf.get('rarity','common'),'flavor_text':normalize_scryfall_inline_italics(get('flavor_text'))}
    d['supertypes']=[word for word in str(type_line).replace('—',' - ').replace('–',' - ').partition(' - ')[0].split() if word in {'Basic','Legendary','Snow','World','Token'}]
    d['printed_type_line']=str(type_line)
    d['devoid']=any(str(keyword).strip().lower()=='devoid' for keyword in d['keywords']) or bool(re.search(r'(?im)^\\s*Devoid\\b',d['oracle_text']))
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


_DEVOID_EFFECT_MASKS={'Pinline','Title','Type','Rules','Frame','Border'}

def _devoid_frame_code(sem):
    """Use colored mana symbols for Devoid's visual frame while the card remains colorless."""
    found=[]
    for token in re.findall(r'\{([^{}]+)\}',str(sem.get('mana_cost') or '')):
        for part in token.upper().split('/'):
            if part in 'WUBRG' and part not in found:found.append(part)
    if len(found)>=2:return 'M'
    if found:return found[0]
    if 'Artifact' in set(sem.get('types',[])):return 'A'
    if 'Land' in set(sem.get('types',[])):return 'L'
    return 'A'

def apply_devoid_frame(data,sem):
    """Retarget ordinary M15 layers to CardConjurer's genuine Zendikar Devoid pack.

    Native colorless-creature recipes may use different source filenames, so
    identify the structural frame by its M15 mask roles rather than by the old
    image path. This mirrors the M15Devoid pack: every structural mask samples
    the same colored Devoid frame, while the creature P/T uses m15DevoidPT.png.
    """
    if not sem.get('devoid'):return False
    code=_devoid_frame_code(sem)
    frame_src=f'/img/frames/m15/devoid/m15DevoidFrame{code}.png'
    changed=False;structural=0;pt_found=False
    for frame in data.get('frames',[]):
        if not isinstance(frame,dict):continue
        masks={
            str(mask.get('name') or '')
            for mask in frame.get('masks',[])
            if isinstance(mask,dict)
        }
        if masks & _DEVOID_EFFECT_MASKS:
            frame['src']=frame_src
            frame['name']=native.COLOR_NAMES.get(code,code)+' Devoid Frame'
            structural+=1;changed=True
            continue
        if 'power/toughness' in str(frame.get('name') or '').lower():
            frame['src']='/img/frames/m15/devoid/m15DevoidPT.png'
            frame['name']='Devoid Power/Toughness'
            frame['bounds']={'x':0.7573,'y':0.8848,'width':0.188,'height':0.0733}
            pt_found=True;changed=True

    # Fail closed if the preserved native recipe ever stops exposing ordinary
    # M15 structural masks. Silently claiming m15Devoid while drawing another
    # frame is exactly the regression this guard prevents.
    if not structural:
        raise ValidationError('Devoid frame support could not find the native M15 structural frame layers.')
    if 'Creature' in set(sem.get('types',[])) and sem.get('power') is not None and not pt_found:
        data.setdefault('frames',[]).insert(0,{
            'name':'Devoid Power/Toughness',
            'src':'/img/frames/m15/devoid/m15DevoidPT.png',
            'masks':[],
            'bounds':{'x':0.7573,'y':0.8848,'width':0.188,'height':0.0733},
        })

    data['version']='m15Devoid'
    return changed


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
    """Pick structural shell only; universal post-processing owns crown color."""
    types=set(sem.get('types',[]))
    color=_transform_color_code(sem)
    if 'Land' in types:return 'L','L'
    if 'Artifact' in types:return 'A','A'
    return color,color


_TRANSFORM_EFFECT_ICONS={
    'compasslanddfc':('Compass','/img/frames/m15/transform/icons/compass.svg','Land','/img/frames/m15/transform/icons/land.svg'),
    'sunmoondfc':('Sun','/img/frames/m15/transform/icons/sun.svg','Crescent Moon','/img/frames/m15/transform/icons/moon.svg'),
    'mooneldrazidfc':('Crescent Moon','/img/frames/m15/transform/icons/moon.svg','Emrakul','/img/frames/m15/transform/icons/emrakul.svg'),
    'originpwdfc':('Planeswalker Ember','/img/frames/m15/transform/icons/spark.svg','Planeswalker Spark','/img/frames/m15/transform/icons/planeswalker.svg'),
    'fandfc':('Closed Fan','/img/frames/m15/transform/icons/fanClosed.svg','Open Fan','/img/frames/m15/transform/icons/fanOpen.svg'),
}


def _transform_icon_for(card,side):
    if card.get('layout')=='meld' and side=='front':
        return {'name':'Meld','src':'/img/frames/m15/transform/icons/hammer.png','masks':[],'bounds':copy.deepcopy(_TRANSFORM_ICON['bounds'])}
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
            source_code,floating=crown.groups()
            # Native Card Tools may already have built a two-color legendary
            # crown as two separate W/U/B/R/G PNG layers plus Right Blend.
            # Preserve each layer's color identity while changing only its
            # structural family to Transform/Meld. The universal pass that runs
            # afterward can then recognize and preserve that approved blend.
            target_code=source_code if source_code in set('WUBRGMAL') else crown_code
            if target_code not in set('WUBRGMAL'):
                raise ValidationError('This legendary transform face uses an unsupported crown color.')
            if floating:
                frame['src']=f'/img/frames/m15/transform/crowns/floating/{target_code.lower()}.png'
            else:
                frame['src']=(f'/img/frames/m15/transform/crowns/regular/{target_code.lower()}.png' if side=='front'
                              else f'/img/frames/m15/transform/crowns/regular/new/{target_code.lower()}.png')
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


def enforce_saga_creature_rules_frame(data,sem):
    """Keep creature Sagas with ordinary trailing rules on the short full-frame pack.

    FINAL FANTASY Saga creatures such as Summon: Leviathan put chapter abilities
    above the type line and ordinary creature rules (for example Ward {2}) in
    the lower rules2 box.  That printed treatment uses Card-Cipherist's complete
    Saga Creature PNG and its shorter 1009/588/844/1533 art well.  Do not split,
    mask, stretch, or substitute a normal Saga frame for this structural layer.
    """
    meta=native.saga_creature_layout_metadata(sem)
    if not str(meta.get('rules2') or '').strip():
        return False

    frames=data.setdefault('frames',[])
    full=[
        frame for frame in frames
        if isinstance(frame,dict)
        and re.fullmatch(r'/img/frames/saga/creature/[wubrgmcl]\.png',str(frame.get('src','')))
    ]
    if len(full)!=1:
        raise ValidationError('Saga Creature with trailing rules must contain exactly one complete short Saga Creature frame.')
    # The creature-Saga PNG is already the complete structural frame.  Masking
    # it into ordinary Saga pieces is what creates the incorrect full-height look.
    full[0]['masks']=[]

    art=native.SAGA_CREATURE_ART_BOUNDS_PX
    data['artBounds']={
        'x':art['x']/native.CARD_WIDTH,
        'y':art['y']/native.CARD_HEIGHT,
        'width':art['width']/native.CARD_WIDTH,
        'height':art['height']/native.CARD_HEIGHT,
    }
    data['setSymbolBounds']={
        'x':0.9227,
        'y':native.SAGA_CREATURE_SET_SYMBOL_Y_PX/native.CARD_HEIGHT,
        'width':0.12,'height':0.0381,'vertical':'center','horizontal':'right',
    }
    data['setSymbolX']=native.SAGA_CREATURE_SET_SYMBOL_X_PX/native.CARD_WIDTH
    data['setSymbolY']=native.SAGA_CREATURE_SET_SYMBOL_ANCHOR_Y_PX/native.CARD_HEIGHT

    text=data.setdefault('text',{})
    type_box=text.get('type')
    if isinstance(type_box,dict):
        type_box['y']=native.SAGA_CREATURE_TYPE_Y_PX/native.CARD_HEIGHT
    rules2=text.get('rules2')
    if not isinstance(rules2,dict):
        raise ValidationError('Saga Creature with trailing rules is missing its lower rules text box.')
    rb=native.SAGA_CREATURE_RULES2_BOUNDS_PX
    rules2.update({
        'x':rb['x']/native.CARD_WIDTH,
        'y':rb['y']/native.CARD_HEIGHT,
        'width':rb['width']/native.CARD_WIDTH,
        'height':rb['height']/native.CARD_HEIGHT,
    })
    return True


def cover_art_window(data,art):
    """Fill the complete artBounds and center-crop whichever source axis overflows.

    The source is scaled until both the art-window width and height are covered.
    One axis will normally extend beyond the window; that overflow is cropped
    equally from both sides by centering the scaled image in the art window.
    """
    bounds=data.get('artBounds')
    if not isinstance(bounds,dict):raise ValidationError('This frame is missing its art window.')
    try:
        card_w=float(data.get('width') or native.CARD_WIDTH)
        card_h=float(data.get('height') or native.CARD_HEIGHT)
        image_w=float(art.get('width') or 0)
        image_h=float(art.get('height') or 0)
        window_x=float(bounds.get('x') or 0)*card_w
        window_y=float(bounds.get('y') or 0)*card_h
        window_w=float(bounds.get('width') or 0)*card_w
        window_h=float(bounds.get('height') or 0)*card_h
    except (TypeError,ValueError):
        raise ValidationError('This frame has invalid art-window geometry.')
    if min(card_w,card_h,image_w,image_h,window_w,window_h)<=0:
        raise ValidationError('Artwork or art-window dimensions are invalid.')

    zoom=max(window_w/image_w,window_h/image_h)
    scaled_w=image_w*zoom
    scaled_h=image_h*zoom
    x=window_x+(window_w-scaled_w)/2
    y=window_y+(window_h-scaled_h)/2
    data['artX']=x/card_w
    data['artY']=y/card_h
    data['artZoom']=zoom
    data['artRotate']=0
    return True


def _short_saga_creature_needs_cover_fit(sem):
    if 'Creature' not in set(sem.get('types',[])) or 'Saga' not in set(sem.get('subtypes',[])):
        return False
    meta=native.saga_creature_layout_metadata(sem)
    return bool(str(meta.get('rules2') or '').strip())


def apply_short_saga_creature_art_fit(data,art,art_origin):
    """Cover-fit short Saga-creature art to its final printed art window.

    Scryfall art has already had the printed top/bottom trim applied before this
    point. From here on, source provenance does not affect geometry: scale until
    both window dimensions are covered, then center the overflow on the other
    axis. This is the same invariant used for every art-box cover fit.
    """
    return cover_art_window(data,art)


def apply_dual_saga_tassels(data,sem,group):
    """Add only the Saga-specific two-color tassels; pinline is universal."""
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
    if group=='saga-creature':
        target=next((i for i,frame in enumerate(frames)
                     if isinstance(frame,dict)
                     and re.fullmatch(r'/img/frames/saga/creature/[wubrgmcl]\.png',str(frame.get('src','')))
                     and not frame.get('masks')),None)
        missing='Two-color Saga Creature did not contain its complete short Saga Creature frame layer.'
    else:
        target=next((i for i,frame in enumerate(frames)
                     if isinstance(frame,dict)
                     and re.fullmatch(r'/img/frames/saga/regular/sagaFrame[WUBRGMALC]\.png',str(frame.get('src','')))
                     and not frame.get('masks')),None)
        missing='Two-color Saga did not contain its complete Saga frame layer.'
    if target is None:
        raise ValidationError(missing)
    tassel1,tassel2=_SAGA_TASSEL_MASKS[group]
    # Native Saga and Saga-Creature frames are complete unmasked PNGs. Expose
    # only the pinline mask here; the universal color post-pass still owns the
    # actual dual-gradient selection, just as it does for every other card.
    # CardConjurer draws card.frames in reverse order. Banner is the broad/base
    # banner mask; BannerRight is the second/right piece. Put the right overlay
    # earlier in the array so it is drawn after the broad first-color banner.
    overlays=[
        {
            'name':'Saga Pinline',
            'src':_saga_color_frame_src(group,'M'),
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

def build_transform_saga_data(sem,group,card,artist,autofit,flags):
    """Build a transform face that is structurally a Saga.

    CardConjurer has genuine Saga structural frames but no separate transform-
    Saga frame pack. Preserve the complete Saga frame/chapter layout, then add
    the DFC identity icon for the appropriate side. The universal frame-color
    pass still runs afterward, exactly as it does for every other card family.
    """
    d0=copy.deepcopy(sem)
    for key in ('parent_name','face_index','scryfall_layout'):
        d0.pop(key,None)
    types=set(d0.get('types',[]))
    subtypes=set(d0.get('subtypes',[]))
    if 'Saga' not in subtypes or 'Enchantment' not in types:
        raise ValidationError('Transform Saga support requires an Enchantment — Saga face.')
    saga_group='saga-creature' if 'Creature' in types else 'saga'
    d0['layout']='saga_creature' if saga_group=='saga-creature' else 'saga'
    try:
        data=native.build_one(copy.deepcopy(d0),{'artist':artist},autofit,flagged_sagas=flags)['data']
    except native.BuildError as exc:
        raise ValidationError(str(exc)) from exc

    if saga_group=='saga-creature':
        enforce_saga_creature_rules_frame(data,sem)
    apply_dual_saga_tassels(data,sem,saga_group)
    side='front' if group=='transform-front' else 'back'
    icon=_transform_icon_for(card,side)
    if icon:
        data.setdefault('frames',[]).insert(0,icon)
        title=(data.get('text') or {}).get('title')
        if isinstance(title,dict):
            # Reserve the same left-side transform-icon clearance used by the
            # ordinary transform front instead of letting the icon cover title.
            old_x=float(title.get('x') or 0)
            right=old_x+float(title.get('width') or 0)
            title['x']=max(old_x,0.16)
            title['width']=max(0,right-title['x'])

    return d0,data,'saga_transform_'+side


def build_transform_data(sem,group,card,artist,autofit,flags):
    """Build a transform face using its real structural family."""
    if 'Saga' in set(sem.get('subtypes',[])):
        return build_transform_saga_data(sem,group,card,artist,autofit,flags)

    d0=_transform_classic_semantic(sem)
    try:
        data=native.build_one(copy.deepcopy(d0),{'artist':artist},autofit,flagged_sagas=flags)['data']
    except native.BuildError as exc:
        raise ValidationError(str(exc)) from exc
    side='front' if group=='transform-front' else 'back'
    _apply_transform_frame(data,side,sem,card)
    return d0,data,'m15_transform_'+side


def build_meld_data(sem,card,artist,autofit,flags):
    """Build the printed front of a meld card with CardConjurer's meld treatment."""
    d0=_transform_classic_semantic(sem)
    try:
        data=native.build_one(copy.deepcopy(d0),{'artist':artist},autofit,flagged_sagas=flags)['data']
    except native.BuildError as exc:
        raise ValidationError(str(exc)) from exc
    _apply_transform_frame(data,'front',sem,card)
    return d0,data,'m15_meld_front'


_BATTLE_ART_BOUNDS={'x':167/2100,'y':60/1500,'width':1873/2100,'height':1371/1500}
_BATTLE_SYMBOL_BOUNDS={'x':1945/2100,'y':925/1500,'width':180/2100,'height':86/1500,'vertical':'center','horizontal':'right'}

def _battle_frame_code(sem):
    colors=[c for c in sem.get('colors',[]) if c in 'WUBRG']
    types=set(sem.get('types',[]))
    if 'Artifact' in types:return 'A'
    if 'Land' in types:return 'L'
    if len(colors)==1:return colors[0]
    if len(colors)>=2:return 'M'
    return 'C'


_TOKEN_PT_BOUNDS={'x':0.7573,'y':0.8848,'width':0.188,'height':0.0733}
_TOKEN_ART_BOUNDS={'x':0.04,'y':0.0286,'width':0.92,'height':0.8953}
_TOKEN_M15_ART_WINDOW_BOUNDS={'x':0.0767,'y':0.1248,'width':0.8476,'height':0.5143}
_TOKEN_SET_SYMBOL_BOUNDS={'x':0.9213,'y':0.6743,'width':0.12,'height':0.041,'vertical':'center','horizontal':'right'}
_TOKEN_WATERMARK_BOUNDS={'x':0.5,'y':0.8177,'width':0.75,'height':0.1472}

def fit_token_art(data,art_local_path,autofit=True):
    """Fit token artwork to the visible art window for the active token frame."""
    version=str(data.get('version') or '')
    bounds=(
        _TOKEN_M15_ART_WINDOW_BOUNDS if version=='tokenRegularM15' else
        {**_TOKEN_M15_ART_WINDOW_BOUNDS,'height':0.6843} if version=='tokenTextlessM15' else
        {'x':0,'y':0,'width':1,'height':1} if version=='tokenTextlessBorderless' else
        _TOKEN_ART_BOUNDS
    )
    data['artBounds']=copy.deepcopy(bounds)
    if autofit:
        native.auto_fit(data,art_local_path)
        # Native fit rounds zoom to three decimals. Round upward when that
        # leaves a fractional-pixel gap at the edge of the token art window.
        with Image.open(art_local_path) as source:
            width,height=source.size
        required=max(bounds['width']*data['width']/width,bounds['height']*data['height']/height)
        current=float(data['artZoom'])
        if current+1e-9<required:
            zoom=math.ceil(required*1000)/1000
            data['artX']-=width*(zoom-current)/(2*data['width'])
            data['artY']-=height*(zoom-current)/(2*data['height'])
            data['artZoom']=zoom
    return True

def _token_frame_code(sem):
    colors=[]
    for color in sem.get('colors',[]) or []:
        if color in 'WUBRG' and color not in colors:colors.append(color)
    if len(colors)>=2:return 'M'
    if colors:return colors[0]
    types=set(sem.get('types',[]))
    if 'Artifact' in types:return 'A'
    if 'Land' in types:return 'L'
    return 'C'

def _token_frame_src(code):
    if code=='C':return '/img/frames/token/regular/frameC.png'
    return f'/img/frames/token/regular/tokenFrame{code}Regular.png'

def _token_pt_src(code):
    return f'/img/frames/m15/regular/m15PT{code if code in "WUBRGMAC" else "C"}.png'

def build_token_data(sem,artist,autofit,flags,style='token-classic'):
    """Build tokens using the selected genuine CardConjurer token family."""
    types=set(sem.get('types',[]))
    creature='Creature' in types
    base=copy.deepcopy(sem)
    # Start from the preserved ordinary compiler only to inherit its text,
    # credits, bottom-info, watermark and mana-symbol structures. Token-specific
    # geometry and every visible structural frame are replaced below.
    #
    # Colorless Scryfall tokens (notably Construct/Spirit) have no WUBRG color.
    # The ordinary donor compiler requires an inferable M15 color before we get
    # a chance to replace its frames, so give only the disposable donor a white
    # color when necessary. The real token frame below still resolves from the
    # original semantic data: Artifact -> A, otherwise truly colorless -> C.
    donor_colors=[x for x in base.get('colors',[]) if x in 'WUBRG']
    if not donor_colors:base['colors']=['W']
    base['layout']=('creature_legendary' if sem.get('legendary') else 'creature') if creature else ('card_legendary' if sem.get('legendary') else 'card_noncreature')
    try:
        data=native.build_one(base,{'artist':artist},False,flagged_sagas=flags)['data']
    except native.BuildError as exc:
        raise ValidationError(str(exc)) from exc

    code=_token_frame_code(sem)
    cname=native.COLOR_NAMES.get(code,'Colorless')
    frames=[]
    if creature and sem.get('power') is not None and sem.get('toughness') is not None:
        frames.append({
            'name':f'{cname} Power/Toughness',
            'src':_token_pt_src(code),
            'masks':[],
            'bounds':copy.deepcopy(_TOKEN_PT_BOUNDS),
        })

    # CardConjurer exposes Floating Legend Crowns as an addon for tokens.
    # Preserve that native token-compatible treatment for legendary token cards.
    if sem.get('legendary'):
        crown_code=code if code in 'WUBRGMALC' else 'M'
        frames.extend([
            {
                'name':f'{native.COLOR_NAMES.get(crown_code,crown_code)} Legend Crown',
                'src':f'/img/frames/m15/crowns/m15Crown{crown_code}Floating.png',
                'masks':[],
                'bounds':{'x':0.0307,'y':0.0191,'width':0.9387,'height':0.1024},
            },
            {
                'name':'Legend Crown Border Cover',
                'src':'/img/black.png','masks':[],
                'bounds':{'x':0.0394,'y':0.0277,'width':0.9214,'height':0.0177},
            },
            {
                'name':'Legend Crown Lower Cutout',
                'src':'/img/black.png','masks':[],'erase':True,
                'bounds':{'x':0.0734,'y':0.1096,'width':0.8532,'height':0.0143},
            },
            {
                'name':'Legend Crown Outline',
                'src':'/img/frames/m15/crowns/m15CrownFloatingOutline.png','masks':[],
                'bounds':{'x':0.028,'y':0.0172,'width':0.944,'height':0.1062},
            },
        ])

    frames.append({
        'name':f'{cname} Token Frame',
        'src':_token_frame_src(code),
        'masks':[],
    })
    data['frames']=frames
    data['version']='tokenRegular'
    data['artBounds']=copy.deepcopy(_TOKEN_ART_BOUNDS)
    data['setSymbolBounds']=copy.deepcopy(_TOKEN_SET_SYMBOL_BOUNDS)
    data['watermarkBounds']=copy.deepcopy(_TOKEN_WATERMARK_BOUNDS)

    text=data.setdefault('text',{})
    mana=text.setdefault('mana',{})
    title=text.setdefault('title',{})
    typ=text.setdefault('type',{})
    rules=text.setdefault('rules',{})
    pt=text.setdefault('pt',{})

    mana.update({
        'name':'Mana Cost','y':0.0613,'width':0.9292,'height':71/2100,
        'oneLine':True,'size':71/1638,'align':'right','shadowX':-0.001,
        'shadowY':0.0029,'manaCost':True,'manaSpacing':0,
    })
    title.update({
        'name':'Title','x':0.0854,'y':0.0522,'width':0.8292,'height':0.0543,
        'oneLine':True,'font':'belerenbsc','size':0.0381,'color':'white','align':'center',
    })
    typ.update({
        'name':'Type','x':0.0854,'y':0.65,'width':0.8292,'height':0.0543,
        'oneLine':True,'font':'belerenb','size':0.0324,
    })
    typ['text']=str(sem.get('printed_type_line') or typ.get('text') or '')
    rules.update({
        'name':'Rules Text','x':0.086,'y':0.7143,'width':0.828,
        'height':0.2048,'size':0.0362,
    })
    # Noncreature donors omit PT; every native text box still needs a string.
    pt.setdefault('text','')
    pt.update({
        'name':'Power/Toughness','x':0.7928,'y':0.902,'width':0.1367,
        'height':0.0372,'size':0.0372,'font':'belerenbsc',
        'oneLine':True,'align':'center',
    })

    short=token_has_short_text(sem)
    configure_token_style(data,code,style,short)
    fit_token_art(data,sem['art_local_path'],autofit)
    return base,data,('token_regular' if style=='token-full-art' and not short else style.replace('-','_')+('_short' if short else '_rules'))


def token_has_short_text(sem):
    # Only compact plain keywords qualify. Activated abilities, reminder text,
    # multiple lines and flavor always retain the larger rules area.
    rules=str(sem.get('oracle_text') or '').strip()
    return not sem.get('flavor_text') and len(rules)<=24 and not any(c in rules for c in '\n{}():')


def configure_token_style(data,code,style,short):
    classic=style=='token-classic'
    borderless=style=='token-borderless'
    large_art=short or borderless
    family='textless' if large_art else 'regular'
    frame=next(f for f in reversed(data['frames']) if str(f.get('src','')).startswith('/img/frames/token/'))
    if not classic and not large_art:frame['src']=_token_frame_src(code)
    pinline='/img/frames/token/tokenMaskRegularPinline.png'
    if classic:
        frame['src']=f'/img/frames/token/m15/{family}/{(code if code in "WUBRGMAL" else "A").lower()}.png'
        pinline=f'/img/frames/token/m15/{family}/pinline.svg'
    elif large_art:
        folder='textless-borderless' if borderless else 'textless'
        frame['src']=f'/img/frames/token/{folder}/'+('frameC.png' if code=='C' else f'tokenFrame{code}Textless.png')
        pinline='/img/frames/token/tokenMaskTextlessPinline.png'
    # These packs contain complete textured frames. Combining their editor
    # masks cuts out much of that texture; keep the whole image as the base.
    # Only multicolor tokens need a separate pinline layer for the shared dual
    # gradient treatment. It sits above the complete native multicolor frame.
    frame['masks']=[]
    if code=='M':
        data['frames'].insert(data['frames'].index(frame),{
            'name':'Token Pinline','src':frame['src'],
            'masks':[{'src':pinline,'name':'Pinline'}],
        })
    data['version']=('tokenTextlessM15' if large_art else 'tokenRegularM15') if classic else ('tokenTextlessBorderless' if borderless else 'tokenTextless' if large_art else 'tokenRegular')
    text=data['text']
    if large_art:
        text['type']['y']=0.8196
        data['setSymbolBounds']['y']=0.8439
        data['watermarkBounds']={'x':-1,'y':-1,'width':0.0007,'height':0.0005}
        text['rules'].update(x=0.086,y=0.875,width=0.65,height=0.043,size=0.026,oneLine=True,align='center')
        if borderless and not short:
            text['rules'].update(y=0.62,width=0.828,height=0.18,size=0.0324,oneLine=False,align='left')
    if classic:
        for field in text.values():
            field.update(color='black',outlineWidth=0,shadowX=0,shadowY=0)
        text['title']['color']='#fde367'
    else:apply_full_art_text(data)


def build_emblem_data(sem,artist,autofit,flags):
    """Build an emblem using CardConjurer's complete native Emblem frame."""
    # The preserved compiler has no Emblem recipe. Use an ordinary card only
    # for its shared metadata/text structures, then replace the whole frame and
    # every layout field that differs in CardConjurer's Emblem pack.
    donor=copy.deepcopy(sem)
    donor.update(types=['Enchantment'],subtypes=[],legendary=False,
                 colors=['W'],layout='card_noncreature')
    try:
        data=native.build_one(donor,{'artist':artist},False,flagged_sagas=flags)['data']
    except native.BuildError as exc:
        raise ValidationError(str(exc)) from exc
    data.update(version='emblem',
                frames=[{'name':'Emblem Frame','src':'/img/frames/token/emblem/frame.png','masks':[]}],
                artBounds={'x':0.142,'y':0.0496,'width':0.716,'height':0.8548},
                setSymbolBounds={'x':0.9213,'y':0.7043,'width':0.12,'height':0.041,
                                 'vertical':'center','horizontal':'right'},
                watermarkBounds={'x':0.5,'y':0.8177,'width':0.75,'height':0.1472})
    fields=data.setdefault('text',{})
    fields['mana'].update(text='',y=0.0613,width=0.9292,height=71/2100,
                          oneLine=True,size=71/1638,align='right',
                          shadowX=-0.001,shadowY=0.0029,manaCost=True,manaSpacing=0)
    fields['title'].update(text=sem['name'],x=0.0854,y=0.0522,width=0.8292,
                            height=0.0543,oneLine=True,font='belerenbsc',
                            size=0.0381,color='white',align='center')
    fields['type'].update(text=str(sem.get('printed_type_line') or 'Emblem'),
                           x=0.0854,y=0.68,width=0.8292,height=0.0543,
                           oneLine=True,font='belerenb',size=0.0324)
    fields['rules'].update(x=0.086,y=0.7443,width=0.828,height=0.1748,size=0.0362)
    fields.setdefault('pt',{}).update(text='',x=0.7928,y=0.902,width=0.1367,height=0.0372,
                         size=0.0372,font='belerenbsc',oneLine=True,align='center')
    if autofit:native.auto_fit(data,sem['art_local_path'])
    return sem,data,'emblem'


def build_art_series_data(sem,artist,flags,recipe='art_series_scan'):
    """Render an Art Series or helper face as its complete selected-printing scan."""
    donor=copy.deepcopy(sem)
    donor.update(types=['Enchantment'],subtypes=[],legendary=False,
                 colors=['W'],layout='card_noncreature')
    try:
        data=native.build_one(donor,{'artist':artist},False,flagged_sagas=flags)['data']
    except native.BuildError as exc:
        raise ValidationError(str(exc)) from exc
    # Keep a supported CardConjurer version and valid transparent symbol asset
    # for the renderer, but remove visible generated layers: the art asset
    # already contains the whole printed card.
    for field in data.get('text',{}).values():
        if isinstance(field,dict):field['text']=''
    for field in data.get('bottomInfo',{}).values():
        if isinstance(field,dict):field['text']=''
    data.update(frames=[],artBounds={'x':0,'y':0,'width':1,'height':1},
                setSymbolSource='/img/blank.png',setSymbolZoom=0,
                watermarkSource='/img/blank.png',watermarkOpacity=0,
                bottomInfoZoom=0,margins=False)
    native.auto_fit(data,sem['art_local_path'])
    return sem,data,recipe


def build_battle_data(sem,card,artist,autofit,flags):
    """Build CardConjurer's genuine landscape M15 Battle — Siege frame."""
    if 'Battle' not in set(sem.get('types',[])):
        raise ValidationError('Battle frame requested for a non-Battle face.')
    defense=str(sem.get('defense') or '').strip()
    if not defense:
        raise ValidationError('Battle cards need a defense value.')

    # Use an ordinary noncreature only as a metadata donor. Battle replaces the
    # complete structural frame, canvas orientation, text geometry and art well.
    base=copy.deepcopy(sem)
    base['types']=['Enchantment']
    base['subtypes']=[]
    base['legendary']=False
    base['layout']='card_noncreature'
    try:
        data=native.build_one(copy.deepcopy(base),{'artist':artist},False,flagged_sagas=flags)['data']
    except native.BuildError as exc:
        raise ValidationError(str(exc)) from exc

    code=_battle_frame_code(sem)
    # The Battle PNG is already the complete printed Invasion frame. Do not
    # mask it down to individual components and do not add the separate holo
    # sticker; both made the built-in frame appear incomplete.
    frames=[{
        'name':native.COLOR_NAMES.get(code,code)+' Battle Frame',
        'src':f'/img/frames/m15/battle/{code.lower()}.png',
        'masks':[],
    }]

    reverse_pt=''
    faces=card.get('card_faces') or []
    if len(faces)>1:
        power=faces[1].get('power')
        toughness=faces[1].get('toughness')
        if power is not None and toughness is not None:
            reverse_pt=f'{power}/{toughness}'

    rules=native.italicize_dash_labels(sem.get('oracle_text',''))
    if sem.get('flavor_text'):
        rules+=('{flavor}' if rules else '')+str(sem['flavor_text'])

    data.update({
        'width':2814,
        'height':2010,
        'landscape':True,
        'version':'battle',
        'frames':frames,
        'artBounds':copy.deepcopy(_BATTLE_ART_BOUNDS),
        'setSymbolBounds':copy.deepcopy(_BATTLE_SYMBOL_BOUNDS),
        'watermarkBounds':{'x':0,'y':0,'width':0,'height':0},
        'artX':0,'artY':0,'artZoom':1,'artRotate':0,
        'bottomInfoTranslate':{'x':-123,'y':-2814},
        'bottomInfoRotate':90,
        'bottomInfoZoom':1.4,
    })
    data['text']={
        'mana':{
            'name':'Mana Cost','text':sem.get('mana_cost',''),
            'x':0,'y':100/1500,'width':1957/2100,'height':71/1500,
            'oneLine':True,'size':((71/1638)*2100)/1500,'align':'right',
            'shadowX':-0.001,'shadowY':0.0029,'manaCost':True,'manaSpacing':0,
        },
        'title':{
            'name':'Title','text':sem['name'],
            'x':387/2100,'y':81/1500,'width':1547/2100,'height':114/1500,
            'oneLine':True,'font':'belerenb','size':(0.0381*2100)/1500,
        },
        'type':{
            'name':'Type',
            'text':native.get_type_info(sem)['normalized'].replace(' - ',' — '),
            'x':268/2100,'y':873/1500,'width':1667/2100,'height':114/1500,
            'oneLine':True,'font':'belerenb','size':(0.0324*2100)/1500,
        },
        'rules':{
            'name':'Rules Text','text':rules,
            'x':272/2100,'y':1008/1500,'width':1661/2100,'height':414/1500,
            'size':(0.0362*2100)/1500,
        },
        'reminder':{
            'name':'Reverse PT','text':reverse_pt,
            'x':257/2100,'y':1219/1500,'width':1667/2100,'height':43/1500,
            'size':(0.0291*2100)/1500,'oneLine':True,'color':'#666',
            'align':'right','font':'belerenbsc',
        },
        'defense':{
            'name':'Defense','text':defense,
            'x':1920/2100,'y':1320/1500,'width':86/2100,'height':123/1500,
            'size':(0.0372*2100)/1500,'color':'white','font':'belerenbsc',
            'oneLine':True,'align':'center',
        },
    }
    if autofit:native.auto_fit(data,sem['art_local_path'])
    return sem,data,'m15_battle'


_CLASS_FRAME_NAMES={'w':'White','u':'Blue','b':'Black','r':'Red','g':'Green','m':'Multicolored','a':'Artifact','l':'Land'}

# Class uses the same shared-font strategy as Saga: one font size for every
# ability text box, with the separators moving to give longer abilities more
# vertical room. CardConjurer's Class renderer reserves 0.0481 card-height for
# each level header/separator and hard-stops the final text box at y=0.8368.
_CLASS_TEXT_START_Y=0.1129
_CLASS_TEXT_END_Y=0.8368
_CLASS_SEPARATOR_HEIGHT=0.0481
_CLASS_FIRST_TEXT_TOP_INSET_PX=10
_CLASS_ABILITY_FONT_SIZE=0.0305
_CLASS_MIN_FONT_SIZE=0.024
_CLASS_FONT_STEP=0.0005


def _shared_class_text_layout(texts):
    """Balance Class separators so all ability text can share one font size."""
    if not texts:
        return {'heights':[],'size':_CLASS_ABILITY_FONT_SIZE,'required':[],'lines':[]}

    separator_px=max(0,len(texts)-1)*_CLASS_SEPARATOR_HEIGHT*native.CARD_HEIGHT
    available_total=int(round(
        (_CLASS_TEXT_END_Y-_CLASS_TEXT_START_Y)*native.CARD_HEIGHT-separator_px
    ))
    if available_total<=0:
        raise ValidationError('Class ability region has no usable text height.')

    size=_CLASS_ABILITY_FONT_SIZE
    while True:
        line_counts=[native.estimated_saga_wrapped_lines(text,size=size) for text in texts]
        heights=native.allocate_saga_heights(line_counts,available_total)
        required=[
            native.saga_required_height_px(lines,size)
            + (_CLASS_FIRST_TEXT_TOP_INSET_PX if i==0 else 0)
            for i,lines in enumerate(line_counts)
        ]
        if all(req<=height for req,height in zip(required,heights)) or size<=_CLASS_MIN_FONT_SIZE:
            return {'heights':heights,'size':size,'required':required,'lines':line_counts}
        size=max(_CLASS_MIN_FONT_SIZE,round(size-_CLASS_FONT_STEP,4))


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
    ability_texts=[base_text]+[level['text'] for level in levels]
    shared_layout=_shared_class_text_layout(ability_texts)
    heights_px=list(shared_layout['heights'])
    shared_size=float(shared_layout['size'])
    if len(heights_px)!=level_count:
        raise ValidationError('Class shared text layout returned the wrong number of ability boxes.')

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
        # Give the first ability 10 px more top breathing room without moving
        # its separator: move the text top down 10 px and remove the same 10 px
        # from that text box's height.
        'level0c':{
            'name':'1 - Text','text':base_text,'x':0.5093,
            'y':_CLASS_TEXT_START_Y+_CLASS_FIRST_TEXT_TOP_INSET_PX/native.CARD_HEIGHT,
            'width':0.404,
            'height':max(0,heights_px[0]-_CLASS_FIRST_TEXT_TOP_INSET_PX)/native.CARD_HEIGHT,
            'size':shared_size,
        },
    }
    # Separator positions use the full balanced allocation. The 10 px inset
    # above level0c therefore changes only its text padding, not the first
    # separator's intended balanced position.
    last_y=_CLASS_TEXT_START_Y+heights_px[0]/native.CARD_HEIGHT+_CLASS_SEPARATOR_HEIGHT
    for i in range(1,4):
        active=i<=len(levels)
        height=(heights_px[i]/native.CARD_HEIGHT) if active else 0
        y=last_y if active else 2
        info=levels[i-1] if active else {'cost':'','name':'','text':''}
        text[f'level{i}a']={'name':f'{i+1} - Cost','text':info['cost'],'x':0.5093,'y':y-0.0361 if active else 2,'width':0.3967,'height':0.0277,'size':0.0277}
        text[f'level{i}b']={'name':f'{i+1} - Name','text':info['name'],'x':0.5093,'y':y-0.0361 if active else 2,'width':0.3967,'height':0.0281,'size':0.0281,'align':'right'}
        text[f'level{i}c']={'name':f'{i+1} - Text','text':info['text'],'x':0.5093,'y':y,'width':0.404,'height':height,'size':shared_size}
        if active:last_y+=height+_CLASS_SEPARATOR_HEIGHT
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


_MODAL_FRAME_RE=re.compile(r'^(.*?/img/frames/modal/regular/(?:back/)?)([wubrgmalc])(\.png)$')
_MODAL_CROWN_RE=re.compile(r'^(.*?/img/frames/modal/crowns/regular/)([wubrgmalc])(\.png)$')
_M15_PT_RE=re.compile(r'^(.*?/img/frames/m15/regular/m15PT)([WUBRGMACV])(\.png)$')

def _modal_dfc_flipside_label(pair,index,face):
    """Return the approved printed helper-strip label for known modal DFC pairs."""
    if pair==('Esika, God of the Tree','The Prismatic Bridge'):
        # Front previews the back's card type; back previews Esika's God subtype.
        if index==0:
            info=ingest.split_type_line(str(face.get('type_line') or ''))
            return ' '.join(info.get('types') or [])
        return 'God'
    if pair==('Bruce Banner','The Incredible Hulk'):
        # The printed Marvel treatment uses P/T + Creature on both sides.
        power=str(face.get('power') or '').strip()
        toughness=str(face.get('toughness') or '').strip()
        if power and toughness:
            return power+'/'+toughness+' Creature'
        return 'Creature'
    raise ValidationError('This modal DFC needs a compatible custom template.')

def _fit_modal_flipside_label_width(data,mana_cost):
    """Reserve helper-strip space for the opposite face's rendered mana cluster."""
    text=data.get('text') or {};label=text.get('flipsideType');reminder=text.get('flipSideReminder')
    if not isinstance(label,dict) or not isinstance(reminder,dict):return False
    tokens=_MODAL_MANA_TOKEN_RE.findall(str(mana_cost or ''))
    if not tokens:return False
    try:
        left=float(label.get('x') or 0);original_width=float(label.get('width') or 0)
        reminder_x=float(reminder.get('x') or 0);reminder_width=float(reminder.get('width') or 0)
        size=float(reminder.get('size') or label.get('size') or .03)
        card_w=float(data.get('width') or native.CARD_WIDTH);card_h=float(data.get('height') or native.CARD_HEIGHT)
    except (TypeError,ValueError,ZeroDivisionError):return False
    if min(original_width,size,card_w,card_h)<=0:return False
    symbol_width=size*card_h/card_w
    reserved=len(tokens)*symbol_width
    gap=max(.006,symbol_width*.18)
    strip_right=max(left+original_width,reminder_x+reminder_width)
    label['width']=max(.03,min(original_width,strip_right-left-reserved-gap))
    return True

def apply_approved_modal_dfc_semantics(data,sem,sf,index):
    """Retarget the Esika-seeded modal frame to an approved pair's real faces.

    The preserved vendor template contains Esika-specific G/M frame sources and
    hardcoded opposite-face reminder text. Keep its geometry, masks and typography,
    but derive visible colors and reminder content from the actual modal DFC.
    """
    faces=sf.get('card_faces') or []
    if len(faces)!=2 or index not in {0,1}:
        raise ValidationError('Approved modal DFC support requires exactly two faces.')
    pair=tuple(str(face.get('name') or '') for face in faces)
    if pair not in APPROVED_MODAL_DFC_PAIRS:
        raise ValidationError('This modal DFC needs a compatible custom template.')

    other_index=1-index
    other=faces[other_index]
    other_sem=semantic(sf,other,other_index)
    current_code=frame_treatment_code(sem)
    other_code=frame_treatment_code(other_sem)
    if current_code not in {'W','U','B','R','G','M'} or other_code not in {'W','U','B','R','G','M'}:
        raise ValidationError('This approved modal DFC resolves to an unsupported frame color.')

    for frame in data.get('frames',[]):
        if not isinstance(frame,dict):continue
        src=str(frame.get('src') or '')
        masks={
            str(mask.get('name') or '')
            for mask in frame.get('masks',[])
            if isinstance(mask,dict)
        }

        crown=_MODAL_CROWN_RE.fullmatch(src)
        if crown:
            frame['src']=crown.group(1)+current_code.lower()+crown.group(3)
            continue

        modal=_MODAL_FRAME_RE.fullmatch(src)
        if modal:
            code=other_code if 'Flipside' in masks else current_code
            frame['src']=modal.group(1)+code.lower()+modal.group(3)
            continue

        pt=_M15_PT_RE.fullmatch(src)
        if pt and 'Creature' in set(sem.get('types',[])):
            frame['src']=pt.group(1)+current_code+pt.group(3)

    text=data.setdefault('text',{})
    mana_cost=str(other.get('mana_cost') or '')
    if isinstance(text.get('flipsideType'),dict):
        text['flipsideType']['text']=_modal_dfc_flipside_label(pair,index,other)
    if isinstance(text.get('flipSideReminder'),dict):
        text['flipSideReminder']['text']=mana_cost
    _fit_modal_flipside_label_width(data,mana_cost)
    return True



_NICKNAME_TITLE_BOUNDS={'x':0.0494,'y':0.0405,'width':0.9014,'height':0.1053}
_NICKNAME_CROWN_BOUNDS={'x':0.024,'y':0.0172,'width':0.952,'height':0.1286}
_NICKNAME_PT_BOUNDS={'x':0.7573,'y':0.8848,'width':0.188,'height':0.0733}
_NICKNAME_ART_BOUNDS={'x':0,'y':0,'width':1,'height':0.9224}
_NICKNAME_SYMBOL_BOUNDS={'x':0.9213,'y':0.591,'width':0.12,'height':0.041,'vertical':'center','horizontal':'right'}
_NICKNAME_WATERMARK_BOUNDS={'x':0.5,'y':0.7762,'width':0.75,'height':0.2305}

def _nickname_code(sem):
    code=frame_treatment_code(sem)
    if code and code in 'WUBRGMAL':return code
    return 'C'

def _nickname_title_src(code,complete=False):
    if code=='C':
        return ('/img/frames/m15/nickname/m15NicknameTitleA.png' if complete
                else '/img/frames/m15/nickname/addons/m15NicknameTitleC.png')
    return f'/img/frames/m15/nickname/m15NicknameTitle{code}.png'

def _nickname_crown_src(code,complete=False):
    if code=='C':
        return ('/img/frames/m15/nickname/m15NicknameCrownA.png' if complete
                else '/img/frames/m15/nickname/smooth/c.png')
    return f'/img/frames/m15/nickname/m15NicknameCrown{code}.png'

def _nickname_frame_src(code):
    # The pinned pack has no C body image. Its complete neutral A body pairs
    # with the genuine colorless title and P/T addon.
    return f'/img/frames/m15/nickname/m15NicknameFrame{code if code in "WUBRGMAL" else "A"}.png'

def _nickname_pt_src(code):
    return f'/img/frames/m15/nickname/m15NicknamePT{code if code in "WUBRGMAC" else "C"}.png'

def _nickname_text(data,sem,group,force=False):
    text=data.setdefault('text',{})
    true_name=str(sem.get('name') or '')
    nickname=str(sem.get('nickname') or '').strip()
    if force and not nickname:nickname=true_name
    if not nickname:return False

    if group=='battle':
        # Battle is compiled directly onto a landscape canvas. Keep its native
        # Battle frame, and use the same landscape title axis for both names.
        old=text.get('title') if isinstance(text.get('title'),dict) else {}
        text['nickname']={
            'name':'Nickname','text':nickname,
            'x':old.get('x',387/2100),'y':old.get('y',81/1500),
            'width':old.get('width',1547/2100),'height':old.get('height',114/1500),
            'oneLine':True,'font':'belerenb','size':old.get('size',(0.0381*2100)/1500),
        }
        text['title']={
            'name':'Title','text':true_name,
            'x':387/2100,'y':155/1500,'width':1547/2100,'height':50/1500,
            'oneLine':True,'font':'mplantini','size':(0.0229*2100)/1500,
            'color':'white','align':'center',
        }
        return True

    # Standard portrait nickname typography. Special card families keep all of
    # their own type/rules/chapter/loyalty/helper-strip geometry.
    nickname_x=.0854;nickname_w=.8292
    if group=='transform-front' or group in {'modal-front','modal-back'}:
        nickname_x=.1614;nickname_w=.7534
    elif group=='planeswalker':
        nickname_x=.0867;nickname_w=.8267
    nickname_y=.0372 if group=='planeswalker' else .0522
    title_y=.1015 if group=='planeswalker' else .1129
    text['nickname']={
        'name':'Nickname','text':nickname,'x':nickname_x,'y':nickname_y,
        'width':nickname_w,'height':.0548 if group=='planeswalker' else .0543,
        'oneLine':True,'font':'belerenb','size':.0381,'color':'white',
        'shadowX':.0014,'shadowY':.001,
    }
    text['title']={
        'name':'Title','text':true_name if nickname!=true_name else '', 'x':.14,'y':title_y,'width':.72,'height':.0243,
        'oneLine':True,'font':'mplantini','size':.0229,'color':'white',
        'shadowX':.0014,'shadowY':.001,'align':'center',
    }
    return True


def _apply_full_m15_nickname_pack(data,sem,refit=False):
    """Replace the current structural frame with CardConjurer's M15Nickname pack.

    The pack has complete W/U/B/R/G/M/A/L frames. Colorless uses its
    neutral A body and title because the pinned pack has no C body.
    It is deliberately mask-free here: one full Frame plus Title/Crown and P/T.
    """
    code=_nickname_code(sem)
    frame_src=_nickname_frame_src(code)
    if not frame_src:return False

    color_name=native.COLOR_NAMES.get(code,code)
    legendary=bool(sem.get('legendary'))
    pt_text=str((((data.get('text') or {}).get('pt') or {}).get('text') or '')).strip()

    frames=[
        {'name':f'{color_name} Frame','src':frame_src,'masks':[]},
    ]
    if legendary:
        frames.append({
            'name':f'{color_name} Crown','src':_nickname_crown_src(code,True),
            'masks':[],'bounds':copy.deepcopy(_NICKNAME_CROWN_BOUNDS),
        })
    else:
        frames.append({
            'name':f'{color_name} Title','src':_nickname_title_src(code,True),
            'masks':[],'bounds':copy.deepcopy(_NICKNAME_TITLE_BOUNDS),
        })
    if pt_text:
        frames.append({
            'name':f'{color_name} Power/Toughness','src':_nickname_pt_src(code),
            'masks':[],'bounds':copy.deepcopy(_NICKNAME_PT_BOUNDS),
        })

    data['frames']=frames
    data['version']='m15Nickname'
    data['artBounds']=copy.deepcopy(_NICKNAME_ART_BOUNDS)
    data['setSymbolBounds']=copy.deepcopy(_NICKNAME_SYMBOL_BOUNDS)
    data['watermarkBounds']=copy.deepcopy(_NICKNAME_WATERMARK_BOUNDS)

    text=data.setdefault('text',{})
    mana=text.setdefault('mana',{})
    nickname=text.setdefault('nickname',{})
    title=text.setdefault('title',{})
    typ=text.setdefault('type',{})
    rules=text.setdefault('rules',{})
    pt=text.setdefault('pt',{})
    if 'text' not in typ:
        typ['text']=native.get_type_info(sem)['normalized']
    if 'text' not in rules:
        rules['text']=native.italicize_dash_labels(sem.get('oracle_text',''))+('{flavor}'+sem['flavor_text'] if sem.get('flavor_text') else '')
    rules.setdefault('font','mplantin')

    mana.update({
        'name':'Mana Cost','text':str(sem.get('mana_cost') or ''),'y':.0613,'width':.9292,'height':71/2100,
        'oneLine':True,'size':71/1638,'align':'right','shadowX':-.001,
        'shadowY':.0029,'manaCost':True,'manaSpacing':0,
    })
    nickname.update({
        'name':'Nickname','text':str(sem.get('nickname') or '').strip(),
        'x':.0854,'y':.0522,'width':.8292,'height':.0543,
        'oneLine':True,'font':'belerenb','size':.0381,'color':'white',
        'shadowX':.0014,'shadowY':.001,
    })
    title.update({
        'name':'Title','text':str(sem.get('name') or ''),
        'x':.14,'y':.1129,'width':.72,'height':.0243,
        'oneLine':True,'font':'mplantini','size':.0229,'color':'white',
        'shadowX':.0014,'shadowY':.001,'align':'center',
    })
    typ.update({
        'name':'Type','x':.0854,'y':.5664,'width':.8292,'height':.0543,
        'oneLine':True,'font':'belerenb','size':.0324,'color':'white',
        'shadowX':.0014,'shadowY':.001,
    })
    rules.update({
        'name':'Rules Text','x':.086,'y':.6303,'width':.828,'height':.2875,
        'size':.0362,'color':'white','shadowX':.0014,'shadowY':.001,
    })
    pt.update({
        'name':'Power/Toughness','text':pt_text,'x':.7928,'y':.902,'width':.1367,
        'height':.0372,'size':.0372,'font':'belerenbsc',
        'oneLine':True,'align':'center','color':'white',
    })

    if refit:native.auto_fit(data,sem['art_local_path'])
    return True


def _force_token_text_white(data):
    """Token nickname fallback must remain legible over the dark token boxes."""
    text=data.get('text') or {}
    for key in ('nickname','title','type','rules','pt'):
        field=text.get(key)
        if isinstance(field,dict):field['color']='white'


def _apply_planeswalker_nickname_frame(data):
    changed=False
    for frame in data.get('frames',[]):
        if not isinstance(frame,dict):continue
        src=str(frame.get('src') or '')
        m=re.fullmatch(r'/img/frames/planeswalker/regular/planeswalkerFrame([WUBRGMA])\.png',src)
        if not m:continue
        frame['src']=f'/img/frames/planeswalker/nickname/planeswalkerNicknameFrame{m.group(1)}.png'
        changed=True
    if changed:data['version']='planeswalkerNickname'
    return changed

def _apply_modal_nickname_frame(data):
    changed=False
    for frame in data.get('frames',[]):
        if not isinstance(frame,dict):continue
        src=str(frame.get('src') or '')
        m=re.fullmatch(r'/img/frames/modal/regular/(back/)?([wubrgma])\.png',src)
        if not m:continue
        side='b' if m.group(1) else 'f'
        frame['src']=f'/img/frames/modal/nickname/{m.group(2)}{side}.png'
        changed=True
    if changed:data['version']='modalNickname'
    return changed


def apply_full_art_text(data):
    """Use the native text renderer's white fill and black stroke on art."""
    for key in ('title','nickname','type','rules','flavor','pt'):
        field=(data.get('text') or {}).get(key)
        if isinstance(field,dict):
            field['color']='white'
            field['outlineColor']='black'
            field['outlineWidth']=.0035


def reserve_nickname_mana_space(data,sem):
    """Keep the alternate title out of the right-aligned mana symbols."""
    symbols=len(re.findall(r'\{[^{}]+\}',str(sem.get('mana_cost') or '')))
    if not symbols:return
    nickname=(data.get('text') or {}).get('nickname')
    if not isinstance(nickname,dict):return
    left=float(nickname.get('x',0.0854))
    right=min(left+float(nickname.get('width',0.8292)),0.93-(0.034+0.052*symbols))
    nickname['width']=max(0.25,right-left)


def apply_nickname_treatment(data,sem,group,refit=False,*,force=False,full_frame=False):
    """Apply complete nickname frames where supported, preserving special layouts."""
    nickname=str(sem.get('nickname') or '').strip()
    if not nickname and not force:return False
    effective_sem=sem
    if force and not nickname:
        effective_sem={**sem,'nickname':str(sem.get('name') or '')}
    # A nickname alone adds the two-name treatment to the chosen ordinary
    # frame. Only the explicit Godzilla choice replaces that frame outright.
    # Tokens retain their complete nickname pack because their native frame
    # needs the matching full title/body assets.
    if full_frame or group=='token':
        if _apply_full_m15_nickname_pack(data,effective_sem,refit):
            if force and not nickname:(data.get('text') or {}).get('title',{})['text']=''
            return True
    if not _nickname_text(data,effective_sem,group):return False
    if group=='token':_force_token_text_white(data)

    # Battle has no rotatable nickname frame asset in CardConjurer. Its native
    # Battle frame stays intact; only the two-name text treatment is applied.
    if group=='battle':return True

    # These two structural families have real CardConjurer nickname packs.
    if group=='planeswalker' and _apply_planeswalker_nickname_frame(data):
        return True
    if group in {'modal-front','modal-back'} and _apply_modal_nickname_frame(data):
        return True

    code=_nickname_code(sem)
    legendary=bool(sem.get('legendary'))
    frames=data.setdefault('frames',[])
    if legendary:
        frames.append({
            'name':'Nickname Crown','src':_nickname_crown_src(code),
            'masks':[],'bounds':copy.deepcopy(_NICKNAME_CROWN_BOUNDS)
            if code!='C' else {'x':0,'y':0,'width':1,'height':1},
        })
    else:
        frames.append({
            'name':'Nickname Title','src':_nickname_title_src(code),
            'masks':[],'bounds':copy.deepcopy(_NICKNAME_TITLE_BOUNDS),
        })
    return True


def custom_data(template,sem,other_faces=None):
    d=copy.deepcopy(template['data'])
    if template.get('schemaVersion')==2:
        try:
            reference=native.build_one(copy.deepcopy(choose_builtin(sem,'auto')),
                                       {'artist':sem.get('artist','')},False)['data']
        except native.BuildError as exc:
            raise ValidationError('This card needs a structural template with its own dynamic regions.') from exc
        apply_regions(d,reference,template['regions'])
    values={'title':sem['name'],'type':native.get_type_info(sem)['normalized'],'mana':sem.get('mana_cost',''),
      'rules':native.italicize_dash_labels(sem.get('oracle_text',''))+('{flavor}'+sem['flavor_text'] if sem.get('flavor_text') else ''),
      'flavor':sem.get('flavor_text',''),'pt':str(sem['power'])+'/'+str(sem['toughness']) if sem.get('power') is not None and sem.get('toughness') is not None else '',
      'loyalty':sem.get('loyalty',''),'defense':sem.get('defense','')}
    for i,line in enumerate(sem.get('oracle_text','').splitlines(),1):values['line'+str(i)]=line
    mapping=({slot:region['field'] for slot,region in template['regions'].items()}
             if template.get('schemaVersion')==2 else (template.get('mapping') or {k:k for k in values}))
    for slot,field in mapping.items():
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
        fingerprint=stable_hash({'data':t.get('data'),'mapping':t.get('mapping',{}),'regions':t.get('regions',{}),
                                 'schemaVersion':t.get('schemaVersion',1),'baseGroup':t.get('baseGroup'),
                                 'groups':t.get('groups',[]),'legendary':bool(t.get('legendary'))})
        return 'custom:'+choice,fingerprint,1
    def compile_face(self,sf,face,index,options,settings,art_id,*,art_origin='custom artwork'):
        sem=semantic(sf,face,index)
        for k in ('nickname','flavor_text','rarity','oracle_text','mana_cost','power','toughness','loyalty','defense'):
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
            builtin=next(x for x in BUILTINS if x['id']==choice)
            if choice!='auto' and builtin['groups']!='ordinary' and group not in builtin['groups']:
                raise ValidationError('This template does not support '+group+'.')
            if group not in ORDINARY_GROUPS and choice not in {'auto','godzilla-card','token-classic','token-full-art','token-borderless'}:
                raise ValidationError('Choose automatic or a custom template for '+group+'.')
            if choice=='godzilla-card' and group!='token' and 'Land' in sem.get('types',[]):
                raise ValidationError('Choose the Godzilla land template for lands.')
            if choice=='godzilla-land' and 'Land' not in sem.get('types',[]):
                raise ValidationError('Choose the Godzilla non-land template for this card.')
            if group in NEEDS_CUSTOM:raise ValidationError('Recognized '+group+' needs a compatible custom template; no incorrect frame will be substituted.')
            if group in {'modal-front','modal-back'}:
                pair=tuple(x.get('name') for x in sf.get('card_faces',[]))
                if pair not in APPROVED_MODAL_DFC_PAIRS:
                    approved='; '.join(' / '.join(x) for x in sorted(APPROVED_MODAL_DFC_PAIRS))
                    raise ValidationError('This modal DFC needs a compatible custom template. Approved built-in pairs: '+approved+'.')
            if group in {'transform-front','transform-back'}:
                d0,data,recipe=build_transform_data(sem,group,sf,artist,not settings.get('disableAutofit',False),flags)
                fit_set_symbol_to_bounds(data,self.store.asset(symbol_id),recipe)
            elif group=='battle':
                d0,data,recipe=build_battle_data(sem,sf,artist,not settings.get('disableAutofit',False),flags)
                fit_set_symbol_to_bounds(data,self.store.asset(symbol_id),recipe)
            elif group=='station' and 'Land' in sem.get('types',[]):
                d0,data,recipe=build_station_land_data(sem,artist,not settings.get('disableAutofit',False),flags,art_origin)
                fit_set_symbol_to_bounds(data,self.store.asset(symbol_id),recipe)
            elif group=='token':
                d0,data,recipe=build_token_data(sem,artist,not settings.get('disableAutofit',False),flags,choice if choice.startswith('token-') else 'token-classic')
                fit_set_symbol_to_bounds(data,self.store.asset(symbol_id),recipe)
            elif group=='emblem':
                d0,data,recipe=build_emblem_data(sem,artist,not settings.get('disableAutofit',False),flags)
                fit_set_symbol_to_bounds(data,self.store.asset(symbol_id),recipe)
            elif group in {'art-series','helper'}:
                d0,data,recipe=build_art_series_data(sem,artist,flags,'helper_scan' if group=='helper' else 'art_series_scan')
            elif group=='meld':
                d0,data,recipe=build_meld_data(sem,sf,artist,not settings.get('disableAutofit',False),flags)
                fit_set_symbol_to_bounds(data,self.store.asset(symbol_id),recipe)
            elif group=='class':
                d0,data,recipe=build_class_data(sem,artist,not settings.get('disableAutofit',False),flags)
                fit_set_symbol_to_bounds(data,self.store.asset(symbol_id),recipe)
            elif choice=='auto' and group in {'land','legendary-land','basic-land'} and 'Land' in sem.get('types',[]) and 'Enchantment' in sem.get('types',[]):
                d0,data,recipe=build_enchantment_land_data(sem,artist,not settings.get('disableAutofit',False),flags)
                fit_set_symbol_to_bounds(data,self.store.asset(symbol_id),recipe)
            else:
                d0=choose_builtin(sem,'auto' if choice.startswith('godzilla-') else choice)
                # Saga is the highest-priority structural card treatment. Do not
                # let another type on the same line (notably Land on Urza's Saga)
                # win inside the preserved native recipe classifier.
                if choice=='auto' and group in {'saga','saga-creature'}:
                    d0=copy.deepcopy(d0)
                    d0['layout']='saga' if group=='saga' else 'saga_creature'
                try:
                    data=native.build_one(copy.deepcopy(d0),{'artist':artist},not settings.get('disableAutofit',False),flagged_sagas=flags)['data']
                    if group in {'standard','legendary'} and choice=='auto':
                        if sem.get('devoid'):apply_devoid_frame(data,sem)
                        apply_miracle_frame(data,sem)
                    if choice=='legend-land' and not sem['legendary']:native.remove_crown(data)
                    if d0.get('_neutral_classic'):native.recolor_m15(data,'L')
                    recipe=native.infer_layout(d0,native.get_type_info(d0))
                    if choice=='auto' and group in {'modal-front','modal-back'}:
                        apply_approved_modal_dfc_semantics(data,sem,sf,index)
                    if choice=='auto' and group=='saga-creature':
                        enforce_saga_creature_rules_frame(data,sem)
                    if choice=='auto' and group in {'saga','saga-creature'}:
                        apply_dual_saga_tassels(data,sem,group)
                    if choice=='auto' and group=='station':
                        apply_station_underframe_policy(data,sem,art_origin)
                    if choice=='auto' and group=='prepare':
                        apply_prepare_frame_color(data,sem)
                    fit_set_symbol_to_bounds(data,self.store.asset(symbol_id),recipe)
                except native.BuildError as e:raise ValidationError(str(e)) from e
        else:
            t=self.store.get('templates',choice)
            if not t:raise ValidationError('The selected template was deleted.')
            if group not in t.get('groups',[]):raise ValidationError('The template is not approved for '+group+'.')
            if sem['legendary'] and not t.get('legendary',False):raise ValidationError('This template does not support legendary cards.')
            if sem.get('power') is not None and not ('pt' in t['data']['text'] or 'pt' in (t.get('mapping') or {}).values()):raise ValidationError('A creature template needs a P/T text slot.')
            data=custom_data(t,sem,sf.get('card_faces',[])[1:]);data.update(artSource=sem['art'],setSymbolSource=sem['set_symbol_source'],infoArtist=str(artist))
            if t.get('schemaVersion')==2:fit_set_symbol_to_bounds(data,self.store.asset(symbol_id),'custom')
            if not settings.get('disableAutofit',False):native.auto_fit(data,sem['art_local_path'])
            recipe='custom:'+choice
        source_aware_placement=None
        if choice=='auto':
            source_aware_placement=apply_source_aware_art_placement(
                data,art,sem,recipe,group,art_origin,
                not settings.get('disableAutofit',False),
                raw_card=bool(options.get('rawCard')),
            )

        short_saga_cover_fit=(
            choice=='auto'
            and not settings.get('disableAutofit',False)
            and _short_saga_creature_needs_cover_fit(sem)
            and not options.get('rawCard')
        )
        if short_saga_cover_fit:
            apply_short_saga_creature_art_fit(data,art,art_origin)
        for k in ('artX','artY','artZoom','artRotate'):
            if k in options.get('fit',{}):
                v=float(options['fit'][k])
                if not math.isfinite(v) or (k=='artZoom' and v<=0):raise ValidationError('Invalid artwork placement.')
                data[k]=v
        if options.get('rawCard'):
            data=copy.deepcopy(options['rawCard']);data['artSource']=sem['art'];data['setSymbolSource']=sem['set_symbol_source'];data['infoArtist']=str(artist)
        apply_universal_frame_color_treatment(data,sem)
        nickname_applied=False
        if choice.startswith('godzilla-'):
            nickname_applied=apply_nickname_treatment(data,sem,group,force=True,full_frame=True)
            data.update(full_art_nonland_placement(art))
            for key in ('artX','artY','artZoom','artRotate'):
                if key in options.get('fit',{}):data[key]=float(options['fit'][key])
            apply_full_art_text(data)
        elif recipe not in {'art_series_scan','helper_scan'}:
            nickname_applied=apply_nickname_treatment(
                data,sem,group,
                refit=bool(not settings.get('disableAutofit',False) and not options.get('fit') and not options.get('rawCard')),
            )
            if choice in {'land','legend-land'}:apply_full_art_text(data)
            if group=='token' and data.get('version') not in {'tokenRegularM15','tokenTextlessM15'}:apply_full_art_text(data)
        if nickname_applied and group in ORDINARY_GROUPS:
            reserve_nickname_mana_space(data,sem)
        if nickname_applied and data.get('version')=='m15Nickname':
            # Nickname frames move the type bar, so refit the set symbol.
            fit_set_symbol_to_bounds(data,self.store.asset(symbol_id),'m15_nickname')
        if recipe in {'art_series_scan','helper_scan'}:
            data['infoArtist']=''
            data['infoNote']=''
        else:
            data['infoArtist']=str(artist)
            data['infoNote']=CARD_FOOTER_NOTE
            bottom_info=data.get('bottomInfo') or {}
            if isinstance(bottom_info.get('bottomLeft'),dict):bottom_info['bottomLeft']['text']=CARD_FOOTER_NOTE
        data['artSource']='/api/assets/'+art_id
        data['setSymbolSource']='/img/blank.png' if recipe in {'art_series_scan','helper_scan'} else '/api/assets/'+symbol_id
        key=render_key(data,art_id,template_cache_version);warning=crop_metrics(art['width'],art['height'],data)
        if (
            short_saga_cover_fit
            and art_origin=='Scryfall selected printing'
            and not options.get('fit')
        ):
            # The selected-printing art is intentionally trimmed/fitted for the
            # printed short Saga-creature window. Custom art never receives this
            # exemption.
            warning={**warning,'warning':False,'scryfallShortSagaFit':True}
        elif (
            source_aware_placement
            and source_aware_placement.get('mode')=='art-window'
            and source_aware_placement.get('suppressCropWarning')
            and not options.get('fit')
        ):
            warning={**warning,'warning':False,'intentionalArtWindow':True}
        return {'name':sem['name'],'data':data,'renderKey':key,'render':self.store.render_get(key),'group':group,'recipe':recipe,'crop':warning,'flags':flags,'artId':art_id,'symbolId':symbol_id,'artist':str(artist),'credit':credit,'generationVersion':PIPELINE_VERSION,'templateKey':template_key,'templateVersion':template_version,'templateCacheVersion':template_cache_version}
