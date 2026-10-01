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
  const status=document.createElement('p');
  status.setAttribute('role','status');
  status.textContent='Building frame previews… You can choose a frame now.';
  body.append(status);

  const gallery=document.createElement('div');
  gallery.style.display='flex';
  gallery.style.flexWrap='wrap';
  gallery.style.gap='16px';
  body.append(gallery);

  const controller=new AbortController();
  const rows=new Map();
  const previewBlobs=new Map();
  const urls=[];
  const byId=new Map(choices.map(choice=>[choice.id,choice]));
  function selectChoice(choice){
    controller.abort();
    onSelect(choice.id,previewBlobs.get(choice.id));
    closeModal();
  }
  function choiceButton(choice){
    const button=document.createElement('button');
    button.type='button';
    button.className='button';
    button.style.width='170px';
    button.style.display='flex';
    button.style.flexDirection='column';
    button.style.alignItems='center';
    button.style.gap='8px';
    button.setAttribute('aria-label','Select '+choice.name);
    const label=document.createElement('strong');
    label.textContent=choice.name+(choice.id===selected?' · selected':'');
    button.append(label);
    button.onclick=()=>selectChoice(choice);
    return button;
  }
  for(const choice of choices){
    gallery.append(choiceButton(choice));
  }
  const zoom=document.createElement('div');
  zoom.style.cssText='position:fixed;inset:0;z-index:10000;background:#0c0c0cee;display:flex;align-items:center;justify-content:center;cursor:zoom-out';
  zoom.onclick=()=>zoom.remove();
  const zoomImage=document.createElement('img');
  zoomImage.alt='Enlarged frame preview';
  zoomImage.style.cssText='max-height:94vh;max-width:94vw;object-fit:contain';
  zoom.append(zoomImage);

  renderTemplatePreviews(deck.id,group,settings,cardData,(target,blob)=>{
    const url=URL.createObjectURL(blob);
    urls.push(url);
    if(!dialog.isConnected){
      URL.revokeObjectURL(url);
      return;
    }
    const row=rows.get(target.choice);
    if(!row)return;
    for(const id of target.choices||[target.choice])previewBlobs.set(id,blob);
    row.image.src=url;
    row.image.hidden=false;
    row.loading.remove();
    for(const button of row.buttons)button.disabled=false;
  },plan=>{
    gallery.replaceChildren();
    for(const target of plan.targets){
      const represented=(target.choices||[target.choice]).map(id=>byId.get(id)).filter(Boolean);
      if(!represented.length)continue;
      const tile=document.createElement('div');
      tile.className='well';
      tile.style.cssText='display:flex;flex-direction:column;gap:8px;align-items:center;width:190px';
      const buttons=represented.map(choice=>choiceButton(choice));
      const image=document.createElement('img');
      image.alt='Preview of '+represented.map(choice=>choice.name).join(' or ');
      image.style.width='170px';
      image.style.maxWidth='100%';
      image.hidden=true;
      const choice=represented.find(choice=>choice.id===selected)||represented[0];
      const preview=document.createElement('button');
      preview.type='button';preview.className='button quiet';
      preview.setAttribute('aria-label','Choose '+choice.name+' from preview');
      preview.style.width='170px';
      preview.style.minHeight='238px';
      preview.style.padding='0';
      preview.onclick=()=>selectChoice(choice);
      const loading=document.createElement('span');loading.textContent='Rendering…';loading.className='muted';
      preview.append(image,loading);
      const inspect=document.createElement('button');
      inspect.type='button';inspect.className='button quiet';inspect.title='Enlarge preview';
      inspect.textContent='Enlarge preview';inspect.disabled=true;
      inspect.onclick=()=>{zoomImage.src=image.src;document.body.append(zoom);};
      tile.append(preview,...buttons,inspect);
      gallery.append(tile);
      rows.set(target.choice,{buttons,image,loading});
      const row=rows.get(target.choice);
      row.buttons.push(inspect);
    }
    for(const [id,message] of Object.entries(plan.previewErrors||{})){
      const choice=byId.get(id);
      if(!choice)continue;
      const button=choiceButton(choice);
      button.disabled=true;
      button.title=message;
      button.textContent=choice.name+' · unavailable';
      gallery.append(button);
    }
  },controller.signal).then(plan=>{
    if(!plan)return;
    if(!dialog.isConnected)return;
    status.remove();
  }).catch(error=>{
    if(dialog.isConnected)status.textContent='Could not build previews: '+error.message;
  });

  const observer=new MutationObserver(()=>{
    if(dialog.isConnected)return;
    observer.disconnect();
    controller.abort();
    zoom.remove();
    for(const url of urls)URL.revokeObjectURL(url);
  });
  observer.observe(document.body,{childList:true,subtree:true});
}
