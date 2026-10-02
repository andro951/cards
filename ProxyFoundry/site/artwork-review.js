import {$,api,job,modal,closeModal,thumbnail,state,toast,uploadFolder} from './ui.js';
import {sourceRecord,mergeDataDocument,downloadData,saveLocalData,saveGithubData,githubDataLocation,githubCredential,connectGithub,disconnectGithub,pickArtworkFiles} from './artwork-files.js';

const element=(tag,text=``)=>{
    const node=document.createElement(tag);
    node.textContent=text;
    return node;
};
const button=(text,action)=>{
    const node=element(`button`,text);
    node.type=`button`;node.className=`button`;node.onclick=action;
    return node;
};
const imageButton=(url,label,action)=>{
    const node=button(``,action);
    node.setAttribute(`aria-label`,label);
    node.style.width=`140px`;node.style.padding=`8px`;
    Object.assign(node.style,{display:`flex`,flexDirection:`column`,whiteSpace:`normal`,overflowWrap:`anywhere`,boxSizing:`border-box`,flexShrink:`0`});
    const image=element(`img`);image.src=thumbnail(url);image.alt=label;image.loading=`lazy`;image.decoding=`async`;
    image.style.width=`100%`;image.style.height=`185px`;image.style.objectFit=`contain`;
    image.onerror=()=>{image.alt=`Image unavailable. Click to inspect or retry.`;};
    node.append(image);
    return node;
};
const enlarge=(url,label)=>{
    const overlay=element(`dialog`);overlay.setAttribute(`aria-label`,label);
    overlay.style.maxWidth=`95vw`;overlay.style.background=`#160f09`;overlay.style.color=`#f0d7aa`;
    const image=element(`img`);image.src=url.replace(/\/thumbnail$/,``);image.alt=label;
    image.style.maxWidth=`85vw`;image.style.maxHeight=`80dvh`;image.style.objectFit=`contain`;
    overlay.append(image,button(`Close`,()=>{overlay.close();overlay.remove();}));
    overlay.addEventListener(`close`,()=>overlay.remove());
    document.body.append(overlay);overlay.showModal();
};

