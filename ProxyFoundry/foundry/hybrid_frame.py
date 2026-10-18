"""Native M15 hybrid materials, following CardConjurer's autoM15Frame recipe."""
import copy,re
from .legacy import compiler as native

def hybrid_colors(sem):
    """Recognize a two-color hybrid cost, ignoring generic and variable mana.

    Ordinary colored requirements and third colors retain the existing gold
    treatment. Slashes in Phyrexian or monocolored hybrid costs alone do not
    qualify, nor do hybrid symbols appearing only in rules text.
    """
    colors=set(sem.get('colors') or [])
    if len(colors)!=2 or not colors.issubset(set('WUBRG')) or 'Land' in sem.get('types',[]):return []
    found=False
    for token in re.findall(r'\{([^{}]+)\}',str(sem.get('mana_cost') or '').upper()):
        parts=token.split('/')
        colored={part for part in parts if part in 'WUBRG' and len(part)==1}
        if not colored:continue
        if colored!=colors or len(parts)!=2:return []
        found=True
    return native.canonical_dual_color_order(list(colors)) if found else []


def apply_hybrid_frame_treatment(data,sem):
    """Use neutral bars/PT and native split body/rules textures on classic M15.

    CardConjurer's cardFrameProperties selects L for hybrid title/type bars and
    C for PT. Only native regular/Nyx pieces are changed here; structural
    families with their own materials are left to their frame recipes.
    """
    colors=hybrid_colors(sem)
    if not colors:return False
    first,second=colors
    frames=[];changed=False
    for frame in data.get('frames',[]):
        if not isinstance(frame,dict):
            frames.append(frame);continue
        src=str(frame.get('src') or '')
        if re.fullmatch(r'/img/frames/m15/regular/m15PT[WUBRGMAC]\.png',src):
            layer=copy.deepcopy(frame)
            layer.update(src='/img/frames/m15/regular/m15PTC.png',name='Hybrid Colorless Power/Toughness')
            frames.append(layer);changed=True;continue
        match=re.fullmatch(r'/img/frames/m15/(regular|nyx)/m15Frame[WUBRGMALC](Nyx)?\.png',src)
        if not match:
            frames.append(frame);continue
        masks=frame.get('masks') or []
        names={mask.get('name') for mask in masks if isinstance(mask,dict)}
        if names & {'Title','Type'}:
            layer=copy.deepcopy(frame)
            layer.update(src='/img/frames/m15/regular/m15FrameL.png',name='Hybrid Neutral Title/Type')
            frames.append(layer);changed=True
        elif names & {'Rules','Frame'} and not ('Frame' in names and ('Artifact' in sem.get('types',[]) or 'Vehicle' in sem.get('subtypes',[]))):
            base=copy.deepcopy(frame);right=copy.deepcopy(frame)
            family,suffix=match.group(1),match.group(2) or ''
            base.update(src=f'/img/frames/m15/{family}/m15Frame{first}{suffix}.png',name=f'Hybrid {native.COLOR_NAMES[first]} '+('/'.join(sorted(names))))
            right.update(src=f'/img/frames/m15/{family}/m15Frame{second}{suffix}.png',name=f'Hybrid {native.COLOR_NAMES[second]} Right Blend')
            right['masks']=copy.deepcopy(masks)+[{'name':'Hybrid Right Blend','src':native.dual_crown_right_blend_mask_src()}]
            frames.extend([right,base]);changed=True
        else:
            frames.append(frame)
    data['frames']=frames
    return changed
