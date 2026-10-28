import {api,job,modal,closeModal,setModalBusy,$,toast,downloadBlob,work,errorBox} from './ui.js';
import {sourceRecord} from './artwork-files.js';

export const isCompleteDeckDocument=value=>value?.version===2&&value?.format===`bulk-proxy-forge-deck`;

export async function completeDeckDocument(id,{owner=null}={}){
    let plan=await api(`/api/decks/${id}/data-document`);
    if(plan.missing.length){
        const configured=await new Promise(resolve=>{
            let done=false;
            const host=modal(`Add permanent image sources`,``,{onClose:()=>{if(!done)resolve(false);return true;}});
            const body=$(`.modal-body`,host);
            const intro=document.createElement(`p`);intro.textContent=`These images need permanent URLs so the deck can be rebuilt on another computer. Use public GitHub image links or Scryfall image URLs. GitHub links will be pinned to their exact version.`;
            body.append(intro);
            const inputs=new Map();
            for(const ident of plan.missing){
                const row=document.createElement(`label`);row.className=`field`;
                const title=document.createElement(`span`);title.textContent=plan.document.images[ident].label||`Custom image`;
                const image=document.createElement(`img`);image.src=`/api/assets/${ident}/thumbnail`;image.alt=`Image needing a permanent source`;image.style.maxWidth=`100px`;image.style.maxHeight=`120px`;
                const input=document.createElement(`input`);input.type=`url`;input.placeholder=`https://github.com/owner/repo/blob/main/image.png`;input.setAttribute(`aria-label`,`Permanent URL for image ${ident.slice(0,8)}`);
                const original=document.createElement(`a`);original.className=`button small`;original.href=`/api/assets/${ident}`;original.download=`source-${ident.slice(0,8)}`;original.textContent=`Download source image`;
                row.append(title,image,original,input);body.append(row);inputs.set(ident,input);
            }
            const save=document.createElement(`button`);save.className=`button primary`;save.textContent=`Verify and save image sources`;
            save.onclick=async()=>{
                save.disabled=true;setModalBusy(host,true);
                try{
                    const sources=Object.fromEntries([...inputs].map(([ident,input])=>[ident,input.value.trim()]));
                    if(Object.values(sources).some(url=>!url))throw new Error(`Supply a permanent URL for every image.`);
                    await api(`/api/decks/${id}/image-sources`,{revision:plan.revision,sources},'POST',owner);
                    done=true;closeModal();resolve(true);
                }
                catch(error){errorBox(body,error.message);}
                finally{save.disabled=false;setModalBusy(host,false);}
            };
            body.append(save);
        });
        if(!configured)return null;
        plan=await api(`/api/decks/${id}/data-document`);
    }
    return plan.document;
}

export async function downloadCompleteDeck(id){
    const owner=work.begin({label:`Export complete data.json`,resources:[`deck:${id}`]});
    try{
        const document=await completeDeckDocument(id,{owner});
        if(!document)return;
        downloadBlob(new Blob([JSON.stringify(document,null,2)+`\n`],{type:`application/json`}),`data.json`);
        toast(`Complete deck recipe downloaded.`);
    }
    finally{work.finish(owner);}
}

export async function importCompleteDeck(document){
    work.requireIdle();
    const owner=work.begin({label:`Import complete data.json`,resources:[`workspace`]});
    try{
        const deck=await job(`/api/deck-documents/import`,document,{label:`Import complete deck`,owner});
        const source=deck.settings.dataJsonSource;
        await sourceRecord(`deck:${deck.id}`,{document,
            ...(source?.kind===`github`&&source.value.startsWith(`https:`)?{github:source.value}:{})})
            .catch(error=>toast(`Deck imported, but its file connection could not be remembered: ${error.message}`,true));
        return deck;
    }
    finally{work.finish(owner);}
}

export async function generationNeedsDataSave(ids){
    for(const id of ids){
        const deck=await api(`/api/decks/${id}`);
        if(deck.settings.dataJsonSource?.kind===`github`||deck.settings.githubSetupFolder)return true;
    }
    return false;
}

export async function saveGenerationData(ids,{owner}={}){
    for(const id of ids){
        if(owner?.controller.signal.aborted)throw new Error(`Generation cancelled before saving data.json.`);
        const deck=await api(`/api/decks/${id}`);
        const source=deck.settings.dataJsonSource;
        if(source?.kind!==`github`)continue;
        const url=source.value?.startsWith(`https:`)?source.value:deck.settings.githubSetupFolder;
        const {offerDataSave}=await import('./artwork-review.js');
        const saved=await offerDataSave(id,deck.cardData||[],{version:1,cards:deck.cardData||[]},url,deck.cards,
            {title:`Save deck to GitHub before generation`,forceDocument:true,autoSave:true,requireGithubSave:true,owner});
        if(!saved?.github)throw new Error(`Generation stopped: the complete data.json was not saved to GitHub.`);
        if(owner?.controller.signal.aborted)throw new Error(`Generation cancelled after saving data.json. No images were generated.`);
        if(saved?.github&&saved.github!==source?.value){
            const current=await api(`/api/decks/${id}`);
            await api(`/api/decks/${id}/save`,{revision:current.revision,settings:{dataJsonSource:{kind:`github`,value:saved.github}}},'POST',owner);
        }
    }
}
