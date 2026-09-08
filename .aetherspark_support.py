from pathlib import Path

p=Path('CURRENT_CARD_PIPELINE_LAND_RULES_FILL_50_FULL/card_data_to_cardconjurer.py')
s=p.read_text(encoding='utf-8')

if 'def parse_planeswalker_oracle(' in s:
    raise SystemExit('planeswalker support already present; refusing to double-apply')

helper=r'''
PLANESWALKER_ABILITY_LAYOUT={
    1:[0.7467],
    2:[0.6953,0.822],
    3:[0.6639,0.7467,0.8362],
    4:[0.6505,0.72,0.7905,0.861],
}
PLANESWALKER_ABILITY_START_Y=0.6239
PLANESWALKER_ABILITY_END_Y=0.8999
PLANESWALKER_MIN_ABILITY_HEIGHT=0.028
PLANESWALKER_ABILITY_FONT_SIZE=0.0245


def parse_planeswalker_oracle(oracle):
    rows=[]
    for raw in str(oracle or '').split('\n'):
        line=raw.strip()
        if not line:
            continue
        m=re.match(r'^([+\-−]\d+|0)\s*:\s*(.*)$',line,re.S)
        if m:
            cost=m.group(1).replace('−','-')
            body=m.group(2).strip()
        else:
            cost=''
            body=line
        if not body:
            raise BuildError('Planeswalker ability row has no rules text')
        rows.append({'cost':cost,'text':body})
    if not 1 <= len(rows) <= 4:
        raise BuildError(f'Planeswalker needs 1-4 oracle ability rows; found {len(rows)}')
    return rows


def planeswalker_ability_heights(rows):
    total=PLANESWALKER_ABILITY_END_Y-PLANESWALKER_ABILITY_START_Y
    count=len(rows)
    base=PLANESWALKER_MIN_ABILITY_HEIGHT
    remaining=total-base*count
    if remaining < -1e-9:
        raise BuildError('Planeswalker ability area is too small for requested rows')
    extras=[]
    for row in rows:
        # Approximate wrapped-line demand at the native regular planeswalker
        # width. Only extra lines compete for the remaining height so short
        # abilities retain a clean one-line minimum box.
        lines=max(1,(len(str(row['text']))+47)//48)
        extras.append(max(0,lines-1))
    extra_total=sum(extras)
    if extra_total:
        heights=[base+remaining*(x/extra_total) for x in extras]
    else:
        heights=[total/count]*count
    # Pin any floating-point residue to the last box so the stack ends exactly
    # at the native regular-planeswalker rules boundary.
    heights[-1]+=total-sum(heights)
    return heights


def build_planeswalker_recipe(card,type_info):
    ct=type_info['card_types']
    if 'Planeswalker' not in ct:
        raise BuildError('planeswalker recipe requires Planeswalker type')
    if not ct <= {'Planeswalker','Artifact'}:
        raise BuildError(f'Planeswalker mixed with unsupported card types: {sorted(ct)}')

    if 'Artifact' in ct:
        code='A'
    else:
        code=regular_frame_color(card,type_info)
        if code not in 'WUBRGM':
            raise BuildError('colorless nonartifact Planeswalker has no native regular frame color in this pipeline')

    rows=parse_planeswalker_oracle(card.get('oracle_text',''))
    loyalty=str(card.get('loyalty','') or '').strip()
    if not loyalty:
        raise BuildError(f"{card.get('name','<unnamed>')}: Planeswalker needs starting loyalty")

    entry=copy.deepcopy(LAYOUTS['card_noncreature'])
    data=entry['data']
    cname=COLOR_NAMES.get(code,'Artifact')
    src=f'/img/frames/planeswalker/regular/planeswalkerFrame{code}.png'
    masks=[
        {'src':'/img/frames/planeswalker/regular/planeswalkerMaskPinline.png','name':'Pinline'},
        {'src':'/img/frames/planeswalker/regular/planeswalkerMaskTitle.png','name':'Title'},
        {'src':'/img/frames/planeswalker/regular/planeswalkerMaskType.png','name':'Type'},
        {'src':'/img/frames/planeswalker/regular/planeswalkerMaskFrame.png','name':'Frame'},
        {'src':'/img/frames/planeswalker/regular/planeswalkerMaskBorder.png','name':'Border'},
        {'src':'/img/frames/planeswalker/maskLoyalty.png','name':'Loyalty'},
    ]
    data['frames']=[{'name':f'{cname} Frame','src':src,'masks':masks}]
    data['version']='planeswalkerRegular'
    data['onload']='/js/frames/versionPlaneswalker.js'
    data['artBounds']={'x':0.068,'y':0.101,'width':0.864,'height':0.8143}
    data['setSymbolBounds']={'x':0.9227,'y':0.5891,'width':0.12,'height':0.0381,'vertical':'center','horizontal':'right'}
    data['watermarkBounds']={'x':0.5,'y':0.7762,'width':0.75,'height':0.2305}
    # Keep the user's universal creature-approved X position; scale/Y follow
    # the native regular planeswalker bounds closely.
    data['setSymbolY']=0.5689
    data['setSymbolZoom']=0.0938
    data['text']={
        'mana':{'name':'Mana Cost','text':'','y':0.0481,'width':0.9292,'height':71/2100,'oneLine':True,'size':71/1638,'align':'right','shadowX':-0.001,'shadowY':0.0029,'manaCost':True,'manaSpacing':0},
        'title':{'name':'Title','text':'','x':0.0867,'y':0.0372,'width':0.8267,'height':0.0548,'oneLine':True,'font':'belerenb','size':0.0381},
        'type':{'name':'Type','text':'','x':0.0867,'y':0.5625,'width':0.8267,'height':0.0548,'oneLine':True,'font':'belerenb','size':0.0324},
        'ability0':{'name':'Ability 1','text':'','x':0.18,'y':0.6239,'width':0.7467,'height':0.0972,'size':PLANESWALKER_ABILITY_FONT_SIZE},
        'ability1':{'name':'Ability 2','text':'','x':0.18,'y':0,'width':0.7467,'height':0.0972,'size':PLANESWALKER_ABILITY_FONT_SIZE},
        'ability2':{'name':'Ability 3','text':'','x':0.18,'y':0,'width':0.7467,'height':0.0972,'size':PLANESWALKER_ABILITY_FONT_SIZE},
        'ability3':{'name':'Ability 4','text':'','x':0.18,'y':0,'width':0.7467,'height':0,'size':PLANESWALKER_ABILITY_FONT_SIZE},
        'loyalty':{'name':'Loyalty','text':'','x':0.806,'y':0.902,'width':0.14,'height':0.0372,'size':0.0372,'font':'belerenbsc','oneLine':True,'align':'center','color':'white'},
    }

    heights=planeswalker_ability_heights(rows)
    y=PLANESWALKER_ABILITY_START_Y
    for i in range(4):
        box=data['text'][f'ability{i}']
        if i < len(rows):
            box['y']=y
            box['height']=heights[i]
            if rows[i]['cost']=='':
                # versionPlaneswalker.js performs this same expansion when the
                # loyalty-cost field is blank; include it in the saved object
                # too so the card looks right before/without rerunning onload.
                box['x']=0.136
                box['width']=0.7907
            y+=heights[i]
        else:
            box['y']=y
            box['height']=0
            box['text']=''

    defaults=PLANESWALKER_ABILITY_LAYOUT[len(rows)]
    adjustments=[]
    y=PLANESWALKER_ABILITY_START_Y
    for i,row in enumerate(rows):
        center=y+heights[i]/2
        adjustments.append(round(center-defaults[i],4) if row['cost'] else 0)
        y+=heights[i]
    while len(adjustments)<4:
        adjustments.append(0)
    costs=[row['cost'] for row in rows]+['']*(4-len(rows))
    data['planeswalker']={
        'abilities':costs,
        'abilityAdjust':adjustments,
        'count':len(rows),
        'x':0.1167,
        'width':0.8094,
    }
    return entry


def apply_planeswalker_text_layout(data,card):
    rows=parse_planeswalker_oracle(card.get('oracle_text',''))
    for i,row in enumerate(rows):
        set_text_if_present(data,f'ability{i}',italicize_dash_labels(row['text']))
    for i in range(len(rows),4):
        set_text_if_present(data,f'ability{i}','')
    set_text_if_present(data,'loyalty',str(card.get('loyalty','') or ''))
'''

