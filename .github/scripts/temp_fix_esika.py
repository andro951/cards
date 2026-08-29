from pathlib import Path
import json

root = Path('.')
card_path = root / 'doctor_who/doctor_who_cards.cardconjurer'
style_path = root / 'doctor_who/STYLE_RULES.md'

cards = json.loads(card_path.read_text(encoding='utf-8'))
assert len(cards) == 51
assert len({e['key'] for e in cards}) == 51

esika = next(e['data'] for e in cards if e['key'] == 'Esika, God of the Tree')
bridge = next(e['data'] for e in cards if e['key'] == 'The Prismatic Bridge')

# Esika front is already correct: preserve it and verify the opposite-face helper.
assert esika['version'] == 'modalRegular'
assert esika['text']['flipsideType']['text'] == 'Enchantment'
assert esika['text']['flipSideReminder']['text'] == '{W}{U}{B}{R}{G}'

# Rebuild the Bridge as a pure native Modal Regular multicolor BACK frame.
# Do not hybridize M15 Nyx assets into the MDFC back; that caused the frame/title/type/rules layers to fail.
crown = [f for f in bridge['frames'] if f.get('name') in ('Multicolored Legend Crown', 'Legend Crown Border Cover')]
back = '/img/frames/modal/regular/mb.png'
bridge['frames'] = crown + [
    {'name':'Multicolored Frame (Back)','src':back,'masks':[{'src':'/img/frames/modal/regular/reminder.svg','name':'Flipside'}]},
    {'name':'Multicolored Frame (Back)','src':back,'masks':[{'src':'/img/frames/modal/regular/pinline.svg','name':'Pinline'}]},
    {'name':'Multicolored Frame (Back)','src':back,'masks':[{'src':'/img/frames/modal/regular/title.svg','name':'Title'}]},
    {'name':'Multicolored Frame (Back)','src':back,'masks':[{'src':'/img/frames/m15/regular/m15MaskType.png','name':'Type'}]},
    {'name':'Multicolored Frame (Back)','src':back,'masks':[{'src':'/img/frames/modal/regular/textbox.svg','name':'Rules'}]},
    {'name':'Multicolored Frame (Back)','src':back,'masks':[{'src':'/img/frames/modal/titleMDFCArrow.svg','name':'MDFC Arrow'}]},
    {'name':'Multicolored Frame (Back)','src':back,'masks':[{'src':'/img/frames/modal/regular/frame.svg','name':'Frame'}]},
    {'name':'Multicolored Frame (Back)','src':back,'masks':[{'src':'/img/frames/modal/regular/border.svg','name':'Border'}]},
]
bridge['text']['flipsideType']['text'] = 'God'

# Validate all visible Bridge content that was missing/broken in the render.
assert bridge['version'] == 'modalRegular'
assert bridge['text']['title']['text'] == 'The Prismatic Bridge'
assert bridge['text']['mana']['text'] == '{W}{U}{B}{R}{G}'
assert bridge['text']['type']['text'] == 'Legendary Enchantment'
assert 'At the beginning of your upkeep' in bridge['text']['rules']['text']
assert 'Starnheim awaits.' in bridge['text']['rules']['text']
assert bridge['text']['flipsideType']['text'] == 'God'
assert bridge['text']['flipSideReminder']['text'] == '{1}{G}{G}'
assert not any('nyx' in f.get('src','').lower() for f in bridge['frames'])
needed = {'Flipside','Pinline','Title','Type','Rules','MDFC Arrow','Frame','Border'}
seen = []
for frame in bridge['frames']:
    for mask in frame.get('masks', []):
        if mask['name'] in needed:
            seen.append(mask['name'])
            assert frame['src'] == back
assert set(seen) == needed and len(seen) == len(needed)
assert any(f.get('src') == '/img/frames/modal/crowns/regular/m.png' for f in bridge['frames'])

card_path.write_text(json.dumps(cards, separators=(',', ':')), encoding='utf-8')

style = style_path.read_text(encoding='utf-8')
old = "Back (`The Prismatic Bridge`):\n- multicolor Modal back frame + multicolor Nyx treatment + modal multicolor legendary crown\n- compact opposite-face helper: `Creature` and `{1}{G}{G}`"
new = "Back (`The Prismatic Bridge`):\n- use the native multicolor Modal **back** frame for every back-face component (Flipside, Pinline, Title, Type, Rules, MDFC Arrow, Frame, and Border) plus the modal multicolor legendary crown\n- do **not** hybridize the back face with M15 Nyx assets; the official Kaldheim MDFC back uses the native gold Modal back treatment\n- compact opposite-face helper: `God` and `{1}{G}{G}`"
assert old in style
style = style.replace(old, new)
old2 = "On the Bridge back face, keep the Nyx interior treatment but use the actual Modal back title/frame/border assets so the double-triangle back-face indicator remains intact."
new2 = "On the Bridge back face, use the native Modal multicolor back asset throughout so the gold back frame, title/type/rules panels, and back-face indicator all render as one coherent official-style treatment."
assert old2 in style
style = style.replace(old2, new2)
style_path.write_text(style, encoding='utf-8')

print('Esika // The Prismatic Bridge fixes validated and written.')
