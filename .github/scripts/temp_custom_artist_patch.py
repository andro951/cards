from pathlib import Path


def replace(path, old, new, count=1):
    p=Path(path); text=p.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'missing expected text in {path}: {old[:240]!r}')
    p.write_text(text.replace(old,new,count),encoding='utf-8')


replace('ProxyFoundry/foundry/domain.py',
    "PIPELINE_VERSION='card-tools-v58/credits-v1/pipeline-v8'",
    "PIPELINE_VERSION='card-tools-v58/credits-v1/pipeline-v9'")

replace('ProxyFoundry/foundry/credits.py',
    "    else:\n        artist, source = original, 'printing'\n",
    "    else:\n        # Custom artwork has unknown provenance unless the user explicitly\n        # supplies a custom-art artist or chooses the printing artist. Never\n        # silently attribute unrelated custom art to the Scryfall illustrator.\n        artist, source = '', 'missing-custom'\n")
replace('ProxyFoundry/foundry/credits.py',
    "            'source': source, 'locked': source_is_scryfall,\n            'missingOriginalArtist': source in {'scryfall', 'printing'} and not original}\n",
    "            'source': source, 'locked': source_is_scryfall,\n            'missingOriginalArtist': source in {'scryfall', 'printing'} and not original,\n            'missingCustomArtist': source == 'missing-custom'}\n")

replace('ProxyFoundry/foundry/compiler.py',
    "        credit=resolve_credit(sf,face,options,settings,art_origin)\n        artist=credit['display']\n",
    "        credit=resolve_credit(sf,face,options,settings,art_origin)\n        if credit.get('missingCustomArtist'):\n            raise ValidationError('Custom artwork needs an artist credit. Set one artist for all custom artwork or set this card’s artist before generating.')\n        artist=credit['display']\n")

p=Path('ProxyFoundry/site/credits.js')
text=p.read_text(encoding='utf-8')
text=text.replace("import {$,$$,esc} from './ui.js';",
                  "import {$,$$,esc,api,modal,closeModal,errorBox} from './ui.js';",1)
text=text.replace(
    "  const artist=kind==='scryfall'||mode==='printing'?original:\n    artistOverride!==null&&artistOverride!==undefined?artistOverride:(deckArtist||original);",
    "  const artist=kind==='scryfall'||mode==='printing'?original:\n    artistOverride!==null&&artistOverride!==undefined?artistOverride:(deckArtist||'');",1)
marker="export function creditFields(deck,card,face) {\n"
if marker not in text: raise SystemExit('credits.js insertion marker missing')
helper=r'''function isLandFace(card,face){
  const sf=card.scryfall||card,sfFace=sf.card_faces?.[face.index||0]||sf;
  return String(sfFace.type_line||sf.type_line||'').split(' — ')[0].includes('Land');
}
function mayUseCustomArtwork(deck,card,face){
  const kind=artworkKind(deck,card,face,face.artOverride);
  if(kind==='custom')return true;
  if(kind==='scryfall')return false;
  const source=deck.settings?.source||{};
  if(source.mode==='github'&&String(source.githubFolder||'').trim())return true;
  if(deck.settings?.useLandLibrary&&isLandFace(card,face))return true;
  return false;
}
export function missingCustomArtistFaces(deck){
  if(String(deck.settings?.artist||'').trim())return [];
  const missing=[];
  for(const card of deck.cards||[])for(const face of card.faces||[]){
    if(!mayUseCustomArtwork(deck,card,face))continue;
    if(face.artistCreditMode==='printing')continue;
    if(face.artistOverride===''||(typeof face.artistOverride==='string'&&face.artistOverride.trim()))continue;
    missing.push({card,face});
  }
  return missing;
}
export function ensureCustomArtCredits(deck){
  const missing=missingCustomArtistFaces(deck);
  if(!missing.length)return Promise.resolve(deck);
  return new Promise(resolve=>{
    let completed=false;
    const rows=missing.map((item,i)=>{
      const faceLabel=item.card.faces?.length>1&&item.face.name!==item.card.name?' · '+item.face.name:'';
      return `<label class="field"><span>${esc(item.card.name+faceLabel)}</span><input maxlength="300" data-custom-artist="${i}" placeholder="Artist name"></label>`;
    }).join('');
    const host=modal('Credit the custom artwork',`<p class="muted">Bulk Proxy Forge cannot determine who created a custom image from the image itself, so it will not assume the selected printing’s illustrator. Choose how you want to credit the custom artwork before generating.</p><label class="check-line"><input type="radio" name="custom-artist-mode" id="custom-artist-one" value="one" checked><span>One artist for all custom artwork<small>Saved as this deck’s custom-art artist. Scryfall fallback images still keep their real printing artist.</small></span></label><div id="custom-artist-one-fields"><label class="field"><span>Artist name</span><input id="custom-artist-all" maxlength="300" placeholder="Artist name"></label></div><label class="check-line"><input type="radio" name="custom-artist-mode" id="custom-artist-each" value="each"><span>Specify the artist for each card<small>Useful when the custom images came from different artists.</small></span></label><div id="custom-artist-each-fields" class="hidden"><div class="stack">${rows}</div></div><div class="notice info">These credits apply only when custom artwork is actually used. If a card falls back to Scryfall artwork, its selected printing artist remains authoritative. You can also cancel and use the advanced per-card “Use original printing artist” option for modified original art.</div>`,{size:'large',footer:'<button class="button quiet" id="custom-artist-cancel">Cancel</button><button class="button primary" id="custom-artist-apply">Save artist credits & continue</button>',onClose:()=>{if(!completed)resolve(null);return true;}});
    const refresh=()=>{const each=$('#custom-artist-each',host).checked;$('#custom-artist-one-fields',host).classList.toggle('hidden',each);$('#custom-artist-each-fields',host).classList.toggle('hidden',!each);};
    $$('input[name="custom-artist-mode"]',host).forEach(x=>x.onchange=refresh);refresh();
    $('#custom-artist-cancel',host).onclick=closeModal;
    $('#custom-artist-apply',host).onclick=async()=>{
      const button=$('#custom-artist-apply',host);button.disabled=true;
      try{
        let current=deck;
        if($('#custom-artist-one',host).checked){
          const artist=$('#custom-artist-all',host).value.trim();
          if(!artist)throw new Error('Enter the artist name for the custom artwork.');
          current=await api('/api/decks/'+deck.id+'/save',{revision:deck.revision,settings:{artist}});
        }else{
          const artists=$$('[data-custom-artist]',host).map(input=>input.value.trim());
          const blank=artists.findIndex(value=>!value);
          if(blank>=0)throw new Error('Enter an artist for '+missing[blank].card.name+'.');
          for(let i=0;i<missing.length;i++){
            const item=missing[i];
            current=await api('/api/decks/'+deck.id+'/cards/'+item.card.id,{revision:current.revision,faceId:item.face.id,artistOverride:artists[i]});
          }
        }
        completed=true;closeModal();resolve(current);
      }catch(e){errorBox($('.modal-body',host),e.message);button.disabled=false;}
    };
  });
}
'''
text=text.replace(marker,helper+marker,1)
text=text.replace(
    "placeholder=\"${esc(deck.settings.artist||originalArtist(card,face)||'Use the deck default')}\"",
    "placeholder=\"${esc(deck.settings.artist?'Deck default: '+deck.settings.artist:'Enter the custom artwork artist')}\"",1)