marker='def infer_layout(card,type_info):\n'
assert marker in s
s=s.replace(marker,helper+'\n\n'+marker,1)

old='    if "Planeswalker" in ct: raise BuildError("Planeswalker is recognized but unsupported: add an approved planeswalker template first")\n'
new='''    if "Planeswalker" in ct:\n        if ct <= {"Planeswalker","Artifact"}:\n            return "planeswalker"\n        raise BuildError(f"Planeswalker mixed with unsupported card types: {sorted(ct)}")\n'''
assert old in s
s=s.replace(old,new,1)

marker='''    regular_color=regular_frame_color(card,type_info)\n    artifact="Artifact" in type_info["card_types"]\n\n    if recipe=="original_dual_land_textless":\n'''
repl='''    regular_color=regular_frame_color(card,type_info)\n    artifact="Artifact" in type_info["card_types"]\n\n    if recipe=="planeswalker":\n        return build_planeswalker_recipe(card,type_info)\n    if recipe=="original_dual_land_textless":\n'''
assert marker in s
s=s.replace(marker,repl,1)

old='''    if recipe=="saga":\n        parsed=parse_saga_oracle(card.get("oracle_text",""))\n'''
new='''    if recipe=="planeswalker":\n        if card.get("loyalty") in (None,""):\n            raise BuildError(f"{name}: Planeswalker needs starting loyalty")\n        parse_planeswalker_oracle(card.get("oracle_text",""))\n    if recipe=="saga":\n        parsed=parse_saga_oracle(card.get("oracle_text",""))\n'''
assert old in s
s=s.replace(old,new,1)

