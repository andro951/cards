from pathlib import Path
import json

ROOT=Path('.')
WOP=60
RIGHT='/img/frames/maskRightHalf.png'; MID='/img/frames/maskMiddleThird.png'
GS='/img/frames/m15/genericShowcase/m15GenericShowcaseFrame{}.png'
GP='/img/frames/m15/genericShowcase/m15GenericShowcaseMaskPinline.png'
MT='/img/frames/m15/regular/m15MaskTitle.png'; MTYPE='/img/frames/m15/regular/m15MaskType.png'; MR='/img/frames/m15/regular/m15MaskRules.png'; MB='/img/frames/m15/regular/m15MaskBorder.png'
SS={'L':'/img/frames/m15/boxTopper/short/l.png','W':'/img/frames/m15/boxTopper/short/wl.png','U':'/img/frames/m15/boxTopper/short/ul.png','B':'/img/frames/m15/boxTopper/short/bl.png','R':'/img/frames/m15/boxTopper/short/rl.png','G':'/img/frames/m15/boxTopper/short/gl.png','M':'/img/frames/m15/boxTopper/short/ml.png'}
SP='/img/frames/m15/boxTopper/short/pinline.svg'; ST='/img/frames/m15/boxTopper/short/type.png'; SR='/img/frames/m15/boxTopper/short/text.svg'; SF='/img/frames/m15/boxTopper/short/frame.svg'
LANDS={'Flooded Strand': {'c': ['W', 'U'], 't': 'Land', 'r': '{T}, Pay 1 life, Sacrifice this land: Search your library for a Plains or Island card, put it onto the battlefield, then shuffle.{flavor}Where dragons once slept, their bones now rest.', 's': False, 'z': 0.0335}, 'Scalding Tarn': {'c': ['U', 'R'], 't': 'Land', 'r': '{T}, Pay 1 life, Sacrifice this land: Search your library for an Island or Mountain card, put it onto the battlefield, then shuffle.{flavor}"I came here often to meditate on Ojutai\'s teachings. Now, I must also consider his failings."  - Narset', 's': False, 'z': 0.0315}, 'Crystal Quarry': {'c': ['M'], 't': 'Land', 'r': '{T}: Add {C}.\n{5}, {T}: Add {W}{U}{B}{R}{G}.{flavor}"How tragic that greed eclipses beauty."  - Seton, centaur druid', 's': False, 'z': 0.0362}, "Raffine's Tower": {'c': ['U', 'B', 'W'], 't': 'Land - Plains Island Swamp', 'r': "{center}{i}({T}: Add {W}, {U}, or {B}.){/i}{lns}{left}This land enters tapped.\nCycling {3} ({3}, Discard this card: Draw a card.){flavor}The Obscura's Cloud Spire dominates the skyline, its eye a beacon of progress that sees all.", 's': False, 'z': 0.0315}, 'The World Tree': {'c': ['M'], 't': 'Land', 'r': 'This land enters tapped.\n{T}: Add {G}.\nAs long as you control six or more lands, lands you control have "{T}: Add one mana of any color."\n{W}{W}{U}{U}{B}{B}{R}{R}{G}{G}, {T}, Sacrifice this land: Search your library for any number of God cards, put them onto the battlefield, then shuffle.', 's': False, 'z': 0.0295}, 'Savannah': {'c': ['G', 'W'], 't': 'Land - Forest Plains', 'r': '{center}{i}({T}: Add {G} or {W}.){/i}', 's': True, 'z': 0.0362}, 'Misty Rainforest': {'c': ['G', 'U'], 't': 'Land', 'r': '{T}, Pay 1 life, Sacrifice this land: Search your library for a Forest or Island card, put it onto the battlefield, then shuffle.{flavor}In the mist, turbulent enough to deafen.\nBeneath the boughs, serene enough to soothe.', 's': False, 'z': 0.0315}, 'Windswept Heath': {'c': ['G', 'W'], 't': 'Land', 'r': '{T}, Pay 1 life, Sacrifice this land: Search your library for a Forest or Plains card, put it onto the battlefield, then shuffle.{flavor}An underground paradise, bright and thriving beneath the surface of Ixalan.', 's': False, 'z': 0.0315}, 'Steam Vents': {'c': ['U', 'R'], 't': 'Land - Island Mountain', 'r': '{center}{i}({T}: Add {U} or {R}.){/i}{lns}{left}As this land enters, you may pay 2 life. If you don\'t, it enters tapped.{flavor}"A massive new Izzet building project with an unstated purpose? Probably fine."  - Zija, Simic mutationist', 's': False, 'z': 0.0315}, 'Marsh Flats': {'c': ['W', 'B'], 't': 'Land', 'r': '{T}, Pay 1 life, Sacrifice this land: Search your library for a Plains or Swamp card, put it onto the battlefield, then shuffle.{flavor}"We remember all the world has endured, everything it has gone through to bring us to today. We are proud of Tarkir."  - Betor', 's': False, 'z': 0.0315}, "Spara's Headquarters": {'c': ['W', 'U', 'G'], 't': 'Land - Forest Plains Island', 'r': "{center}{i}({T}: Add {G}, {W}, or {U}.){/i}{lns}{left}This land enters tapped.\nCycling {3} ({3}, Discard this card: Draw a card.){flavor}To most, the Nido Sanctuary is an office complex. To the Brokers, it's a vault of secrets.", 's': False, 'z': 0.0315}, 'Cascading Cataracts': {'c': ['M'], 't': 'Land', 'r': 'Indestructible\n{T}: Add {C}.\n{5}, {T}: Add five mana in any combination of colors.{flavor}"The power that flows here cannot be denied. But where is the source?"  - Nissa Revane', 's': False, 'z': 0.0335}, 'Polluted Delta': {'c': ['U', 'B'], 't': 'Land', 'r': '{T}, Pay 1 life, Sacrifice this land: Search your library for an Island or Swamp card, put it onto the battlefield, then shuffle.{flavor}A warped gateway that seeps toxins and malevolence into the waters around Towashi.', 's': False, 'z': 0.0315}, 'Arid Mesa': {'c': ['R', 'W'], 't': 'Land', 'r': '{T}, Pay 1 life, Sacrifice this land: Search your library for a Mountain or Plains card, put it onto the battlefield, then shuffle.{flavor}"This was where I fought my first battle under Kolaghan. How I have outgrown her."  - Zurgo, khan of the Mardu', 's': False, 'z': 0.0315}, 'Forest': {'c': ['G'], 't': 'Basic Land - Forest', 'r': '{center}{i}({T}: Add {G}.){/i}', 's': True, 'z': 0.0362}, "Gaea's Cradle": {'c': ['G'], 't': 'Legendary Land', 'r': '{T}: Add {G} for each creature you control.{flavor}"Here sprouted the first seedling of Argoth. Here the last tree will fall."  - Gamelen, Citanul elder', 's': True, 'z': 0.0335}, "Jetmir's Garden": {'c': ['G', 'W', 'R'], 't': 'Land - Mountain Forest Plains', 'r': '{center}{i}({T}: Add {R}, {G}, or {W}.){/i}{lns}{left}This land enters tapped.\nCycling {3} ({3}, Discard this card: Draw a card.){flavor}The parklike Cabaretti grounds offer rest, food, and the perfect place to shake off a tail.', 's': False, 'z': 0.0315}, 'Mountain': {'c': ['R'], 't': 'Basic Land - Mountain', 'r': '{center}{i}({T}: Add {R}.){/i}', 's': True, 'z': 0.0362}, 'Tundra': {'c': ['W', 'U'], 't': 'Land - Plains Island', 'r': '{center}{i}({T}: Add {W} or {U}.){/i}', 's': True, 'z': 0.0362}, 'Godless Shrine': {'c': ['W', 'B'], 't': 'Land - Plains Swamp', 'r': "{center}{i}({T}: Add {W} or {B}.){/i}{lns}{left}As this land enters, you may pay 2 life. If you don't, it enters tapped.{flavor}Sin is debt, and absolution is paid in tithes of gold and blood.", 's': False, 'z': 0.0315}, 'Swamp': {'c': ['B'], 't': 'Basic Land - Swamp', 'r': '{center}{i}({T}: Add {B}.){/i}', 's': True, 'z': 0.0362}, 'Tropical Island': {'c': ['G', 'U'], 't': 'Land - Forest Island', 'r': '{center}{i}({T}: Add {G} or {U}.){/i}', 's': True, 'z': 0.0362}, 'Zagoth Triome': {'c': ['G', 'U', 'B'], 't': 'Land - Swamp Forest Island', 'r': '{center}{i}({T}: Add {B}, {G}, or {U}.){/i}{lns}{left}This land enters tapped.\nCycling {3} ({3}, Discard this card: Draw a card.){flavor}Hunters in the primeval wetlands become fluent in reading the ripples to tell when to pursue and when to flee.', 's': False, 'z': 0.0315}, 'Indatha Triome': {'c': ['B', 'G', 'W'], 't': 'Land - Plains Swamp Forest', 'r': '{center}{i}({T}: Add {W}, {B}, or {G}.){/i}{lns}{left}This land enters tapped.\nCycling {3} ({3}, Discard this card: Draw a card.){flavor}"These lowlands were formed thousands of years ago by the behemoth Indath - its final footsteps before vanishing into the sea."  - Tales of the Ozolith', 's': False, 'z': 0.0315}, 'Ketria Triome': {'c': ['U', 'R', 'G'], 't': 'Land - Forest Island Mountain', 'r': '{center}{i}({T}: Add {G}, {U}, or {R}.){/i}{lns}{left}This land enters tapped.\nCycling {3} ({3}, Discard this card: Draw a card.){flavor}Nowhere on Ikoria are monsters more integral to the landscape than Ketria, where the river itself will stand up and roar.', 's': False, 'z': 0.0315}, 'Reflecting Pool': {'c': ['M'], 't': 'Land', 'r': '{T}: Add one mana of any type that a land you control could produce.{flavor}Does it reflect the future that once was or the past that can never be?', 's': True, 'z': 0.0335}, 'Watery Grave': {'c': ['U', 'B'], 't': 'Land - Island Swamp', 'r': '{center}{i}({T}: Add {U} or {B}.){/i}{lns}{left}As this land enters, you may pay 2 life. If you don\'t, it enters tapped.{flavor}"I fear that as we scurry after phantoms, the Dimir pull nine puppet strings."  - Ral Zarek', 's': False, 'z': 0.0315}, 'Plaza of Heroes': {'c': ['M'], 't': 'Land', 'r': '{T}: Add {C}.\n{T}: Add one mana of any color. Spend this mana only to cast a legendary spell.\n{T}: Add one mana of any color among legendary permanents you control.\n{3}, {T}, Exile this land: Target legendary creature gains hexproof and indestructible until end of turn.', 's': False, 'z': 0.0315}, 'Mana Confluence': {'c': ['M'], 't': 'Land', 'r': '{T}, Pay 1 life: Add one mana of any color.{flavor}Five rivers encircle Theros, flowing with waters more ancient than the world itself.', 's': True, 'z': 0.0335}, 'Sacred Foundry': {'c': ['R', 'W'], 't': 'Land - Mountain Plains', 'r': '{center}{i}({T}: Add {R} or {W}.){/i}{lns}{left}As this land enters, you may pay 2 life. If you don\'t, it enters tapped.{flavor}"You will not be trained here. You will be forged."  - Commander Yaszen', 's': False, 'z': 0.0315}, 'Raugrin Triome': {'c': ['R', 'W', 'U'], 't': 'Land - Island Mountain Plains', 'r': '{center}{i}({T}: Add {U}, {R}, or {W}.){/i}{lns}{left}This land enters tapped.\nCycling {3} ({3}, Discard this card: Draw a card.){flavor}Raugrin meets the sea with jaws wide, its coast spiked with teeth of crystal and granite.', 's': False, 'z': 0.0315}, 'Plains': {'c': ['W'], 't': 'Basic Land - Plains', 'r': '{center}{i}({T}: Add {W}.){/i}', 's': True, 'z': 0.0362}, 'Island': {'c': ['U'], 't': 'Basic Land - Island', 'r': '{center}{i}({T}: Add {U}.){/i}', 's': True, 'z': 0.0362}}
NONLAND_RULES={'Farewell': 'Choose one or more  - \n• Exile all artifacts.\n• Exile all creatures.\n• Exile all enchantments.\n• Exile all graveyards.{flavor}"I don\'t want to go."', 'Esika, God of the Tree': 'Vigilance\n{T}: Add one mana of any color.\nOther legendary creatures you control have vigilance and "{T}: Add one mana of any color."{flavor}"I know this world, from canopy to roots."', 'The Prismatic Bridge': 'At the beginning of your upkeep, reveal cards from the top of your library until you reveal a creature or planeswalker card. Put that card onto the battlefield and the rest on the bottom of your library in a random order.{flavor}Starnheim awaits.', 'Sol Ring': '{T}: Add {C}{C}.{flavor}"The Eye of Harmony. Exploding star in the act of becoming a black hole. Time Lord engineering."  - The Eleventh Doctor', 'Propaganda': 'Creatures can\'t attack you unless their controller pays {2} for each creature they control that\'s attacking you.{flavor}"You\'ve failed Gerrard. You\'ve failed the Legacy. You\'ve failed yourself. I can do no more."  - Volrath, to Karn', 'Everybody Lives!': 'All creatures gain hexproof and indestructible until end of turn. Players gain hexproof until end of turn. Players can\'t lose life this turn and players can\'t lose the game or win the game this turn.{flavor}"Everybody lives, Rose. Just this once, everybody lives!"  - The Ninth Doctor', 'Elven Chorus': 'You may look at the top card of your library any time.\nYou may cast creature spells from the top of your library.\nCreatures you control have "{T}: Add one mana of any color."{flavor}Elvish singing was not a thing to miss, in June under the stars.', 'Brago, King Eternal': 'Flying\nWhenever Brago deals combat damage to a player, exile any number of target nonland permanents you control, then return those cards to the battlefield under their owner\'s control.{flavor}"My rule persists beyond death itself."', "Akroma's Memorial": 'Creatures you control have flying, first strike, vigilance, trample, haste, and protection from black and from red.{flavor}"No rest. No mercy. No matter what."  - Memorial inscription', 'Sonic Screwdriver': "{T}: Add one mana of any color.\n{1}, {T}: Untap another target artifact.\n{2}, {T}: Scry 1. (Look at the top card of your library. You may put that card on the bottom.)\n{3}, {T}: Target creature can't be blocked this turn.{flavor}The Doctor's technologically advanced tool helps them out in most situations.", 'Morophon, the Boundless': 'Changeling (This card is every creature type.)\nAs Morophon enters, choose a creature type.\nSpells of the chosen type you cast cost\n{W}{U}{B}{R}{G} less to cast. This effect reduces only the amount of colored mana you pay.\nOther creatures you control of the chosen type get +1/+1.'}

