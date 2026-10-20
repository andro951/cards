"""Extend the native nickname frame by repeating its straight rules-box middle."""
import io
import xml.etree.ElementTree as ET
from PIL import Image,ImageChops,ImageFilter

PREFIX='/img/frames/proxy-foundry/planeswalker/'
TALL_VERSION='repeat-middle-v1'
PINLINE_VERSION='nickname-pinline-v1'
CLASSIC_PINLINE_VERSION='badge-cutout-v1'
TALL_EXTRA=147
TALL_SHIFT=TALL_EXTRA/2100
SPLICE_Y=1550
MOVE_START=900
MIN_BADGE_GAP=.008


def badge_extents(cost):
    """Native image bounds relative to the ability row center, including shadows."""
    if '+' in cost:return (-.0343,.0381)
    if '-' in cost or '−' in cost:return (-.0238,.0467)
    return (-.0238,.0372)


def badge_bases(version,count):
    tall=version!='planeswalkerNicknameTall' and any(v in version for v in ('Tall','Compleated'))
    return ({1:[.72],2:[.6391,.801],3:[.5986,.72,.8415],4:[.5986,.6796,.7605,.8415]} if tall else
            {1:[.7467],2:[.6953,.822],3:[.6639,.7467,.8362],4:[.6505,.72,.7905,.861]})[count]


def has_touching_ability_badges(data):
    """Refresh only cached native layouts whose fixed-size badges lack clearance."""
    walker=data.get('planeswalker') or {}
    if not walker.get('uniformAbilityText'):return False
    count=walker.get('count',0)
    if count not in (1,2,3,4):return False
    bases=badge_bases(data.get('version',''),count)
    previous_bottom=None
    for index,cost in enumerate(walker.get('abilities',[])[:count]):
        if not cost:continue
        center=bases[index]+walker.get('abilityAdjust',[0]*4)[index]+.0085
        top,bottom=badge_extents(cost)
        if previous_bottom is not None and center+top-previous_bottom<MIN_BADGE_GAP-1e-9:return True
        previous_bottom=center+bottom
    return False


def pinline_without_loyalty_png(pinline_raw,loyalty_raw):
    with Image.open(io.BytesIO(pinline_raw)) as source:
        pinline=source.convert('RGBA')
    with Image.open(io.BytesIO(loyalty_raw)) as source:
        badge=source.convert('RGBA').getchannel('A').resize(pinline.size,Image.Resampling.LANCZOS)
    badge=badge.point(lambda a:255 if a else 0).filter(ImageFilter.MaxFilter(3))
    pinline.putalpha(ImageChops.multiply(pinline.getchannel('A'),ImageChops.invert(badge)))
    out=io.BytesIO();pinline.save(out,'PNG');return out.getvalue()


def fit_ability_rows(abilities,bounds):
    """Fit one to four abilities into normalized card-space text bounds.

    Bounds include the passive row's extra left margin. Cost-bearing rows
    reserve that margin for the native badges. No frame or color is involved.
    The browser subsequently verifies this estimate using actual font metrics.
    """
    from .legacy import compiler as native
    from .domain import ValidationError
    if not 1<=len(abilities)<=4:
        raise ValidationError('Planeswalker frames support one to four ability rows.')
    if bounds['width']<=.044 or bounds['height']<=0:
        raise ValidationError('The planeswalker rules box has no usable text area.')
    gutter=.044
    for step in range(35,17,-1):
        size=step/1000
        heights=[.009+size*1.12*native.approx_tall_pw_wrapped_lines(
            text,passive=not cost,font_size=size*(.7467 if cost else .7907)/(bounds['width']-(gutter if cost else 0)))
            for cost,text in abilities]
        # Keep the first cost badge clear of the type bar.
        if abilities[0][0]:heights[0]=max(.088,heights[0])
        if sum(heights)>bounds['height']:continue
        spare=(bounds['height']-sum(heights))/len(abilities)
        candidate=[height+spare for height in heights]
        costs=[i for i,(cost,_) in enumerate(abilities) if cost]
        # Preserve existing layouts when their equal-share padding is sufficient.
        if all((candidate[a]+candidate[b])/2+sum(candidate[a+1:b])>=
               badge_extents(abilities[a][0])[1]-badge_extents(abilities[b][0])[0]+MIN_BADGE_GAP
               for a,b in zip(costs,costs[1:])):break
        # Adjacent centers depend on half of each end row's height. Reserve
        # their actual asymmetric image extents, rather than treating a short
        # ability as permission to stack fixed-size badges on top of each other.
        for a,b in zip(costs,costs[1:]):
            distance=badge_extents(abilities[a][0])[1]-badge_extents(abilities[b][0])[0]+MIN_BADGE_GAP
            required=2*(distance-sum(heights[a+1:b]))
            if heights[a]+heights[b]>=required:continue
            #Grow the shorter row first, then both equally. A short ability
            #should not receive a huge empty band just to space its neighbors.
            smaller,larger=sorted((a,b),key=lambda i:heights[i])
            heights[smaller]=max(heights[smaller],required-max(heights[larger],required/2))
            heights[larger]=max(heights[larger],required/2)
        if sum(heights)<=bounds['height']:break
    else:raise ValidationError('Planeswalker abilities do not fit the rules box.')
    spare=(bounds['height']-sum(heights))/len(abilities)
    y=bounds['y'];rows=[]
    for (cost,_),height in zip(abilities,heights):
        height+=spare
        rows.append({'x':bounds['x']+(gutter if cost else 0),'y':y,
                     'width':bounds['width']-(gutter if cost else 0),
                     'height':height,'size':size,'fontSize':0,'noVerticalCenter':False})
        y+=height
    return rows


