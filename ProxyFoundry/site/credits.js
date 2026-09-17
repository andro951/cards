/* Preview and controls only. The compiler independently enforces the same provenance rules. */
import {$,$$,esc,api,modal,closeModal,errorBox} from './ui.js';
export function originalArtist(card, face={}) {
  const sf=card.scryfall||card;
  const sfFace=sf.card_faces?.[face.index||0]||sf;
  return String(sfFace.artist?.trim()||sf.artist?.trim()||'');
}
export function composeCredit(original, artistOverride, deckArtist, mode, modificationOverride, deckModification, kind) {
  const artist=kind==='scryfall'||mode==='printing'?original:
    artistOverride!==null&&artistOverride!==undefined?artistOverride:(deckArtist||'');
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
function isLandFace(card,face){
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
export function creditFields(deck,card,face) {
  return `<section class="credit-fields"><label class="field"><span>Original printing artist</span><output id="printing-artist" class="credit-original">${esc(originalArtist(card,face)||'Not supplied by Scryfall')}</output><small>This is the credit from the selected printing, specific to this face.</small></label>
  <label class="field"><span>Artist for this custom artwork <small>optional override</small></span><input id="face-artist" maxlength="300" value="${esc(face.artistOverride??'')}" placeholder="${esc(deck.settings.artist?'Deck default: '+deck.settings.artist:'Enter the custom artwork artist')}"><small id="artist-source-note"></small></label>
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
      'Applies only to your custom image. Leave blank to inherit the deck’s custom-art artist. If neither is set, Generate images will ask before rendering.';
    const text=composeCredit(original,value.artistOverride,deck.settings.artist,value.artistCreditMode,value.modificationCreditOverride,deck.settings.modificationCredit,kind);
    $('#face-credit-preview',root).textContent=text||'(No credit supplied)';
    $('#credit-preview-note',root).textContent=kind==='pending'?'Custom-art preview; the resolved source is confirmed during generation. Any Scryfall fallback will keep its original artist.':
      locked&&!original?'Scryfall did not supply an artist. No custom-art artist will be substituted.':'The original Scryfall metadata is kept separately and never overwritten.';
  }
  $$('input',root.querySelector('.credit-fields')).forEach(input=>{input.addEventListener('input',refresh);input.addEventListener('change',refresh);});
  refresh();return {values,refresh};
}
