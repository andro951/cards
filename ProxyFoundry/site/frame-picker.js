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

  const controller=new AbortController();
  const rows=new Map();
  const urls=[];
  const byId=new Map(choices.map(choice=>[choice.id,choice]));
  function choiceButton(choice){
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
    const label=document.createElement('strong');
    label.textContent=choice.name+(choice.id===selected?' · selected':'');
    button.append(label);
    button.onclick=()=>{onSelect(choice.id);closeModal();};
    return button;
  }
  for(const choice of choices){
    const button=choiceButton(choice);
    const detail=document.createElement('small');
    detail.textContent='Preparing preview…';
    button.append(detail);
    gallery.append(button);
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
    row.detail.textContent=row.buttons.length>1?'Same frame for this card · choose below':'Native preview ready';
    for(const button of row.buttons)button.disabled=false;
  },plan=>{
    gallery.replaceChildren();
    for(const target of plan.targets){
      const represented=(target.choices||[target.choice]).map(id=>byId.get(id)).filter(Boolean);
      if(!represented.length)continue;
      const tile=document.createElement('div');
      tile.style.display='flex';
      tile.style.flexDirection='column';
      tile.style.gap='6px';
      const buttons=represented.map(choice=>choiceButton(choice));
      const image=document.createElement('img');
      image.alt='Preview of '+represented.map(choice=>choice.name).join(' or ');
      image.style.width='170px';
      image.style.maxWidth='100%';
      image.hidden=true;
      buttons[0].prepend(image);
      const detail=document.createElement('small');
      detail.textContent='Rendering…';
      buttons[0].append(detail);
      tile.append(...buttons);
      gallery.append(tile);
      rows.set(target.choice,{buttons,image,detail});
    }
    for(const [id,message] of Object.entries(plan.previewErrors||{})){
      const choice=byId.get(id);
      if(!choice)continue;
      const button=choiceButton(choice);
      const detail=document.createElement('small');
      detail.textContent=message;
      button.append(detail);
      gallery.append(button);
    }
  },controller.signal).then(plan=>{
    if(!plan)return;
    if(!dialog.isConnected)return;
    status.textContent='Rendered '+plan.targets.length+' distinct frame previews using '+plan.sample+'.';
  }).catch(error=>{
    if(dialog.isConnected)status.textContent='Could not build previews: '+error.message;
  });

  const observer=new MutationObserver(()=>{
    if(dialog.isConnected)return;
    observer.disconnect();
    controller.abort();
    for(const url of urls)URL.revokeObjectURL(url);
  });
  observer.observe(document.body,{childList:true,subtree:true});
}
