import {thumbnail} from './ui.js';

const node=(tag,text=``)=>{
    const result=document.createElement(tag);result.textContent=text;
    return result;
};
const action=(text,click)=>{
    const result=node(`button`,text);result.type=`button`;result.className=`button`;result.onclick=click;
    return result;
};
const gallery=()=>{
    const result=node(`div`);
    Object.assign(result.style,{display:`grid`,gridTemplateColumns:`repeat(auto-fill,minmax(150px,1fr))`,gap:`16px`});
    return result;
};
const tile=(label,image,click)=>{
    const result=action(``,click);result.setAttribute(`aria-label`,label);
    Object.assign(result.style,{display:`flex`,flexDirection:`column`,gap:`8px`,whiteSpace:`normal`,overflowWrap:`anywhere`,minWidth:`0`});
    const picture=node(`img`);picture.src=thumbnail(image);picture.alt=label;
    Object.assign(picture.style,{width:`100%`,height:`200px`,objectFit:`contain`});
    result.append(picture,node(`strong`,label));return result;
};
export const mountArtVariantPicker=(host,{cards,inventory,variants,initialArt=null,initialCard=null,initialFace=null,onComplete,onCancel})=>{
    let art=initialArt,card=initialCard,face=initialFace;
    const list=(title,entries,makeTile)=>{
        host.replaceChildren(node(`h3`,title));
        const search=node(`input`);search.type=`search`;search.placeholder=`Search…`;search.setAttribute(`aria-label`,title);
        Object.assign(search.style,{width:`100%`,padding:`12px`,boxSizing:`border-box`,marginBottom:`16px`});
        const items=gallery(),empty=node(`p`,`No matching choices.`);
        const draw=()=>{
            items.replaceChildren();
            for(const entry of entries.filter(entry=>entry.label.toLowerCase().includes(search.value.trim().toLowerCase()))) {
                items.append(makeTile(entry));
            }

            empty.hidden=Boolean(items.children.length);
        };
        search.oninput=draw;host.append(search,items,empty,action(`Cancel`,onCancel));draw();search.focus();
    };
    const quantity=()=>{
        host.replaceChildren(node(`h3`,`Split copies of ${card.name}`));
        const images=gallery();images.append(tile(face.name,face.image,()=>{}),tile(art.filename,art.image,()=>{}));host.append(images);
        host.append(node(`p`,`Move copies to this artwork. The deck will still contain ${card.quantity} copies across these two entries.`));
        const label=node(`label`,`Copies using the new artwork`),count=node(`input`);count.type=`number`;count.min=`1`;count.max=String(card.quantity);count.value=`1`;count.step=`1`;count.setAttribute(`aria-label`,`Alternate art quantity`);
        Object.assign(count.style,{display:`block`,padding:`10px`,width:`120px`});label.append(count);host.append(label);
        const status=node(`p`);status.setAttribute(`role`,`alert`);host.append(status);
        host.append(action(`Split copies`,async()=>{
            const amount=Number(count.value);
            if(!Number.isInteger(amount)||amount<1||amount>card.quantity) {
                count.setCustomValidity(`Choose 1–${card.quantity} copies.`);count.reportValidity();return;
            }

            count.setCustomValidity(``);
            const rows=structuredClone(variants),existing=rows.find(row=>row.id===card.variantId);
            const source=existing?structuredClone(existing):null;
            if(existing) {
                existing.quantity-=amount;
                if(!existing.quantity)rows.splice(rows.indexOf(existing),1);
            }

            const faces=existing?structuredClone(source.faces):[];
            const target=faces.find(row=>row.name===face.name);
            if(target)target.art=art.filename;
            else faces.push({name:face.name,art:art.filename});
            const created={id:crypto.randomUUID(),card:card.source,quantity:amount,faces};rows.push(created);
            const controls=[...host.querySelectorAll(`button,input`)];controls.forEach(control=>control.disabled=true);
            await Promise.resolve(onComplete(rows,{card,face,art,created,source})).catch(error=>{
                status.textContent=error.message;controls.forEach(control=>control.disabled=false);
            });
        }),action(`Cancel`,onCancel));count.focus();count.select();
    };
    const chooseCard=()=>list(`Select existing card`,cards.flatMap(card=>card.faces.map(face=>({card,face,label:`${face.name} · ${card.quantity} copies${card.variantId?` · ${face.art}`:``}`}))),(entry)=>tile(entry.label,entry.face.image,()=>{card=entry.card;face=entry.face;quantity();}));
    if(!art)
        list(`Select alternate artwork`,inventory.map(art=>({art,label:art.filename})),entry=>tile(entry.label,entry.art.image,()=>{art=entry.art;if(card)quantity();else chooseCard();}));
    else if(card)
        quantity();
    else
        chooseCard();
};