def f(src,mask=None,ms=None,name='',opacity=None,bounds=None,erase=None):
 x={'name':name,'src':src,'masks':[]}
 if mask:x['masks'].append({'src':mask,'name':ms})
 if opacity is not None:x['opacity']=opacity
 if bounds is not None:x['bounds']=bounds
 if erase is not None:x['erase']=erase
 return x

def extra_mask(x,src,name): x['masks'].append({'src':src,'name':name}); return x

def color_layers(cs,short=False,rules=False):
 out=[]
 for i,c in enumerate(cs):
  src=SS[c] if short else GS.format(c)
  mask=(SR if rules and short else SP if short else MR if rules else GP)
  label=('Multicolored' if c=='M' else c)+(' Short Land Rules' if rules and short else ' Short Land Pinline' if short else ' Rules' if rules else ' Pinline')
  x=f(src,mask,'Rules' if rules else 'Pinline',label,WOP if rules and c=='W' else None)
  if len(cs)==2 and i==1: extra_mask(x,RIGHT,'Right Half')
  if len(cs)==3 and i==1: extra_mask(x,MID,'Middle Third')
  if len(cs)==3 and i==2: extra_mask(x,RIGHT,'Right Half')
  out.append(x)
 return out

def rebuild_land(d,k,spec):
 cs=spec['c']; short=spec['s']; legend=(k=="Gaea's Cradle")
 frames=[]
 if legend:
  frames += [f('/img/frames/m15/crowns/m15CrownFloatingOutline.png',name='Legend Crown Outline',bounds={'x':.028,'y':.0172,'width':.944,'height':.1062}),f('/img/frames/m15/crowns/m15CrownLFloating.png',name='Land Legend Crown',bounds={'x':.0307,'y':.0191,'width':.9387,'height':.1024}),f('/img/black.png',name='Legend Crown Lower Cutout',bounds={'x':.0734,'y':.1096,'width':.8532,'height':.0143},erase=True)]
 if short:
  frames += color_layers(cs,True,False)
  frames += [f(SS['L'],MT,'Title','Neutral Short Land Title'),f(SS['L'],ST,'Type','Neutral Short Land Type')]
  frames += color_layers(cs,True,True)
  frames += [f(SS['L'],SF,'Frame','Short Land Frame'),f(SS['L'],MB,'Border','Short Land Border')]
  d['version']='m15ExtendedArtShort'; d['artBounds']={'x':0,'y':.081,'width':1,'height':.5753}; d['artX']=0.0; d['artY']=-0.1670220326936745; d['artZoom']=1.963
  d['setSymbolBounds']={'x':.9213,'y':.6343,'width':.12,'height':.041,'vertical':'center','horizontal':'right'}; d['setSymbolY']=.6125963752665245; d['watermarkBounds']={'x':.5,'y':.7978,'width':.75,'height':.1872}
  ty=.61; ry=.6743; rh=.2448
 else:
  frames += color_layers(cs,False,False)
  frames += [f(GS.format('L'),MT,'Title','Neutral Land Title'),f(GS.format('L'),MTYPE,'Type','Neutral Land Type')]
  frames += color_layers(cs,False,True)
  frames += [f(GS.format('L'),MB,'Border','Land Frame')]
  d['version']='genericShowcase'; d['artBounds']={'x':0,'y':0,'width':1,'height':.9224}; d['artX']=0; d['artY']=-0.0745142857142857; d['artZoom']=1.962890625
  d['setSymbolBounds']={'x':.9213,'y':.591,'width':.12,'height':.041,'vertical':'center','horizontal':'right'}; d['setSymbolY']=.5692963752665245; d['watermarkBounds']={'x':.5,'y':.7762,'width':.75,'height':.2305}
  ty=.5664; ry=.6303; rh=.2875
 d['frames']=frames
 t=d.setdefault('text',{})
 t['type'].update({'text':spec['t'],'x':.0854,'y':ty,'width':.8292,'height':.0543,'oneLine':True,'font':'belerenb','size':.0324,'color':'white'})
 if short:t['type'].update({'shadowX':.0014,'shadowY':.001})
 t['rules'].update({'text':spec['r'],'x':.105,'y':ry,'width':.79,'height':rh,'size':spec['z'],'color':'white','align':'center' if spec['r'].startswith('{center}') and '{left}' not in spec['r'] and '{flavor}' not in spec['r'] else 'left'})
 t['rules'].pop('noVerticalCenter',None)
 t['title']['width']=.8292
 if short:t['title'].pop('color',None)
 else:t['title']['color']='white'