def layout_planeswalker_abilities(data,sem,bounds=None):
    """Apply shared text/row/badge layout, optionally with explicit safe bounds."""
    from .legacy import compiler as native
    abilities=native.parse_planeswalker_abilities(sem.get('oracle_text',''))
    # Frame-specific geometry ends here. Leave clearance below the type bar
    # and above the bottom curve/starting-loyalty badge on each frame.
    if bounds is None:
        type_box=data['text']['type']
        start=type_box['y']+type_box['height']+.0217
        bounds={'x':.136,'y':start,'width':.764,'height':.891-start}
    rows=fit_ability_rows(abilities,bounds)
    # The pinned renderer has two native anchor tables. These offsets only
    # translate our calculated row centers into its badge coordinates.
    bases=badge_bases(data['version'],len(abilities))
    adjustments=[]
    for index in range(4):
        active=index<len(abilities)
        cost,oracle=abilities[index] if active else ('','')
        row=rows[index] if active else {**rows[-1],'y':bounds['y']+bounds['height'],'height':0}
        data['text'].setdefault(f'ability{index}',{}).update(
            name=f'Ability {index+1}',text=native.italicize_dash_labels(oracle),font='mplantin',**row)
        adjustments.append(row['y']+row['height']/2-native.PLANESWALKER_TALL_4_ICON_TEXT_CENTER_OFFSET-bases[index] if cost else 0)
    data.setdefault('planeswalker',{}).update(
        abilities=[c for c,_ in abilities]+['']*(4-len(abilities)),abilityAdjust=adjustments,
        count=len(abilities),x=.1167,width=.8094,
        orig_ability_textbox_x=bounds['x']+.044,orig_ability_textbox_width=bounds['width']-.044,
        uniformAbilityText=True)


def nickname_pinline_png(frame_raw,pinline_raw,loyalty_raw):
    def alpha(raw,resize=False):
        with Image.open(io.BytesIO(raw)) as image:
            if resize and image.size==(2010,2814):image=image.resize((1500,2100),Image.Resampling.LANCZOS)
            if image.size!=(1500,2100):raise ValueError('Unexpected native planeswalker mask dimensions.')
            return image.convert('RGBA').getchannel('A')
    #The regular mask has art-window rails absent from this frame. The badge
    #is a separate silver/black component, so it must never receive the gradient.
    material=ImageChops.multiply(alpha(frame_raw),alpha(pinline_raw))
    badge=alpha(loyalty_raw,resize=True).point(lambda a:255 if a else 0).filter(ImageFilter.MaxFilter(3))
    material=ImageChops.multiply(material,ImageChops.invert(badge))
    result=Image.new('RGBA',(1500,2100),'white');result.putalpha(material)
    out=io.BytesIO();result.save(out,'PNG');return out.getvalue()


def extend_rules_png(raw):
    with Image.open(io.BytesIO(raw)) as source:
        source=source.convert('RGBA')
        if source.size!=(1500,2100):raise ValueError('Unexpected native planeswalker frame dimensions.')
        result=Image.new('RGBA',source.size)
        result.paste(source.crop((0,0,1500,MOVE_START-TALL_EXTRA)),(0,0))
        result.paste(source.crop((0,MOVE_START,1500,SPLICE_Y)),(0,MOVE_START-TALL_EXTRA))
        # Repeat one complete native row. No resampling of borders or material.
        middle=source.crop((0,SPLICE_Y-1,1500,SPLICE_Y))
        for y in range(SPLICE_Y-TALL_EXTRA,SPLICE_Y):result.paste(middle,(0,y))
        result.paste(source.crop((0,SPLICE_Y,1500,2100)),(0,SPLICE_Y))
        out=io.BytesIO();result.save(out,'PNG');return out.getvalue()


def extend_rules_svg(raw):
    # The native background mask has rounded top corners and a curved bottom.
    # Move its upper portion with the frame; preserve the bottom curve exactly.
    root=ET.fromstring(raw)
    ns='{http://www.w3.org/2000/svg}'
    shape=next(e for e in root if e.tag==ns+'path')
    path=ET.tostring(shape,encoding='unicode')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="2100" viewBox="0 0 1500 2100">'
        f'<defs><clipPath id="upper"><rect width="1500" height="{SPLICE_Y}"/></clipPath>'
        f'<clipPath id="lower"><rect y="{SPLICE_Y}" width="1500" height="{2100-SPLICE_Y}"/></clipPath></defs>'
        f'<g transform="translate(0,-{TALL_EXTRA})"><g clip-path="url(#upper)">{path}</g></g>'
        f'<rect x="179.406" y="{SPLICE_Y-TALL_EXTRA}" width="1205.194" height="{TALL_EXTRA}" fill="rgb(0,123,67)"/>'
        f'<g clip-path="url(#lower)">{path}</g></svg>').encode()


def renderer_script(raw):
    text=raw.decode('utf-8')
    anchor="if (card.version.includes('Tall') || card.version.includes('Compleated')) {"
    if text.count(anchor)!=1:raise ValueError('Unexpected native planeswalker mask selector.')
    replacement='''if (card.version == `planeswalkerNicknameTall`) {
		if (!planeswalkerTextMask.src.includes(`/proxy-foundry/planeswalker/textTall.svg`))
			setImageUrl(planeswalkerTextMask, `/img/frames/proxy-foundry/planeswalker/textTall.svg`);
	}
	else '''+anchor
    return text.replace(anchor,replacement).encode()
