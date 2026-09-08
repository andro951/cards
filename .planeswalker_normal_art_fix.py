from pathlib import Path

p=Path('CURRENT_CARD_PIPELINE_LAND_RULES_FILL_50_FULL/card_data_to_cardconjurer.py')
s=p.read_text(encoding='utf-8')
old="data['artBounds']={'x':0.068,'y':0.101,'width':0.864,'height':0.8143}"
new="data['artBounds']={'x':0.0767,'y':0.1129,'width':0.8476,'height':0.4429}"
if old not in s:
    raise SystemExit('expected planeswalker full-height artBounds not found')
s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')
print('Changed regular planeswalkers to the normal M15 art window.')
