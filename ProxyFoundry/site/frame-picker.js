import {$,modal,closeModal,state,asset} from './ui.js';

const twoSidedGroups=['transform-front','transform-back','modal-front','modal-back'];

export function frameChoices(group,legendary=false){
  const ordinary=['standard','legendary','land','legendary-land','basic-land'].includes(group);
  return state.templates.filter(template=>
    (template.id==='auto'||(template.groups==='ordinary'?ordinary:Array.isArray(template.groups)&&template.groups.includes(group)))
    &&(!legendary||template.legendary)
  ).map(template=>template.id==='godzilla-card'&&twoSidedGroups.includes(group)?{...template,name:'Godzilla full art'}:template);
}

export function framePlaceholder(settings){
  return asset(settings.backAsset||state.bootstrap.backs.default.id);
}

export function openFramePicker(deck,group,settings,cardData,selected,onSelect){
  const choices=frameChoices(group,['legendary','legendary-land'].includes(group));
  const dialog=modal('Choose a frame for '+(state.bootstrap.groups[group]||group),'',{size:'large'});
  const body=$('.modal-body',dialog);
  const gallery=document.createElement('div');
  gallery.style.display='flex';
  gallery.style.flexWrap='wrap';
  gallery.style.gap='16px';
  if(twoSidedGroups.includes(group)){
    const note=document.createElement('p');
    note.textContent='Godzilla uses a full-art frame for each face without the usual two-sided icons or opposite-face bar.';
    body.append(note);
  }
  body.append(gallery);

  for(const choice of choices){
    const button=document.createElement('button');
    button.type='button';
    button.className='button';
    button.style.width='190px';
    button.style.display='flex';
    button.style.flexDirection='column';
    button.style.alignItems='center';
    button.style.gap='8px';
    button.setAttribute('aria-label','Select '+choice.name);
    button.setAttribute('aria-pressed',String(choice.id===selected));
    const image=document.createElement('img');
    image.src=framePlaceholder(settings);
    image.alt='Card back placeholder for '+choice.name;
    image.style.width='170px';
    image.style.maxWidth='100%';
    image.style.objectFit='contain';
    const label=document.createElement('strong');
    label.textContent=choice.name+(choice.id===selected?' · selected':'');
    button.append(image,label);
    button.onclick=()=>{onSelect(choice.id);closeModal();};
    gallery.append(button);
  }
}
