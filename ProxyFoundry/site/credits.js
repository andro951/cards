/* Preview and controls only. The compiler independently enforces the same provenance rules. */
import {$,$$,esc} from './ui.js';
export function originalArtist(card, face={}) {
  const sf=card.scryfall||card;
  const sfFace=sf.card_faces?.[face.index||0]||sf;
  return String(sfFace.artist?.trim()||sf.artist?.trim()||'');
}
export function composeCredit(original, artistOverride, deckArtist, mode, modificationOverride, deckModification, kind) {
  const artist=kind==='scryfall'||mode==='printing'?original:
    artistOverride!==null&&artistOverride!==undefined?artistOverride:(deckArtist||original);
  const modification=modificationOverride!==null&&modificationOverride!==undefined?modificationOverride:(deckModification||'');
  return [String(artist||'').trim(),String(modification||'').trim()].filter(Boolean).join(' · ');
}
function stem(value){return String(value).normalize('NFKD').replace(/[\u0300-\u036f]/g,'').replace(/[Ææ]/g,'ae').replace(/[Œœ]/g,'oe').replace(/['’]/g,'').replace(/[^A-Za-z0-9]+/g,'_').replace(/^_|_$/g,'').toLowerCase();}
export function artworkKind(deck, card, face, artOverride) {
  if(artOverride)return 'custom';
  const source=deck.settings.source||{},mode=source.mode||'scryfall';
  const sfFace=card.scryfall.card_faces?.[face.index||0]||card.scryfall;
  const library=deck.settings.useLandLibrary&&String(sfFace.type_line||'').split(' — ')[0].includes('Land');
  if(mode==='scryfall'&&!library)return 'scryfall';
  if(mode==='local'&&source.localFiles?.[stem(face.name||sfFace.name)])return 'custom';
  if(mode==='local'&&!library&&source.fallback!==false)return 'scryfall';
  if(deck.status!=='draft'&&face.compiled?.artOrigin)return face.compiled.artOrigin==='Scryfall selected printing'?'scryfall':'custom';
  return 'pending';
}
export function creditFields(deck,card,face) {
  return `<section class="credit-fields"><label class="field"><span>Original printing artist</span><output id="printing-artist" class="credit-original">${esc(originalArtist(card,face)||'Not supplied by Scryfall')}</output><small>This is the credit from the selected printing, specific to this face.</small></label>
  <label class="field"><span>Artist for this custom artwork <small>optional override</small></span><input id="face-artist" maxlength="300" value="${esc(face.artistOverride??'')}" placeholder="${esc(deck.settings.artist||originalArtist(card,face)||'Use the deck default')}"><small id="artist-source-note"></small></label>
  <label class="check-line"><input type="checkbox" id="use-printing-artist" ${face.artistCreditMode==='printing'?'checked':''}><span>Use the original printing artist for this custom image<small>Useful for uploaded art that was extended or modified from that printing.</small></span></label>
  <label class="check-line"><input type="checkbox" id="blank-credit" ${face.artistOverride===''?'checked':''}><span>Intentionally leave the custom artist blank</span></label>
  <label class="field"><span>Modification credit <small>optional</small></span><input id="face-modification" maxlength="160" value="${esc(face.modificationCreditOverride??'')}" placeholder="${esc(deck.settings.modificationCredit?'Deck default: '+deck.settings.modificationCredit:'e.g. Modified by ChatGPT')}"><small>Appended after the original/custom artist in the artist spot, not in the rules or footer note.</small></label>
  <label class="check-line"><input type="checkbox" id="no-modification" ${face.modificationCreditOverride===''?'checked':''}><span>No modification credit on this face<small>Overrides the deck-wide modification text.</small></span></label>
  <div class="credit-preview" aria-live="polite"><span class="eyebrow">PRINTED ARTIST LINE</span><strong id="face-credit-preview"></strong><small id="credit-preview-note"></small></div></section>`;
}
export function bindCreditFields(root,deck,card,face,getArtOverride){
  const original=originalArtist(card,face);
  const values=()=>({
    artistOverride:$('#blank-credit',root).checked?'':($('#face-artist',root).value.trim()||null),
    artistCreditMode:$('#use-printing-artist',root).checked?'printing':null,
    modificationCreditOverride:$('#no-modification',root).checked?'':($('#face-modification',root).value.trim()||null)
  });
  function refresh(){
    const kind=artworkKind(deck,card,face,getArtOverride()),locked=kind==='scryfall';
    const value=values();
    $('#face-artist',root).disabled=locked||value.artistCreditMode==='printing'||$('#blank-credit',root).checked;
    $('#use-printing-artist',root).disabled=locked;
    $('#blank-credit',root).disabled=locked||value.artistCreditMode==='printing';
    $('#face-modification',root).disabled=$('#no-modification',root).checked;
    $('#artist-source-note',root).textContent=locked?'Scryfall artwork keeps its real artist. Custom-art overrides do not replace or hide this credit.':
      'Applies only to your custom image. Leave blank to inherit the deck’s custom-art artist.';
    const text=composeCredit(original,value.artistOverride,deck.settings.artist,value.artistCreditMode,value.modificationCreditOverride,deck.settings.modificationCredit,kind);
    $('#face-credit-preview',root).textContent=text||'(No credit supplied)';
    $('#credit-preview-note',root).textContent=kind==='pending'?'Custom-art preview; the resolved source is confirmed during generation. Any Scryfall fallback will keep its original artist.':
      locked&&!original?'Scryfall did not supply an artist. No custom-art artist will be substituted.':'The original Scryfall metadata is kept separately and never overwritten.';
  }
  $$('input',root.querySelector('.credit-fields')).forEach(input=>{input.addEventListener('input',refresh);input.addEventListener('change',refresh);});
  refresh();return {values,refresh};
}