p=ROOT/'doctor_who/doctor_who_cards.cardconjurer'; data=json.loads(p.read_text(encoding='utf-8')); by={e['key']:e['data'] for e in data}
for k,s in LANDS.items(): rebuild_land(by[k],k,s)
for k,r in NONLAND_RULES.items():
 by[k]['text']['rules']['text']=r
 if k=='Morophon, the Boundless': by[k]['text']['rules']['size']=.029
for k,typ,rem in [('Esika, God of the Tree','Enchantment','{W}{U}{B}{R}{G}'),('The Prismatic Bridge','Creature','{1}{G}{G}')]:
 d=by[k]; d['version']='modalRegular'; d['text']['flipsideType'].update({'text':typ,'x':.068,'y':.892,'width':.364,'height':.0391,'size':.0234,'color':'white','oneLine':True,'font':'belerenb'}); d['text']['flipSideReminder'].update({'text':rem,'x':.068,'y':.892,'width':.364,'height':.0391,'size':.0258,'color':'white','oneLine':True,'align':'right'})
assert len(data)==51 and len(by)==51
for k in LANDS:
 r=by[k]['text']['rules']; assert 'noVerticalCenter' not in r and r['x']==.105 and r['width']==.79
for k in ['Flooded Strand','Scalding Tarn','Misty Rainforest','Windswept Heath','Marsh Flats','Polluted Delta','Arid Mesa']:
 ns=[x['name'] for x in by[k]['frames']]; assert sum('Pinline' in n for n in ns)>=2 and sum('Rules' in n for n in ns)>=2