old='''        and "Land" not in type_info["card_types"]\n        and len(ordered_standard_colors(card.get("colors")))==2\n'''
new='''        and "Land" not in type_info["card_types"]\n        and recipe!="planeswalker"\n        and len(ordered_standard_colors(card.get("colors")))==2\n'''
assert old in s
s=s.replace(old,new,1)

old='''    set_text_if_present(data,"type",tl)\n    if recipe=="saga":\n        apply_saga_text_layout(data,saga_meta or saga_layout_metadata(card))\n    else:\n        set_text_if_present(data,"rules",rules)\n    set_text_if_present(data,"pt",pt)\n'''
new='''    set_text_if_present(data,"type",tl)\n    if recipe=="planeswalker":\n        apply_planeswalker_text_layout(data,card)\n    elif recipe=="saga":\n        apply_saga_text_layout(data,saga_meta or saga_layout_metadata(card))\n    else:\n        set_text_if_present(data,"rules",rules)\n    set_text_if_present(data,"pt",pt)\n'''
assert old in s
s=s.replace(old,new,1)

# Keep the support matrix/documentation accurate.
s=s.replace('    ("Modal DFC front/back", "automatic from scryfall_layout=modal_dfc + face_index, using Esika/The Prismatic Bridge as the approved example"),\n',
'''    ("Modal DFC front/back", "automatic from scryfall_layout=modal_dfc + face_index, using Esika/The Prismatic Bridge as the approved example"),\n    ("Planeswalker / Artifact Planeswalker", "native regular planeswalker frame with 1-4 passive/loyalty ability boxes"),\n''',1)
s=s.replace('    "Planeswalker",\n','',1)

p.write_text(s,encoding='utf-8')
print('Applied standard planeswalker support.')
