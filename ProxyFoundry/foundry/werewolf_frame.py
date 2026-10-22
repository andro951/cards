"""Approved Godzilla/Werewolf header pieces, independent of the lower frame."""
from .nickname_geometry import TITLE_BAR_HEIGHT
import copy,io,re
from urllib.parse import quote
from PIL import Image

PREFIX='/img/frames/proxy-foundry/werewolf/'
ICON_RING_VERSION='neutral-surround-v1'
BLACK_TITLE_FILL='data:image/svg+xml,'+quote(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1500 2100">'
    '<rect width="1500" height="2100" fill="black" fill-opacity="0.5"/></svg>',safe='')


def neutralize_icon_surround(raw):
    """Desaturate the red donor fringe without changing neutral paint or alpha."""
    with Image.open(io.BytesIO(raw)) as source:
        result=source.convert('RGBA');pixels=[]
        for r,g,b,a in result.get_flattened_data():
            if r>g+4 and r>b+4:
                value=round(.2126*r+.7152*g+.0722*b)
                pixels.append((value,value,value,a))
            else:pixels.append((r,g,b,a))
        result.putdata(pixels)
        output=io.BytesIO();result.save(output,'PNG');return output.getvalue()


def is_sun_moon_werewolf(card):
    return (card.get('layout')=='transform' and 'sunmoondfc' in (card.get('frame_effects') or [])
            and any('Werewolf' in str(face.get('type_line','')) for face in card.get('card_faces',[])))

def reflect_title_pinline(source):
    """Keep the upper center row and reflect it, discarding the lower rails."""
    source=source.convert('RGBA');width,height=source.size
    upper=source.getchannel('A').crop((0,0,round(width*.15),round(height*.15)))
    opaque=upper.point(lambda value:255 if value>=128 else 0)
    box=opaque.getbbox()
    if box is None:raise ValueError('No Werewolf title circle found.')
    rows=[y for y in range(opaque.height) if opaque.getpixel((box[0],y))]
    split=round((min(rows)+max(rows))/2+.5)
    if split<=0 or split*2>height:raise ValueError('Invalid Werewolf circle center.')
    top=source.crop((0,0,width,split))
    result=Image.new('RGBA',source.size)
    result.paste(top,(0,0));result.paste(top.transpose(Image.Transpose.FLIP_TOP_BOTTOM),(0,split))
    return result

def icon_layers(icon):
    ring_bounds={'x':80/1500,'y':97/2100,'width':129/1500,'height':129/2100}
    if icon['bounds']['x']>.5:ring_bounds['x']=1-ring_bounds['x']-ring_bounds['width']
    return [copy.deepcopy(icon),{'name':'Transform icon surround','src':PREFIX+'IconRing.png','masks':[],
            'bounds':ring_bounds}]


def reserve_icon_space(data,slot,icon,left_min=.16):
    title=data['text'][slot];right=title['x']+title['width']
    if icon['bounds']['x']>.5:
        title['width']=max(.001,min(right,icon['bounds']['x']-.02)-title['x'])
    else:
        title['x']=max(title['x'],left_min);title['width']=right-title['x']

def bar_fills(normal,front,*,right_icon=False):
    """Shared circular-title geometry, black fronts and native colored backs."""
    fills=[]
    for frame in normal['frames']:
        masks=[mask for mask in frame.get('masks',[]) if mask.get('name') in {'Title','Type'}]
        if not masks:continue
        if front:
            masks=[mask for mask in masks if mask.get('name')=='Title']
            if not masks or fills:continue
        layer=copy.deepcopy(frame);layer['masks']=copy.deepcopy(masks)
        if not (right_icon and any(mask.get('name')=='Title' for mask in masks)):
            layer['src']=layer['src'].replace('/transform/regular/new/back','/transform/regular/back')
            for mask in layer['masks']:
                mask['src']=mask['src'].replace('/transform/regular/new/','/transform/regular/')
        if any(mask.get('name')=='Title' for mask in masks):
            code=re.search(r'(?:front|back)([WUBRGMAL])\.png$',str(layer['src']))
            code=code[1] if code else 'M'
            layer.update(name='Godzilla transform title material',
                         src='/img/frames/proxy-foundry/'+('godzilla/Title' if front else 'transform/TitleColored')+code+'.png',
                         bounds={'x':.0494,'y':.0405,'width':.9014,'height':TITLE_BAR_HEIGHT})
            if right_icon:
                # Mirror only the clip; the Godzilla bar itself is symmetric.
                for mask in layer['masks']:
                    if mask.get('name')=='Title':mask['src']='/img/frames/m15/transform/regular/new/maskTitle.png'
        fills.append(layer)
    return fills


def apply_header(data,normal,sem,icon,rim_layers,addon_layers,*,front=None):
    nickname=bool(str(sem.get('nickname') or '').strip())
    if front is None:front=icon['name']!='Crescent Moon'
    # The Godzilla body supplies its black type fill; do not stack another fill.
    right_icon=icon['bounds']['x']>.5
    fills=bar_fills(normal,front,right_icon=right_icon)
    body=[]
    for frame in data['frames']:
        src=str(frame.get('src',''))
        if '/proxy-foundry/godzilla/Title' in src or '/proxy-foundry/godzilla/Crown' in src:continue
        layer=copy.deepcopy(frame)
        if '/nickname/m15NicknameFrame' in src:
            layer.setdefault('masks',[]).append({'name':'Godzilla lower frame only','src':PREFIX+'LowerMask.png'})
        body.append(layer)
    outline={'name':'Reflected Werewolf title black outline',
             'src':'/img/frames/proxy-foundry/transform/TitleOutlineBack.png' if right_icon else PREFIX+'TitleOutline.png','masks':[]}
    data['frames']=[*icon_layers(icon),*rim_layers,outline,*fills,*addon_layers,*body]
    if sem.get('legendary'):
        # The native floating DFC crown has a real circular opening and no strip.
        data['frames']=[*icon_layers(icon),*rim_layers,*fills,*body]
    if nickname:
        data['text']['title'].update(x=.14,y=.1129,width=.72,height=.0243,align='center',
                                    color='white',outlineColor='black',outlineWidth=.0025,shadowX=0,shadowY=0)
    slot='nickname' if nickname else 'title'
    reserve_icon_space(data,slot,icon)
    light_back=(sem.get('colors')==['W'] or
                not sem.get('colors') and 'Land' not in sem.get('types',[]))
    for key in (slot,'type'):
        data['text'][key].update(color='black' if not front and light_back else 'white',
                                 outlineWidth=0,shadowX=0,shadowY=0)
    data['text'][slot].update(color='white',outlineColor='black',outlineWidth=.0025)
