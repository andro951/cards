from pathlib import Path

p=Path('CURRENT_CARD_PIPELINE_LAND_RULES_FILL_50_FULL/card_data_to_cardconjurer.py')
s=p.read_text(encoding='utf-8')
old="""    data['frames']=[{'name':f'{cname} Frame','src':src,'masks':masks}]\n"""
new="""    # Card Conjurer's serialized frame objects effectively intersect multiple\n    # masks on one frame entry. Regular pipeline outputs therefore use one\n    # masked frame entry per visible frame component. Do the same for\n    # planeswalkers so title/type/frame/border/loyalty pieces all render.\n    data['frames']=[]\n    for mask in masks:\n        data['frames'].append({\n            'name':f\"{cname} {mask['name']}\",\n            'src':src,\n            'masks':[mask],\n        })\n"""
if old not in s:
    raise SystemExit('expected planeswalker single-frame construction not found')
s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')
print('Applied separate planeswalker frame-layer serialization.')
