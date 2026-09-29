/* Back preview uses the exact server-produced PNG that will be packaged for print. */
import {$,$$,esc,state,api,uploadImage,attempt,asset} from './ui.js';

export function mountBackPicker(root,initial,onChange,{onBusy=()=>{},allowNone=false}={}) {
  let current=structuredClone(initial),busy=false,warnings=[];
  const catalog=state.bootstrap.backs;
  if(!catalog)throw new Error('Back designs were not loaded. Reload the workspace page.');
  function mode(){return current.backDesign?.mode||(current.backAsset?'custom':'none');}
  function commit(next){current=next;draw();onChange(structuredClone(next));}
  async function upload(kind){
    const input=document.createElement('input');input.type='file';input.accept='image/png,image/jpeg,image/webp,image/gif,.svg';
    const file=await new Promise(resolve=>{input.onchange=()=>resolve(input.files[0]||null);input.oncancel=()=>resolve(null);input.click();});
    if(!file||busy)return;
    busy=true;warnings=[];onBusy(true);draw();
    try {
      const image=await uploadImage(file,{back:kind==='custom'});
      if(kind==='icon'){
        const output=await api('/api/backs/compose',{iconAsset:image.id});
        warnings=output.placement.warnings||[];
        commit({backAsset:output.id,backDesign:output.design});
      }else commit({backAsset:image.id,backDesign:{mode:'custom'}});
    }finally{busy=false;onBusy(false);if(root.isConnected)draw();}
  }
  function draw(){
    const selected=mode(),isIcon=selected==='icon',box=catalog.iconBounds,[bw,bh]=catalog.blankSize;
    const info={default:'Bulk Proxy Forge · default',icon:'Your icon on the forge back',custom:'Your complete back',none:'No back selected'}[selected];
    const url=current.backAsset?asset(current.backAsset):'';
    root.innerHTML=`<div class="back-mode-choices" role="group" aria-label="Card-back design">
      <button type="button" class="back-mode ${selected==='default'?'selected':''}" data-back-action="default" aria-pressed="${selected==='default'}" ${busy?'disabled':''}><b>Default Back</b><small>Bulk Proxy Forge back</small></button>
      <button type="button" class="back-mode ${isIcon?'selected':''}" data-back-action="icon" aria-pressed="${isIcon}" ${busy?'disabled':''}><b>Upload Icon</b><small>Your icon on our back</small></button>
      <button type="button" class="back-mode ${selected==='custom'?'selected':''}" data-back-action="custom" aria-pressed="${selected==='custom'}" ${busy?'disabled':''}><b>Upload Full Back</b><small>Your custom back</small></button>
    </div>
    <div class="back-design-preview"><div class="back-preview-canvas" style="aspect-ratio:${isIcon?bw+'/ '+bh:'auto'}">
      ${url?`<img src="${esc(url)}" alt="${esc(info)}" data-back-preview>`:'<div class="back-none-preview">Choose a back</div>'}
      ${isIcon?`<span class="back-icon-guide hidden" style="left:${100*box.x/bw}%;top:${100*box.y/bh}%;width:${100*box.size/bw}%;height:${100*box.size/bh}%" aria-hidden="true"></span>`:''}
      </div><div class="back-preview-detail"><b>${esc(info)}</b>${selected==='custom'?'<p class="notice">Do not upload the official Magic card back for this proxy-print workflow.</p>':''}
      ${isIcon?`<label class="check-line"><input type="checkbox" data-back-guide><span>Show safe icon area<small>${box.size} × ${box.size} pixels · preview only</small></span></label>`:''}
      <p class="subtitle-line">${busy?'Processing image…':''}</p>
      </div></div>
      ${warnings.map(w=>`<div class="notice">${esc(w)}</div>`).join('')}`;
    $$('[data-back-action]',root).forEach(button=>button.onclick=()=>{
      const action=button.dataset.backAction;
      if(action==='default'){warnings=[];commit({backAsset:catalog.default.id,backDesign:{mode:'default',template:'forge-default-v1'}});}
      else if(action==='none'){warnings=[];commit({backAsset:null,backDesign:{mode:'none'}});}
      else attempt(()=>upload(action));
    });
    const guide=$('[data-back-guide]',root);
    if(guide)guide.onchange=()=>$('[class~="back-icon-guide"]',root).classList.toggle('hidden',!guide.checked);
  }
  draw();
  return {set(value){current=structuredClone(value);warnings=[];draw();},get(){return structuredClone(current);},isBusy(){return busy;}};
}
