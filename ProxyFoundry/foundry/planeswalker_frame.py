"""Extend the native nickname frame by repeating its straight rules-box middle."""
import io
import xml.etree.ElementTree as ET
from PIL import Image

PREFIX='/img/frames/proxy-foundry/planeswalker/'
TALL_VERSION='repeat-middle-v1'
TALL_EXTRA=147
TALL_SHIFT=TALL_EXTRA/2100
SPLICE_Y=1550
MOVE_START=900


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
