from pathlib import Path
import json

root = Path('.')
card_path = root / 'doctor_who/doctor_who_cards.cardconjurer'
rules_path = root / 'doctor_who/STYLE_RULES.md'

cards = json.loads(card_path.read_text(encoding='utf-8'))
by_key = {c['key']: c for c in cards}
assert len(cards) == 51 and len(by_key) == 51

esika = by_key['Esika, God of the Tree']['data']
esika['text']['flipsideType']['text'] = 'Enchantment'
esika['text']['flipSideReminder']['text'] = '{W}{U}{B}{R}{G}'

bridge = by_key['The Prismatic Bridge']['data']
bridge['version'] = 'modalRegular'
bridge['frames'] = [
    {
        'name': 'Multicolored Legend Crown',
        'src': '/img/frames/modal/crowns/regular/m.png',
        'masks': [],
        'bounds': {'x': 0.0274, 'y': 0.0191, 'width': 0.9454, 'height': 0.1667},
    },
    {
        'name': 'Legend Crown Border Cover',
        'src': '/img/frames/modal/crowns/regular/cover.svg',
        'masks': [],
    },
    *[
        {
            'name': 'Multicolored Frame (Back)',
            'src': '/img/frames/modal/regular/mb.png',
            'masks': [{'src': mask_src, 'name': mask_name}],
        }
        for mask_src, mask_name in [
            ('/img/frames/modal/regular/reminder.svg', 'Flipside'),
            ('/img/frames/modal/regular/pinline.svg', 'Pinline'),
            ('/img/frames/modal/regular/title.svg', 'Title'),
            ('/img/frames/m15/regular/m15MaskType.png', 'Type'),
            ('/img/frames/modal/regular/textbox.svg', 'Rules'),
            ('/img/frames/modal/titleMDFCArrow.svg', 'MDFC Arrow'),
            ('/img/frames/modal/regular/frame.svg', 'Frame'),
            ('/img/frames/modal/regular/border.svg', 'Border'),
        ]
    ],
]
bridge['artBounds'] = {'x': 0.0767, 'y': 0.1129, 'width': 0.8476, 'height': 0.4429}
bridge['setSymbolBounds'] = {
    'x': 0.9213, 'y': 0.591, 'width': 0.12, 'height': 0.041,
    'vertical': 'center', 'horizontal': 'right'
}
bridge['text']['flipsideType']['text'] = 'God'
bridge['text']['flipSideReminder']['text'] = '{1}{G}{G}'
bridge['text']['title']['color'] = 'white'
bridge['text']['flipsideType']['color'] = 'black'
bridge['text']['flipSideReminder']['color'] = 'black'
bridge['text']['type'].pop('color', None)
bridge['text']['rules'].pop('color', None)

assert bridge['text']['title']['text'] == 'The Prismatic Bridge'
assert bridge['text']['type']['text'] == 'Legendary Enchantment'
assert 'Starnheim awaits.' in bridge['text']['rules']['text']
assert bridge['text']['flipsideType']['text'] == 'God'
assert bridge['text']['flipSideReminder']['text'] == '{1}{G}{G}'
assert all(f['src'] != '/img/frames/m15/nyx/m15FrameMNyx.png' for f in bridge['frames'])
assert sum(1 for f in bridge['frames'] if f.get('src') == '/img/frames/modal/regular/mb.png') == 8
for required in ['Flipside','Pinline','Title','Type','Rules','MDFC Arrow','Frame','Border']:
    assert any(any(m.get('name') == required for m in f.get('masks', [])) for f in bridge['frames'])

card_path.write_text(json.dumps(cards, separators=(',', ':'), ensure_ascii=False), encoding='utf-8')

rules = rules_path.read_text(encoding='utf-8')
rules = rules.replace(
    '- multicolor Modal back frame + multicolor Nyx treatment + modal multicolor legendary crown\n- compact opposite-face helper: `Creature` and `{1}{G}{G}`',
    '- native multicolor Modal Regular back frame (`/img/frames/modal/regular/mb.png`) for Flipside, Pinline, Title, Type, Rules, MDFC Arrow, Frame, and Border + modal multicolor legendary crown\n- **do not hybridize the back face with the ordinary M15 Nyx frame asset**; that hybrid can render the Bridge with its frame/title/type/rules panels missing\n- compact opposite-face helper: `God` and `{1}{G}{G}`'
)
rules = rules.replace(
    'On the Bridge back face, keep the Nyx interior treatment but use the actual Modal back title/frame/border assets so the double-triangle back-face indicator remains intact.',
    'On the Bridge back face, use the native Modal Regular multicolor back asset for every frame-region mask so the gold frame, title bar, type bar, rules panel, back-face indicator, and border render as one coherent package.'
)
rules_path.write_text(rules, encoding='utf-8')

print('Esika / Prismatic Bridge fix validated and applied')