text=text.replace(
    "'Applies only to your custom image. Leave blank to inherit the deck’s custom-art artist.';",
    "'Applies only to your custom image. Leave blank to inherit the deck’s custom-art artist. If neither is set, Generate images will ask before rendering.';",1)
p.write_text(text,encoding='utf-8')

replace('ProxyFoundry/site/deck.js',
    "import {creditFields,bindCreditFields} from './credits.js';",
    "import {creditFields,bindCreditFields,ensureCustomArtCredits} from './credits.js';")
replace('ProxyFoundry/site/deck.js',
    "  if(!rarities.every(r=>d.settings.symbols?.[r])){nav('deck/'+d.id+'/setup');throw new Error('Set up your four rarity symbols first.');}\n  await renderDecks([d.id],{force:!!d.upgradeRequired,onUpdate:async()=>{if(state.route==='deck'&&state.activeDeck?.id===d.id)await showDeck(d.id,'cards');}});",
    "  if(!rarities.every(r=>d.settings.symbols?.[r])){nav('deck/'+d.id+'/setup');throw new Error('Set up your four rarity symbols first.');}\n  d=await ensureCustomArtCredits(d);if(!d)return;\n  await renderDecks([d.id],{force:!!d.upgradeRequired,onUpdate:async()=>{if(state.route==='deck'&&state.activeDeck?.id===d.id)await showDeck(d.id,'cards');}});")

replace('ProxyFoundry/site/setup.js',
    "<label class=\"field\"><span>Artist for custom artwork in this deck</span><input id=\"deck-artist\" value=\"${esc(s.artist||'')}\" placeholder=\"Use each selected printing’s original artist\"><small>Used only for custom artwork. Scryfall originals and fallback images always keep the real printing artist. Leave blank to inherit the printing artist for custom art too.</small></label>",
    "<label class=\"field\"><span>Artist for custom artwork in this deck</span><input id=\"deck-artist\" value=\"${esc(s.artist||'')}\" placeholder=\"Artist name for your custom artwork\"><small>Used only for custom artwork. Scryfall originals and fallback images always keep the real printing artist. If you leave this blank, Generate images will ask whether one artist applies to all custom art or whether you want to enter artists per card.</small></label>")

p=Path('ProxyFoundry/tests/test_credits.py')
text=p.read_text(encoding='utf-8')
addition='''\n\ndef test_custom_art_without_credit_never_assumes_printing_artist():\n    c=resolve_credit(SF,FACE,{}, {},'uploaded override')\n    assert c['artist']=='' and c['display']==''\n    assert c['source']=='missing-custom' and c['missingCustomArtist']\n\ndef test_explicit_blank_custom_artist_is_intentional_not_missing():\n    c=resolve_credit(SF,FACE,{'artistOverride':''}, {},'uploaded override')\n    assert c['artist']=='' and c['source']=='card'\n    assert not c['missingCustomArtist']\n'''
if 'test_custom_art_without_credit_never_assumes_printing_artist' not in text:
    p.write_text(text+addition,encoding='utf-8')

Path('ProxyFoundry/tests/test_custom_artist_prompt_contract.py').write_text('''from pathlib import Path\n\nROOT=Path(__file__).resolve().parents[1]\n\ndef test_custom_artist_prompt_and_no_printing_fallback_contract():\n    credits=(ROOT/'site/credits.js').read_text(encoding='utf-8')\n    deck=(ROOT/'site/deck.js').read_text(encoding='utf-8')\n    setup=(ROOT/'site/setup.js').read_text(encoding='utf-8')\n    assert 'ensureCustomArtCredits' in credits\n    assert 'One artist for all custom artwork' in credits\n    assert 'Specify the artist for each card' in credits\n    assert \"(deckArtist||'')\" in credits\n    assert 'await ensureCustomArtCredits(d)' in deck\n    assert 'Generate images will ask' in setup\n''',encoding='utf-8')
