import {$,modal,closeModal,state} from './ui.js';
import {renderTemplatePreviews} from './render.js';

export function frameChoices(group,legendary=false){
  const ordinary=['standard','legendary','land','legendary-land','basic-land'].includes(group);
  return state.templates.filter(template=>
    (template.id==='auto'||(template.groups==='ordinary'?ordinary:Array.isArray(template.groups)&&template.groups.includes(group)))
    &&(!legendary||template.legendary)
  );
}

export function openFramePicker(deck,group,settings,cardData,selected,onSelect){
  const choices=frameChoices(group,['legendary','legendary-land'].includes(group));
  const dialog=modal('Choose a frame for '+(state.bootstrap.groups[group]||group),'',{size:'large'});
  const body=$('.modal-body',dialog);
  const intro=document.createElement('p');
  intro.textContent='Building '+(deck.cards.find(card=>card.faces.some(face=>face.group===group))?.name||'a card')+' with each compatible frame. Select the preview you want.';
  body.append(intro);

  const status=document.createElement('p');
  status.setAttribute('role','status');
  status.textContent='Preparing native card previews…';
  body.append(status);

  const gallery=document.createElement('div');
  gallery.style.display='flex';
  gallery.style.flexWrap='wrap';
  gallery.style.gap='16px';
  body.append(gallery);

  const rows=new Map();
  const urls=[];
  for(const choice of choices){
    const button=document.createElement('button');
    button.type='button';
    button.className='button';
    button.disabled=true;
    button.style.width='190px';
    button.style.display='flex';
    button.style.flexDirection='column';
    button.style.alignItems='center';
    button.style.gap='8px';
    button.setAttribute('aria-label','Select '+choice.name);

    const image=document.createElement('img');
    image.alt='Preview of '+choice.name;
    image.style.width='170px';
    image.style.maxWidth='100%';
    image.hidden=true;
    button.append(image);

    const label=document.createElement('strong');
    label.textContent=choice.name+(choice.id===selected?' · selected':'');
    button.append(label);

    const detail=document.createElement('small');
    detail.textContent='Rendering…';
    button.append(detail);
    button.onclick=()=>{
      onSelect(choice.id);
      closeModal();
    };
    gallery.append(button);
    rows.set(choice.id,{button,image,detail});
  }

  renderTemplatePreviews(deck.id,group,settings,cardData,(target,blob)=>{
    const url=URL.createObjectURL(blob);
    urls.push(url);
    if(!dialog.isConnected){
      URL.revokeObjectURL(url);
      return;
    }
    const row=rows.get(target.choice);
    if(!row)return;
    row.image.src=url;
    row.image.hidden=false;
    row.detail.textContent='Native preview ready';
    row.button.disabled=false;
  }).then(plan=>{
    if(!dialog.isConnected)return;
    status.textContent='Rendered '+plan.targets.length+' frame previews using '+plan.sample+'.';
    for(const [choice,message] of Object.entries(plan.previewErrors||{})){
      const row=rows.get(choice);
      if(row)row.detail.textContent=message;
    }
  }).catch(error=>{
    if(dialog.isConnected)status.textContent='Could not build previews: '+error.message;
  });

  const observer=new MutationObserver(()=>{
    if(dialog.isConnected)return;
    observer.disconnect();
    for(const url of urls)URL.revokeObjectURL(url);
  });
  observer.observe(document.body,{childList:true,subtree:true});
}
