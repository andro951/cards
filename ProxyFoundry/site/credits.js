/* Preview and controls only. The compiler independently enforces the same provenance rules. */
import {$,$$,esc,api,modal,closeModal,errorBox} from './ui.js';
export function originalArtist(card, face={}) {
  if(face.selectedArtPrintingId&&face.selectedArtArtist)return String(face.selectedArtArtist).trim();
  const sf=card.scryfall||card;
  const sfFace=sf.card_faces?.[face.index||0]||sf;
  return String(sfFace.artist?.trim()||sf.artist?.trim()||'');
}
export function composeCredit(original, artistOverride, deckArtist, mode, kind) {
  const artist=kind==='scryfall'||mode==='printing'?original:
    artistOverride!==null&&artistOverride!==undefined?artistOverride:(deckArtist||'');
  const name=String(artist||'').trim();
  if(kind==='scryfall')return name?name+' (Scryfall) • Art © respective rights holders':'Scryfall • Art © respective rights holders';
  return name;
}
function stem(value){return String(value).normalize('NFKD').replace(/[\u0300-\u036f]/g,'').replace(/[Ææ]/g,'ae').replace(/[Œœ]/g,'oe').replace(/['’]/g,'').replace(/[^A-Za-z0-9]+/g,'_').replace(/^_|_$/g,'').toLowerCase();}
export function artworkKind(deck, card, face, artOverride) {
  if(artOverride)return 'custom';
  if(face.selectedArtPrintingId)return 'scryfall';
  const source=deck.settings.source||{},mode=source.mode||'scryfall';
  const sfFace=card.scryfall.card_faces?.[face.index||0]||card.scryfall;
  const identity=(sfFace.oracle_id||card.scryfall.oracle_id||card.scryfall.id||card.id)+'/'+(sfFace.name||face.name);
  if(deck.settings.artDefaults?.includes(identity))return 'scryfall';
  if(mode==='scryfall')return 'scryfall';
  if(mode==='local'&&source.localFiles?.[stem(face.name||sfFace.name)])return 'custom';
  if(mode==='local'&&Object.entries(source.localNames||{}).some(([key,filename])=>source.localFiles?.[key]&&(filename===face.artFilename||String(filename).toLowerCase().includes(String(sfFace.oracle_id||card.scryfall.oracle_id||'invalid-uuid').toLowerCase())||stem(filename.replace(/\.[^.]+$/,'').replace(/^\d+_/,''))===stem(face.name||sfFace.name))))return 'custom';
  if(mode==='local'&&source.fallback!==false)return 'scryfall';
  if(deck.status!=='draft'&&face.compiled?.artOrigin)return face.compiled.artOrigin==='Scryfall selected printing'?'scryfall':'custom';
  return 'pending';
}
function mayUseCustomArtwork(deck,card,face){
  const kind=artworkKind(deck,card,face,face.artOverride);
  if(kind==='custom')return true;
  if(kind==='scryfall')return false;
  const source=deck.settings?.source||{};
  if(source.mode==='github'&&String(source.githubFolder||'').trim())return true;
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
//Rebase only the explicit credit edit when background work advances the deck revision.
async function saveCustomArtCredit(deckId,path,patch){
  for(let attempt=0;attempt<3;attempt++){
    const current=await api('/api/decks/'+deckId);
    const result=await api(path,{...patch,revision:current.revision}).then(
      deck=>({deck}),error=>({error}));
    if(!result.error)
      return result.deck;

    if(result.error.status!==409||attempt===2)
      throw result.error;
  }
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
    const host=modal('Credit the custom artwork',`<p class="muted">Bulk Proxy Forge cannot determine who created a custom image from the image itself, so it will not assume the selected printing’s illustrator. Choose how you want to credit the custom artwork before generating.</p><label class="check-line"><input type="radio" name="custom-artist-mode" id="custom-artist-one" value="one" checked><span>One artist for all custom artwork<small>Saved as this deck’s custom-art artist. Scryfall fallback images still keep their real printing artist.</small></span></label><div id="custom-artist-one-fields"><label class="field"><span>Artist name</span><input id="custom-artist-all" maxlength="300" placeholder="Artist name"></label></div><label class="check-line"><input type="radio" name="custom-artist-mode" id="custom-artist-each" value="each"><span>Specify the artist for each card<small>Useful when the custom images came from different artists.</small></span></label><div id="custom-artist-each-fields" class="hidden"><div class="stack">${rows}</div></div><div class="notice info">These credits apply only when custom artwork is actually used. If a card falls back to Scryfall artwork, its selected printing artist remains authoritative.</div>`,{size:'large',dismissible:false,footer:'<button class="button primary" id="custom-artist-apply">Continue</button>',onClose:()=>completed});
    const refresh=()=>{const each=$('#custom-artist-each',host).checked;$('#custom-artist-one-fields',host).classList.toggle('hidden',each);$('#custom-artist-each-fields',host).classList.toggle('hidden',!each);};
    $$('input[name="custom-artist-mode"]',host).forEach(x=>x.onchange=refresh);refresh();
    $('#custom-artist-apply',host).onclick=async()=>{
      const button=$('#custom-artist-apply',host);button.disabled=true;
      try{
        let current=deck;
        if($('#custom-artist-one',host).checked){
          const artist=$('#custom-artist-all',host).value.trim();
          if(!artist)throw new Error('Enter the artist name for the custom artwork.');
          current=await saveCustomArtCredit(deck.id,'/api/decks/'+deck.id+'/save',{settings:{artist}});
        }else{
          const artists=$$('[data-custom-artist]',host).map(input=>input.value.trim());
          const blank=artists.findIndex(value=>!value);
          if(blank>=0)throw new Error('Enter an artist for '+missing[blank].card.name+'.');
          for(let i=0;i<missing.length;i++){
            const item=missing[i];
            current=await saveCustomArtCredit(deck.id,'/api/decks/'+deck.id+'/cards/'+item.card.id,{faceId:item.face.id,artistOverride:artists[i]});
            deck=current;
          }
        }
        completed=true;closeModal({completed:true});resolve(current);
      }catch(e){errorBox($('.modal-body',host),e.message);button.disabled=false;}
    };
  });
}
export function creditFields(deck,card,face) {
  return `<section class="credit-fields"><label class="field"><span>Original printing artist</span><output id="printing-artist" class="credit-original">${esc(originalArtist(card,face)||'Not supplied by Scryfall')}</output><small>This is the credit from the selected printing, specific to this face.</small></label>
  <label class="field"><span>Artist for this custom artwork <small>optional override</small></span><input id="face-artist" maxlength="300" value="${esc(face.artistOverride??'')}" placeholder="${esc(deck.settings.artist?'Deck default: '+deck.settings.artist:'Enter the custom artwork artist')}"><small id="artist-source-note"></small></label>
  <label class="check-line"><input type="checkbox" id="use-printing-artist" ${face.artistCreditMode==='printing'?'checked':''}><span>Use the original printing artist for this custom image<small>Use this when the custom image should keep the selected printing’s artist credit.</small></span></label>
  <label class="check-line"><input type="checkbox" id="blank-credit" ${face.artistOverride===''?'checked':''}><span>Intentionally leave the custom artist blank</span></label>
  <div class="credit-preview" aria-live="polite"><span class="eyebrow">PRINTED ARTIST LINE</span><strong id="face-credit-preview"></strong><small id="credit-preview-note"></small></div></section>`;
}
export function bindCreditFields(root,deck,card,face,getArtOverride,getCurrentFace=()=>face){
  const values=()=>({
    artistOverride:$('#blank-credit',root).checked?'':($('#face-artist',root).value.trim()||null),
    artistCreditMode:$('#use-printing-artist',root).checked?'printing':null
  });
  function refresh(){
    face=getCurrentFace();
    const original=originalArtist(card,face);
    $('#printing-artist',root).textContent=original||'Not supplied by Scryfall';
    const kind=artworkKind(deck,card,face,getArtOverride()),locked=kind==='scryfall';
    const value=values();
    $('#face-artist',root).disabled=locked||value.artistCreditMode==='printing'||$('#blank-credit',root).checked;
    $('#use-printing-artist',root).disabled=locked;
    $('#blank-credit',root).disabled=locked||value.artistCreditMode==='printing';
    $('#artist-source-note',root).textContent=locked?'Scryfall artwork keeps its real artist. Custom-art overrides do not replace or hide this credit.':
      'Applies only to your custom image. Leave blank to inherit the deck’s custom-art artist. If neither is set, Generate images will ask before rendering.';
    const text=composeCredit(original,value.artistOverride,deck.settings.artist,value.artistCreditMode,kind);
    $('#face-credit-preview',root).textContent=text||'(No credit supplied)';
    $('#credit-preview-note',root).textContent=kind==='pending'?'Custom-art preview; the resolved source is confirmed during generation. Any Scryfall fallback will keep its original artist.':
      locked&&!original?'Scryfall did not supply an artist. No custom-art artist will be substituted.':'The original Scryfall metadata is kept separately and never overwritten.';
  }
  $$('input',root.querySelector('.credit-fields')).forEach(input=>{input.addEventListener('input',refresh);input.addEventListener('change',refresh);});
  refresh();return {values,refresh};
}