for k in ['Crystal Quarry','The World Tree','Cascading Cataracts','Reflecting Pool','Mana Confluence','Plaza of Heroes']:
 assert any('Multicolored' in x['name'] for x in by[k]['frames'])
for k,d in by.items():
 if k in LANDS:
  for x in d['frames']:
   if 'W' in x['name'].split()[:1] and 'Rules' in x['name']: assert x.get('opacity')==60
assert by['Morophon, the Boundless']['text']['rules']['size']==.029 and '\n{W}{U}{B}{R}{G}' in by['Morophon, the Boundless']['text']['rules']['text']
p.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')

p=ROOT/'derevi/derevi_cards.cardconjurer'; data=json.loads(p.read_text(encoding='utf-8')); by={e['key']:e['data'] for e in data}
for k,d in by.items():
 if 'Land' in d.get('text',{}).get('type',{}).get('text',''): d['text']['rules'].pop('noVerticalCenter',None)
for k in ['Savannah','Tundra']:
 for x in by[k]['frames']:
  if any(m.get('name')=='Rules' for m in x.get('masks',[])) and 'White' in x.get('name',''): x['opacity']=60
for k,d in by.items():
 if 'Land' in d.get('text',{}).get('type',{}).get('text',''): assert 'noVerticalCenter' not in d['text']['rules']
for k in ['Savannah','Tundra']:
 assert any(x.get('opacity')==60 and any(m.get('name')=='Rules' for m in x.get('masks',[])) and 'White' in x.get('name','') for x in by[k]['frames'])
p.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
print('validated Doctor Who',len(LANDS),'lands / 51 faces and Derevi land overrides')