//#region Pairing helper
export const openArtworkHelper=async(initial,{deckId,settings,onAdd=null})=>{
    let review=initial,selected=null,search=``;
    const saved=await sourceRecord(`pairing:${deckId}`);
    const pairs=new Map(saved?.signature===review.signature?saved.pairs:[]);
    const manualItems=()=>review.items.filter(item=>[`missing`,`conflict`].includes(item.status));
    const files=new Map();
    const loadFiles=()=>{
        const previous=new Map(files);
        files.clear();
        for(const file of review.inventory) {
            files.set(file.key,file);
        }

        for(const [id,key] of pairs) {
            if(!files.has(key)||!review.items.some(item=>item.id===id)||previous.has(key)&&(previous.get(key).filename!==files.get(key).filename||previous.get(key).identity!==files.get(key).identity))
                pairs.delete(id);
        }
    };
    loadFiles();
    return new Promise(resolve=>{
        let done=false,saveTimer;
        const persist=()=>sourceRecord(`pairing:${deckId}`,{signature:review.signature,pairs:[...pairs]});
        const changed=()=>{clearTimeout(saveTimer);saveTimer=setTimeout(()=>persist().catch(error=>toast(error.message,true)),150);};
        modal(`Match your artwork`,``,{onClose:()=>{clearTimeout(saveTimer);if(!done){persist().catch(error=>toast(error.message,true));resolve(null);}return true;}});
        const dialog=$(`#modal-host .modal-backdrop`);
        dialog.style.padding=`0`;
        const box=$(`.modal`,dialog),body=$(`.modal-body`,dialog);
        Object.assign(box.style,{width:`100vw`,maxWidth:`100vw`,height:`100dvh`,maxHeight:`100dvh`,borderRadius:`0`,display:`flex`,flexDirection:`column`});
        Object.assign(body.style,{flex:`1`,minHeight:`0`,overflow:`auto`});
        const instructions=element(`p`,`Click a card, then click its artwork to pair them. Double-click an image to enlarge it.`);
        const status=element(`p`);status.setAttribute(`role`,`status`);status.id=`artwork-counts`;
        const warning=element(`p`);warning.id=`artwork-warning`;warning.setAttribute(`role`,`alert`);
        const paired=element(`section`);paired.setAttribute(`aria-label`,`Paired artwork`);
        const columns=element(`div`);Object.assign(columns.style,{display:`flex`,gap:`24px`,alignItems:`flex-start`,flexWrap:`wrap`});
        const left=element(`section`),right=element(`section`);
        left.setAttribute(`aria-label`,`Cards needing artwork`);right.setAttribute(`aria-label`,`Unused artwork`);
        for(const column of [left,right]) {
            Object.assign(column.style,{flex:`1 1 280px`,minWidth:`0`});
        }

        const leftGrid=element(`div`),rightGrid=element(`div`);
        for(const grid of [leftGrid,rightGrid]) {
            Object.assign(grid.style,{display:`flex`,flexWrap:`wrap`,gap:`12px`});
        }

        const searchInput=element(`input`);searchInput.type=`search`;searchInput.placeholder=`Find an artwork filename…`;searchInput.setAttribute(`aria-label`,`Find an artwork filename`);
        left.append(element(`h3`,`Cards needing artwork`),leftGrid);
        right.append(element(`h3`,`Unused artwork`),searchInput,rightGrid);columns.append(left,right);
        const actions=element(`footer`);Object.assign(actions.style,{padding:`16px`,display:`flex`,gap:`12px`,flexWrap:`wrap`});
        const finish=button(`Finish`,()=>complete(false));finish.id=`artwork-finish`;
        const fallback=button(`Default Art for the rest`,()=>complete(true));fallback.id=`artwork-default-rest`;fallback.style.fontWeight=`bold`;
        const add=button(settings.source.mode===`github`?`Refresh GitHub folder`:`Add images`,async()=>{
            add.disabled=true;
            try{review=await onAdd();loadFiles();cardNodes.clear();fileNodes.clear();pairNodes.clear();leftLimit=80;rightLimit=60;draw();changed();}
            catch(error){warning.textContent=error.message;}
            finally{add.disabled=false;}
        });add.id=`artwork-add-images`;add.hidden=!onAdd;
        if(!onAdd)add.style.display=`none`;
        actions.append(button(`Back to setup`,closeModal),add,finish,fallback);
        body.append(instructions,status,warning,paired,columns);box.append(actions);
        let leftLimit=80,rightLimit=60;
        const cardNodes=new Map(),fileNodes=new Map(),pairNodes=new Map();
        const selectCard=item=>{
            selected=item.id;warning.textContent=item.reason;
            for(const [id,node] of cardNodes) {
                node.style.outline=id===selected?`3px solid #ef8a23`:``;
                node.setAttribute(`aria-pressed`,id===selected?`true`:`false`);
            }
        };
        const pairFile=file=>{
            if(!selected) {
                warning.textContent=`Select a card on the left first.`;
                return;
            }

            pairs.set(selected,file.key);selected=null;warning.textContent=``;draw();changed();
        };
        const draw=()=>{
            const outstanding=manualItems().filter(item=>!pairs.has(item.id));
            const used=new Set([...review.items.filter(item=>item.key!==null&&!pairs.has(item.id)).map(item=>item.key),...pairs.values()]);
            const unused=review.inventory.filter(file=>!used.has(file.key));
            status.textContent=`${outstanding.length} cards need artwork · ${unused.length} unused images · ${pairs.size} paired`;
            paired.replaceChildren();
            for(const [id,key] of pairs) {
                const item=review.items.find(item=>item.id===id),file=files.get(key);
                let row=pairNodes.get(id);
                if(!row||row.dataset.file!==key) {
                    row=element(`div`);row.dataset.file=key;row.dataset.artworkPair=id;
                    Object.assign(row.style,{display:`flex`,alignItems:`center`,gap:`16px`,flexWrap:`wrap`,padding:`12px`});
                    const target=imageButton(item.image,item.name,()=>enlarge(item.image,item.name));
                    const art=imageButton(file.image,file.filename,()=>enlarge(file.image,file.filename));
                    art.append(element(`small`,file.filename));
                    const undo=button(`×`,()=>{pairs.delete(id);draw();changed();});undo.setAttribute(`aria-label`,`Undo artwork pairing for `+item.name);
                    row.append(target,element(`span`,`→`),art,undo);pairNodes.set(id,row);
                }

                paired.append(row);
            }

            leftGrid.replaceChildren();
            for(const item of outstanding.slice(0,leftLimit)) {
                let node=cardNodes.get(item.id);
                if(!node) {
                    node=imageButton(item.image,item.name,()=>selectCard(item));node.dataset.artworkCard=item.id;
                    node.ondblclick=()=>enlarge(item.image,item.name);cardNodes.set(item.id,node);
                }

                leftGrid.append(node);
            }

            if(outstanding.length>leftLimit)
                leftGrid.append(button(`Show more cards`,()=>{leftLimit+=80;draw();}));

            rightGrid.replaceChildren();
            const visible=unused.filter(file=>file.filename.toLowerCase().includes(search.toLowerCase()));
            for(const file of visible.slice(0,rightLimit)) {
                let node=fileNodes.get(file.key);
                if(!node) {
                    node=imageButton(file.image,file.filename,()=>pairFile(file));node.dataset.artworkFile=file.key;
                    const caption=element(`small`,file.filename);caption.style.display=`block`;caption.style.overflowWrap=`anywhere`;
                    node.append(caption);node.ondblclick=()=>enlarge(file.image,file.filename);fileNodes.set(file.key,node);
                }

                rightGrid.append(node);
            }

            if(visible.length>rightLimit)
                rightGrid.append(button(`Show more images`,()=>{rightLimit+=60;draw();}));

            finish.disabled=outstanding.length>0;
            finish.textContent=unused.length?`Finish — leave unused images`:`Finish`;
            fallback.hidden=!settings.source.fallback||!outstanding.length;
            fallback.style.display=fallback.hidden?`none`:``;
            fallback.disabled=!outstanding.length;
            if(outstanding.length&&settings.source.fallback&& !warning.textContent)
                warning.textContent=`These cards don’t have custom artwork. Add images now, or choose Default Art for the rest to use their Scryfall artwork.`;
        };
        const complete=async useDefaults=>{
            const changes=[...pairs].map(([id,key])=>({...review.items.find(item=>item.id===id).selector,art:files.get(key).filename}));
            const defaults=review.items.filter(item=>item.status===`default`||useDefaults&&manualItems().some(row=>row.id===item.id)&&!pairs.has(item.id)).map(item=>item.id);
            finish.disabled=true;fallback.disabled=true;
            try{await sourceRecord(`pairing:${deckId}`,null);}
            catch(error){warning.textContent=error.message;draw();return;}
            done=true;clearTimeout(saveTimer);
            closeModal();resolve({changes,defaults,signature:review.signature});
        };
        searchInput.oninput=()=>{search=searchInput.value;rightLimit=60;draw();};
        draw();
    });
};
//#endregion

