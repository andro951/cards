import copy, json, re
from pathlib import Path

path = Path('derevi/derevi_cards.cardconjurer')
data = json.loads(path.read_text(encoding='utf-8'))
data = [x for x in data if x.get('key') != 'Spellseeker']

template = next(x for x in data if x.get('key') == 'Recruiter of the Guard')
spell = copy.deepcopy(template['data'])

spell['text']['title']['text'] = 'Spellseeker'
spell['text']['mana']['text'] = '{2}{U}'
spell['text']['type']['text'] = 'Creature — Human Wizard'
spell['text']['rules']['text'] = 'When this creature enters, you may search your library for an instant or sorcery card with mana value 2 or less, reveal it, put it into your hand, then shuffle.'
spell['text']['rules']['size'] = 0.0348
spell['text']['pt']['text'] = '1/1'
spell['artSource'] = 'https://raw.githubusercontent.com/andro951/cards/main/derevi/spellseeker.png'

# Nonlegendary blue M15 frame.
new_frames = []
for frame in spell.get('frames', []):
    name = frame.get('name', '')
    src = frame.get('src', '')
    if 'Legend Crown' in name or '/crowns/' in src:
        continue
    if 'Power/Toughness' in name or '/regular/m15PT' in src:
        frame['name'] = 'Blue Power/Toughness'
        frame['src'] = '/img/frames/m15/regular/m15PTU.png'
    elif '/img/frames/m15/regular/m15Frame' in src:
        frame['name'] = 'Blue Frame'
        frame['src'] = '/img/frames/m15/regular/m15FrameU.png'
    new_frames.append(frame)
spell['frames'] = new_frames

# Project layout rules.
CARD_WIDTH = 2010
mana_symbols = len(re.findall(r'\{[^{}]+\}', spell['text']['mana']['text']))
spell['text']['type']['width'] = 1560 / CARD_WIDTH
spell['text']['title']['width'] = (1680 - 95 * mana_symbols) / CARD_WIDTH

# Let Card Conjurer itself inspect the loaded image dimensions and center-cover the art window.
spell['artX'] = spell['artBounds']['x']
spell['artY'] = spell['artBounds']['y']
spell['artZoom'] = 1
spell['artRotate'] = '0'
spell['onload'] = 'https://cdn.jsdelivr.net/gh/andro951/cards@main/derevi/auto_fit_art.js'

data.append({'key': 'Spellseeker', 'data': spell})
path.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

rules = Path('derevi/STYLE_RULES.md')
text = rules.read_text(encoding='utf-8') if rules.exists() else ''
rule = '\n## Art fitting\n- New hosted art should default to Card Conjurer\'s built-in centered **Auto Fit Art** behavior.\n- Preserve the original image file; cropping is controlled only by `artX`, `artY`, and `artZoom`.\n- Manual repositioning is only needed when the centered crop is compositionally undesirable.\n'
if '## Art fitting' not in text:
    rules.write_text(text.rstrip() + '\n' + rule, encoding='utf-8')
