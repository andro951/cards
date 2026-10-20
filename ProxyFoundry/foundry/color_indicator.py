"""Native face color indicators on compatible Godzilla and transform type bars."""
import math
from urllib.parse import quote

COLORS = {'W':'#fcfeff', 'U':'#0075be', 'B':'#272624', 'R':'#ef3827', 'G':'#007b43'}
INDICATOR_NAME = 'Face color indicator'
INDICATOR_BASE_NAME = 'Recessed color indicator base'
PREFIX = '/img/frames/m15/ciPips/'
BASE_BOUNDS = {'x':.0767,'y':.5748,'width':.0467,'height':.0334}


def indicator_svg(colors):
    if len(colors) == 1:
        fill = f'<circle cx="150" cy="1242" r="22" fill="{COLORS[colors[0]]}"/>'
    else:
        parts = []
        for index, color in enumerate(colors):
            start = -math.pi/2 + index*math.tau/len(colors)
            end = -math.pi/2 + (index+1)*math.tau/len(colors)
            x1,y1 = 150+22*math.cos(start),1242+22*math.sin(start)
            x2,y2 = 150+22*math.cos(end),1242+22*math.sin(end)
            parts.append(f'<path d="M150 1242 L{x1:.6f} {y1:.6f} A22 22 0 0 1 {x2:.6f} {y2:.6f} Z" fill="{COLORS[color]}"/>')
        fill = ''.join(parts)
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1500 2100">'+fill+'</svg>'


def apply_color_indicator(data, face):
    # Do not infer this from colors or color identity, or inherit the other face.
    supplied = face.get('color_indicator')
    if not isinstance(supplied, list):return False
    colors = [color for color in 'WUBRG' if color in supplied]
    if not colors:return False
    box = data.get('text', {}).get('type')
    if not isinstance(box, dict):return False
    frames = data.setdefault('frames', [])
    if any(frame.get('name') == INDICATOR_NAME for frame in frames):return False
    left = float(box['x'])
    right = left+float(box['width'])
    new_left = max(left,BASE_BOUNDS['x']+BASE_BOUNDS['width']+.009)
    if new_left >= right:return False
    layers=[]
    if len(colors)<=3:
        masks=(['firstHalf','secondHalf'] if len(colors)==2 else
               ['firstThird','secondThird','thirdThird'] if len(colors)==3 else [])
        for index,color in enumerate(colors):
            layers.append({'name':INDICATOR_NAME if not index else f'Indicator color {color}',
                'src':PREFIX+color.lower()+'.svg',
                'masks':[{'name':masks[index],'src':PREFIX+masks[index]+'.svg'}] if masks else []})
    else:
        layers.append({'name':INDICATOR_NAME,
            'src':'data:image/svg+xml,'+quote(indicator_svg(colors),safe=''),'masks':[]})
    # Native pip paint draws above its native beveled/recessed surround.
    layers.append({'name':INDICATOR_BASE_NAME,'src':PREFIX+'base.png','masks':[],
                   'bounds':dict(BASE_BOUNDS)})
    if data.get('saga'):
        #Saga type bars are at the foot of the card. The pip SVGs are full-card
        #native assets, so translate both their paint and their recessed base.
        offset=float(box['y'])+float(box['height'])/2-(BASE_BOUNDS['y']+BASE_BOUNDS['height']/2)
        for layer in layers:
            if layer['name']==INDICATOR_BASE_NAME:layer['bounds']['y']+=offset
            else:layer['bounds']={'x':0,'y':offset,'width':1,'height':1}
    frames[0:0]=layers
    box['x'] = new_left
    box['width'] = right-new_left
    return True