//#region Optional data.json export
const githubGuideSnippet=(label,height)=>{
    const canvas=window.document.createElement(`canvas`);canvas.width=480;canvas.height=height;
    const context=canvas.getContext(`2d`);
    context.fillStyle=`#25201b`;context.fillRect(0,0,480,height);
    context.strokeStyle=`#80603c`;context.strokeRect(1,1,478,height-2);
    context.fillStyle=`#c7ac87`;context.font=`16px sans-serif`;context.textAlign=`center`;
    context.fillText(`Screenshot placeholder`,240,height/2-8);
    context.font=`13px sans-serif`;context.fillText(label,240,height/2+17);
    const image=element(`img`);image.src=canvas.toDataURL();image.alt=`Screenshot placeholder: ${label}`;
    Object.assign(image.style,{display:`block`,width:`100%`,maxWidth:`480px`,height:`auto`,borderRadius:`8px`});
    return image;
};
export const offerDataSave=async(deckId,changes,document,githubUrl=``)=>{
    if(!changes.length)
        return;

    const record=await sourceRecord(`deck:${deckId}`)||{};
    let url=record.github||githubUrl;
    let sourceWarning=``;
    try{if(url)githubDataLocation(url);}
    catch(error){url=``;sourceWarning=`Use the full GitHub folder link in Art & Setup to update data.json. You can download it now.`;}
    return new Promise(resolve=>{
        let saving=false;
        modal(`Save artwork choices for next time?`,``,{onClose:()=>{if(saving)return false;resolve();return true;}});
        const dialog=$(`#modal-host .modal-backdrop`);
        const body=$(`.modal-body`,dialog),status=element(`p`);status.setAttribute(`role`,`status`);
        $(`.modal`,dialog).style.width=`580px`;
        Object.assign(body.style,{display:`flex`,flexDirection:`column`,gap:`18px`});
        status.style.margin=`0`;status.style.overflowWrap=`anywhere`;
        status.textContent=sourceWarning;
        const choices=element(`section`);
        Object.assign(choices.style,{display:`flex`,flexDirection:`column`,gap:`12px`});
        const intro=element(`p`,`Save a data.json to reuse these choices next time.`);intro.style.margin=`0 0 6px`;
        choices.append(intro);body.append(choices);
        const finish=()=>{if(saving)return;closeModal();resolve();};
        choices.append(button(`Download data.json`,()=>{if(saving)return;downloadData(mergeDataDocument(document,changes));finish();}));
        if(url) {
            const save=button(`Update data.json on GitHub`,async()=>{
                if(saving)return;
                save.disabled=true;saving=true;status.textContent=`Updating data.json…`;
                try{
                    const location=githubDataLocation(url);
                    let token=await githubCredential(location.repo);
                    if(!token) {
                        choices.style.display=`none`;connection.style.display=`flex`;
                        $(`#modal-title`,dialog).textContent=`Connect GitHub`;status.textContent=``;
                        guide.focus();save.disabled=false;saving=false;return;
                    }

                    const merged=await saveGithubData(location,token,changes,record.document);
                    await rememberResult(merged);status.textContent=`data.json updated on GitHub.`;
                    if(!remember.checked&&!remembered)
                        await disconnectGithub(location.repo);

                    saving=false;finish();
                }
                catch(error){status.textContent=error.message;}
                finally{if(!remember.checked&&!remembered)await disconnectGithub(githubDataLocation(url).repo);save.disabled=false;saving=false;}
            });
            const location=githubDataLocation(url),[owner,repo]=location.repo.split(`/`);
            const connection=element(`section`);
            Object.assign(connection.style,{display:`none`,flexDirection:`column`,gap:`18px`});
            const summary=element(`p`,`Connect ${location.repo} to save your data.json.`);summary.style.margin=`0`;
            const guide=element(`a`,`Open GitHub token setup ↗`);guide.className=`button`;
            guide.href=`https://github.com/settings/personal-access-tokens/new?`+new URLSearchParams({name:`BulkProxyForge`,description:`Update data.json artwork choices`,target_name:owner,contents:`write`,expires_in:`90`});guide.target=`_blank`;guide.rel=`noopener noreferrer`;
            connection.append(summary,guide);
            const steps=element(`ol`);Object.assign(steps.style,{display:`flex`,flexDirection:`column`,gap:`20px`,paddingLeft:`24px`,margin:`0`});
            const instructions=[
                [`Choose your repository`,`Resource owner: ${owner}. Choose an expiration, then Only select repositories → ${repo}.`,`Repository selection`,120],
                [`Check the permission`,`Under Repository permissions, Contents should say Read and write.`,`Contents permission`,90],
                [`Generate and copy`,`Click Generate token. Copy the token, then paste it below.`,`Generate token and copy button`,90]
            ];
            for(const [title,text,snippet,height] of instructions) {
                const step=element(`li`),heading=element(`strong`,title),detail=element(`p`,text);
                heading.style.display=`block`;detail.style.margin=`6px 0 10px`;
                step.append(heading,detail,githubGuideSnippet(snippet,height));steps.append(step);
            }

            connection.append(steps);
            const tokenInput=element(`input`);tokenInput.type=`password`;tokenInput.autocomplete=`off`;tokenInput.setAttribute(`aria-label`,`GitHub connection token`);
            tokenInput.placeholder=`Paste your GitHub token`;
            Object.assign(tokenInput.style,{display:`block`,width:`100%`,boxSizing:`border-box`,minWidth:`0`,padding:`12px`,borderRadius:`8px`,border:`1px solid #76502d`,background:`#100c08`,color:`#f0d7aa`});
            const tokenLabel=element(`label`,`GitHub token`);tokenLabel.style.display=`block`;tokenLabel.append(tokenInput);
            const remember=element(`input`);remember.type=`checkbox`;
            const label=element(`label`);label.append(remember,documentNode(`Remember access to update data.json next time`));
            Object.assign(label.style,{display:`flex`,alignItems:`flex-start`,gap:`10px`});
            Object.assign(remember.style,{flexShrink:`0`,marginTop:`4px`});
            const once=element(`small`,`Unchecked: connect for this update only.`);once.style.display=`block`;
            let remembered=false;
            sourceRecord(`github:${githubDataLocation(url).repo}`).then(token=>{remembered=!!token;forget.style.display=remembered?`block`:`none`;}).catch(error=>{status.textContent=error.message;});
            const connect=button(`Connect and update data.json`,async()=>{
                if(saving)return;
                try{await connectGithub(githubDataLocation(url).repo,tokenInput.value,remember.checked);tokenInput.value=``;await save.onclick();}
                catch(error){status.textContent=error.message;}
            });
            connect.disabled=true;tokenInput.oninput=()=>{connect.disabled=!tokenInput.value.trim();};
            const forget=button(`Forget GitHub connection`,async()=>{await disconnectGithub(githubDataLocation(url).repo);remembered=false;status.textContent=`GitHub connection forgotten.`;});
            forget.style.display=`none`;
            const back=button(`Back to save options`,()=>{if(saving)return;connection.style.display=`none`;choices.style.display=`flex`;$(`#modal-title`,dialog).textContent=`Save artwork choices for next time?`;status.textContent=``;save.focus();});
            connection.append(tokenLabel,label,once,connect,back);choices.append(save,forget);body.append(connection);
        }
        else if(record.file||record.folder) {
            const save=button(record.file?`Update existing data.json`:`Create data.json in artwork folder`,async()=>{
                save.disabled=true;saving=true;status.textContent=`Saving data.json…`;
                try{const result=await saveLocalData(record,changes);await sourceRecord(`deck:${deckId}`,result);saving=false;finish();}
                catch(error){status.textContent=error.message;}
                finally{save.disabled=false;saving=false;}
            });choices.append(save);
        }

        const rememberResult=async merged=>sourceRecord(`deck:${deckId}`,{...record,github:url,document:merged});
        body.append(status,button(`Not now`,finish));
        for(const control of body.querySelectorAll(`.button`)) {
            Object.assign(control.style,{whiteSpace:`normal`,overflowWrap:`anywhere`,width:`100%`,boxSizing:`border-box`});
        }
    });
};
const documentNode=text=>window.document.createTextNode(text);
//#endregion

export const checkArtwork=async(deck,settings=deck.settings,cardData=deck.cardData||[],onAdd=null)=>{
    if(settings.source.mode===`scryfall`)
        return {changes:[],defaults:settings.artDefaults||[],signature:settings.artReviewSignature||``};

    const load=()=>job(`/api/setup/artwork-review`,{deckId:deck.id,settings,cardData},{label:`Check artwork`});
    const review=await load();
    if(!review.needsReview)
        return {changes:[],defaults:settings.artDefaults||[],signature:review.signature};

    return openArtworkHelper(review,{deckId:deck.id,settings,onAdd:async()=>{if(onAdd)await onAdd();return load();}});
};
export const ensureArtworkReady=async id=>{
    const deck=await api(`/api/decks/`+id);
    const settings=structuredClone(deck.settings);
    const add=async()=>{
        if(settings.source.mode===`github`)
            return;

        const files=await pickArtworkFiles(id);
        if(!files)
            throw new Error(`Return to Art & setup to add artwork in this browser.`);

        settings.source.localFiles=await uploadFolder(files,null,settings.source);
    };
    const result=await checkArtwork(deck,settings,deck.cardData||[],add);
    if(!result)
        return false;

    if(settings.source.mode!==`scryfall`) {
        settings.artDefaults=result.defaults;settings.artReviewSignature=result.signature;
        const saved=await api(`/api/decks/`+id+`/save`,{revision:deck.revision,settings,cardData:result.changes});
        await offerDataSave(id,result.changes,{version:1,cards:saved.cardData||[]},settings.dataJsonSource?.kind===`github`?settings.githubSetupFolder||settings.source.githubFolder:``);
        if(state.activeDeck?.id===id)
            state.activeDeck=saved;
    }

    return true;
};