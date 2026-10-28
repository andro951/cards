import {api,asset,thumbnail,modal,closeModal,setModalBusy,attempt,toast,$,confirmAction,errorBox,state,work} from './ui.js';
import {offerDataSave} from './artwork-review.js';

//#region Shared controls and persistence
const element=(tag,text=``)=>{
    const node=document.createElement(tag);node.textContent=text;
    return node;
};
const button=(text,action,primary=false)=>{
    const node=element(`button`,text);node.type=`button`;node.className=primary?`button primary`:`button`;
    node.onclick=()=>attempt(action);
    return node;
};
const grid=()=>{
    const node=element(`div`);node.className=`card-grid`;
    Object.assign(node.style,{display:`grid`,gridTemplateColumns:`repeat(auto-fill, minmax(min(180px, 100%), 1fr))`,gap:`18px`,maxHeight:`none`,overflow:`visible`,marginTop:`16px`});
    return node;
};
const search=(label,changed)=>{
    const node=element(`input`);node.type=`search`;node.placeholder=label;node.setAttribute(`aria-label`,label);
    Object.assign(node.style,{width:`100%`,boxSizing:`border-box`,padding:`12px`,marginTop:`12px`});
    node.oninput=()=>changed(node.value);
    return node;
};
const displayName=card=>card.faces[0]?.semanticOverrides?.nickname||card.scryfall?.flavor_name||card.faces[0]?.name||card.name;
const searchText=card=>[card.name,displayName(card),card.scryfall?.type_line,...card.faces.map(face=>[face.name,face.semanticOverrides?.nickname].join(` `))].join(` `).toLowerCase();
const tokenData=deck=>({tokenAssignments:deck.settings.tokenAssignments||[],tokenTreatments:deck.settings.tokenTreatments||[]});
const snapshot=deck=>deck.githubCardDataState?{version:1,cards:deck.githubCardDataState.entries,...deck.githubCardDataState.settings}:null;
export const saveTokenData=async(deck,{beforePrompt=null}={})=>{
    const source=deck.settings.dataJsonSource;
    const url=source?.kind===`github`?(source.value.startsWith(`https:`)?source.value:deck.settings.githubSetupFolder):``;
    const options={
        title:`Save token assignments`,autoSave:true,baseline:snapshot(deck),tokenData:tokenData(deck),beforePrompt
    };
    const document={version:1,cards:deck.cardData||[],...tokenData(deck)};
    const result=await offerDataSave(deck.id,[],document,url,deck.cards,options).catch(error=>{
        toast(`Saved in this deck. ${error.message}`,true);
        return offerDataSave(deck.id,[],document,url,deck.cards,{...options,autoSave:false});
    });
    if(result?.github&&result.github!==source?.value) {
        const current=await api(`/api/decks/${deck.id}`);
        await api(`/api/decks/${deck.id}/save`,{revision:current.revision,settings:{dataJsonSource:{kind:`github`,value:result.github}}});
    }

    return result;
};
const persistTokenChange=async(deck,onChanged,save)=>{
    const existing=$(`#modal-host .modal`);
    const host=existing||modal(`Saving token assignments`,``,{dismissible:false});
    const controls=[...host.querySelectorAll(`button,input,select`)].map(node=>[node,node.disabled]);
    for(const [node] of controls) {
        node.disabled=true;
    }

    setModalBusy(host,true);
    try {
        await save();
        const updated=await api(`/api/decks/${deck.id}`);
        await saveTokenData(updated,{beforePrompt:()=>closeModal({completed:true})});
        //Connecting the data file can save the deck again; display that revision.
        await onChanged(await api(`/api/decks/${deck.id}`));
        closeModal({completed:true});
    }
    finally {
        setModalBusy(host,false);
        for(const [node,disabled] of controls) {
            node.disabled=disabled;
        }

        if(!existing&&host.isConnected)
            closeModal({completed:true});
    }
};
const persist=(deck,rows,onChanged)=>persistTokenChange(deck,onChanged,()=>
    api(`/api/decks/${deck.id}/save`,{revision:deck.revision,tokenAssignments:rows}));
const savedRows=deck=>{
    const rows=structuredClone(deck.settings.tokenAssignments||[]);
    for(const pair of deck.tokens.assigned) {
        if(pair.index===null)
            rows.push(structuredClone(pair.assignment));
    }

    return rows;
};
const imageTile=(card,source,onClick,{back=``,quantity=``,caption=``,title=displayName(card),dataKey=``,dataValue=``}={})=>{
    const article=element(`article`);article.className=`card-item`;
    const pick=button(``,onClick);pick.className=`card-image`;pick.setAttribute(`aria-label`,caption||displayName(card));
    if(dataKey)
        pick.dataset[dataKey]=dataValue;

    const image=element(`img`);image.loading=`lazy`;image.alt=title;
    const front=thumbnail(source);image.src=front||``;
    if(!front)
        image.hidden=true;

    if(back) {
        pick.onmouseenter=()=>{image.src=thumbnail(back);};
        pick.onmouseleave=()=>{image.src=front;};
        pick.onfocus=()=>{image.src=thumbnail(back);};
        pick.onblur=()=>{image.src=front;};
    }

    if(quantity!==``) {
        const count=element(`span`,quantity);count.className=`quantity-pill`;pick.append(count);
    }

    pick.append(image);
    if(!front) {
        const missing=element(`span`,`Image not rendered`);pick.append(missing);
    }

    const label=element(`span`,title);label.className=`card-name-pill`;pick.append(label);
    label.style.left=`${Math.max(50,String(quantity).length*6+24)}px`;
    const face=card.faces[0],ready=Boolean(face?.compiled?.render);
    if(face&&!ready) {
        const status=element(`span`,face.error?`Needs attention`:face.lastRender?.render?`Previous render · changes pending`:`Not rendered`);status.className=`image-label`;pick.append(status);
    }

    if(card.faces.some(face=>face.error||((face.compiled?.crop?.warning||face.compiled?.flags?.length)&&face.acceptedWarningKey!==face.compiled?.renderKey))) {
        const warning=element(`span`,`!`);warning.className=`warn-pill`;warning.title=`Needs review`;pick.append(warning);
    }
    article.append(pick);
    if(caption) {
        const detail=element(`p`,caption);Object.assign(detail.style,{margin:`8px 0`,overflowWrap:`anywhere`,fontSize:`13px`});article.append(detail);
    }

    return article;
};
//#endregion

//#region Token pairing
export const assignToken=async(deck,front,onChanged,preview,pair=null,onInspect=null)=>{
    const host=modal(pair?`Edit token pairing`:`Choose a back for ${displayName(front)}`,``,{size:`large`});
    const body=$(`.modal-body`,host),cards=new Map(deck.cards.map(card=>[card.id,card]));
    let selected=pair,editing=pair?.index??null,busy=false;
    const fail=error=>{errorBox(body,error.message);};
    const write=async rows=>{
        if(busy)
            return;

        busy=true;
        for(const node of host.querySelectorAll(`button,input`)) {
            node.disabled=true;
        }

        await persist(deck,rows,onChanged).catch(error=>{
            busy=false;
            for(const node of host.querySelectorAll(`button,input`)) {
                node.disabled=false;
            }

            fail(error);
        });
    };
    const quantityStep=()=>{
        body.replaceChildren();
        const other=cards.get(selected.backCardId);
        const title=element(`h3`,`${displayName(front)} / ${selected.backKind===`reverse`?front.faces[1].name:other?displayName(other):`Normal card back`}`);
        body.append(title);
        const previews=grid();previews.style.gridTemplateColumns=`repeat(2, minmax(0, 220px))`;
        previews.append(imageTile(front,preview(front,front.faces[0]),()=>{}, {caption:`Front`}));
        const back=selected.backKind===`reverse`?preview(front,front.faces[1]):other?preview(other,other.faces[0]):asset(deck.settings.backAsset);
        previews.append(imageTile(other||front,back,()=>{}, {caption:`Back`,title:selected.backKind===`reverse`?front.faces[1].name:other?displayName(other):`Normal card back`}));body.append(previews);
        const label=element(`label`,`Copies of this pairing`);label.style.display=`block`;label.style.marginTop=`18px`;
        const count=element(`input`);count.type=`number`;count.min=`1`;count.max=`9999`;count.step=`1`;count.value=selected.quantity||front.quantity;
        count.setAttribute(`aria-label`,`Token quantity`);Object.assign(count.style,{display:`block`,width:`120px`,marginTop:`8px`,padding:`10px`});label.append(count);body.append(label);
        body.append(element(`p`,`This quantity is independent of the imported deck quantity. Each copy counts toward the usage of both token faces.`));
        const actions=element(`div`);Object.assign(actions.style,{display:`flex`,gap:`10px`,flexWrap:`wrap`});
        actions.append(button(`Save token`,async()=>{
            const value=Number(count.value);
            if(!Number.isInteger(value)||value<1||value>9999) {
                count.setCustomValidity(`Enter a whole number from 1 to 9999.`);count.reportValidity();return;
            }

            count.setCustomValidity(``);
            const rows=savedRows(deck),row={...structuredClone(selected.assignment),quantity:value};
            const index=editing??(pair?.index===null?rows.findIndex(item=>JSON.stringify(item.front)===JSON.stringify(row.front)&&item.back.kind===`reverse`):-1);
            if(index>=0)
                rows[index]=row;
            else
                rows.push(row);

            await write(rows);
        },true));
        if(selected.backKind!==`reverse`)
            actions.append(button(`Choose another back`,()=>{selected=null;editing=null;chooseBack();}));

        if(editing!==null) {
            actions.append(button(`Delete pairing`,async()=>{
                if(!await confirmAction(`Delete token pairing?`,`Faces no longer used by any pairing will need Token Review before printing.`,`Delete pairing`,true))
                    return;

                await write(savedRows(deck).filter((row,index)=>index!==editing));
            }));
        }

        actions.append(button(`Cancel`,()=>closeModal()));body.append(actions);
        if(onInspect&&selected.backKind===`reverse`) {
            body.append(button(`Edit front face`,()=>{closeModal();return onInspect(front,0);}));
            body.append(button(`Edit back face`,()=>{closeModal();return onInspect(front,1);}));
        }

        count.focus();count.select();
    };
    const select=other=>{
        const existing=deck.tokens.assigned.find(row=>row.backKind!==`reverse`&&(other?
            row.frontCardId===front.id&&row.backCardId===other.id||row.frontCardId===other.id&&row.backCardId===front.id:
            row.frontCardId===front.id&&row.backKind===`card-back`));
        if(existing) {
            const title=element(`h3`,`This combination already exists`),message=element(`p`,`You already have ${existing.quantity} ${existing.quantity===1?`copy`:`copies`} of this exact front/back combination. You can adjust its quantity.`);
            const warning=element(`section`);warning.setAttribute(`role`,`alertdialog`);warning.setAttribute(`aria-label`,`Duplicate token combination`);
            warning.append(title,message,button(`Cancel`,()=>closeModal()),button(`Adjust quantity`,()=>{
                selected=existing;editing=existing.index;front=cards.get(existing.frontCardId);quantityStep();
            },true));body.replaceChildren(warning);return;
        }

        const face=deck.tokens.faces.find(row=>row.cardId===front.id);
        selected={frontCardId:front.id,backCardId:other?.id,backKind:other?`token`:`card-back`,quantity:face.suggestedQuantity,
            assignment:{front:face.reference,back:other?deck.tokens.faces.find(row=>row.cardId===other.id).reference:{kind:`card-back`},quantity:face.suggestedQuantity}};
        quantityStep();
    };
    const chooseBack=()=>{
        body.replaceChildren(element(`p`,`Choose a different token face, or a normal card back. Naturally double-sided tokens keep their own reverse and cannot be selected here.`));
        const selectedFace=element(`p`,`Front: ${displayName(front)} · imported quantity ${front.quantity}`);body.append(selectedFace);
        const frontImage=element(`img`);frontImage.src=thumbnail(preview(front,front.faces[0]));frontImage.alt=`Selected front: ${displayName(front)}`;
        Object.assign(frontImage.style,{width:`95px`,maxHeight:`140px`,objectFit:`contain`,borderRadius:`8px`});body.append(frontImage);
        const choices=grid();choices.setAttribute(`aria-label`,`Available token backs`);
        const input=search(`Search token backs`,query=>{
            const text=query.trim().toLowerCase();
            for(const node of choices.children) {
                node.hidden=!node.dataset.search.includes(text);
            }

            empty.hidden=[...choices.children].some(node=>!node.hidden);
        });body.append(input,choices);
        const normal=imageTile(front,asset(deck.settings.backAsset),()=>select(null),{caption:`Normal card back`,title:`Normal card back`,dataKey:`tokenBack`,dataValue:`normal`});
        normal.dataset.search=`normal card back`;choices.append(normal);
        for(const face of deck.tokens.faces) {
            const other=cards.get(face.cardId);
            if(other.id===front.id)
                continue;

            const tile=imageTile(other,preview(other,other.faces[0]),()=>select(other),{quantity:`(${face.used})`,caption:displayName(other),dataKey:`tokenBack`,dataValue:other.id});
            tile.dataset.search=searchText(other);choices.append(tile);
        }

        const empty=element(`p`,`No token backs match your search.`);empty.hidden=true;body.append(empty,button(`Cancel`,()=>closeModal()));input.focus();
    };
    if(pair)
        quantityStep();
    else
        chooseBack();
};
//#endregion

//#region Deck image grid
export const mountDeckCards=(root,initial,view,{preview,backPreview,inspect,onChanged})=>{
    let deck=initial,approving=false;
    const tokenChanged=updated=>{
        if(view.filter===`tokens`)
            view.filter=`all`;

        return onChanged(updated);
    };
    root.replaceChildren();
    const toolbar=element(`div`);toolbar.className=`toolbar`;
    Object.assign(toolbar.style,{flexWrap:`wrap`,gap:`8px`,marginBottom:`0`});
    const filters=element(`div`);filters.className=`filter-pills`;
    Object.assign(filters.style,{height:`44px`,maxWidth:`100%`,minWidth:`0`,overflowX:`auto`,flex:`0 1 auto`});
    for(const [id,label] of [[`all`,`All cards`],[`unrendered`,`Not rendered`],[`attention`,`Needs Review`],[`tokens`,`Token Review`]]) {
        const control=button(label,()=>{view.filter=id;draw();});control.dataset.cardFilter=id;control.dataset.filterLabel=label;
        Object.assign(control.style,{display:`inline-flex`,alignItems:`center`,height:`36px`,minHeight:`36px`,padding:`6px 12px`,flexShrink:`0`});
        if(id!==`all`) {
            const count=element(`span`);count.dataset.filterCount=id;count.setAttribute(`aria-hidden`,`true`);
            Object.assign(count.style,{alignItems:`center`,justifyContent:`center`,minWidth:`18px`,height:`18px`,padding:`0 4px`,marginLeft:`6px`,borderRadius:`9px`,background:`#422918`,fontSize:`10px`,fontWeight:`700`});
            control.append(count);
        }

        filters.append(control);
    }

    const input=search(`Find a card or token…`,query=>{view.query=query;draw();});input.id=`card-search`;input.value=view.query;
    Object.assign(input.style,{marginTop:`0`,height:`44px`,minHeight:`44px`,minWidth:`0`,width:`auto`,flex:`1 1 240px`,padding:`8px 12px`});
    toolbar.append(filters,input);root.append(toolbar);
    const content=element(`div`);root.append(content);
    const draw=()=>{
        content.replaceChildren();
        const tokens=deck.tokens||{faces:[],assigned:[],cardIds:[],unused:[],invalid:[],ready:true};
        const byId=new Map(deck.cards.map(card=>[card.id,card])),tokenIds=new Set(tokens.cardIds),query=view.query.toLowerCase().trim();
        const counts={unrendered:Math.max(0,(deck.summary?.faces||0)-(deck.summary?.rendered||0)),attention:(deck.summary?.warnings||0)+(deck.summary?.errors||0),tokens:tokens.unused.length};
        for(const control of filters.children) {
            control.classList.toggle(`active`,control.dataset.cardFilter===view.filter);
            control.setAttribute(`aria-pressed`,String(control.dataset.cardFilter===view.filter));
            const counter=control.querySelector(`[data-filter-count]`);
            if(counter) {
                const count=counts[control.dataset.cardFilter];counter.textContent=String(count);
                counter.style.display=count?`inline-flex`:`none`;
                control.setAttribute(`aria-label`,`${control.dataset.filterLabel} (${count})`);
            }
        }

        const matches=card=>searchText(card).includes(query)&&(view.filter!==`unrendered`||card.faces.some(face=>!face.compiled?.render))&&
            (view.filter!==`attention`||card.faces.some(face=>face.error||((face.compiled?.crop?.warning||face.compiled?.flags?.length)&&face.acceptedWarningKey!==face.compiled?.renderKey)));
        const section=(title,description,kind)=>{
            const node=element(`section`);node.dataset.deckSection=kind;Object.assign(node.style,{marginTop:content.children.length?`12px`:`8px`,minWidth:`0`});
            node.append(element(`h2`,title),element(`p`,description));const items=grid();items.style.marginTop=`8px`;node.append(items);content.append(node);
            return {node,items};
        };
        if(!tokens.ready) {
            const notice=element(`section`);notice.className=`notice info`;notice.setAttribute(`aria-label`,`Tokens not ready`);
            notice.append(element(`strong`,`Tokens not ready`),element(`p`,`${tokens.unused.length} token ${tokens.unused.length===1?`face has`:`faces have`} no assigned copies. Pair different token faces to save space, or assign normal card backs. Printing is blocked until every face is used.`));
            if(view.filter!==`tokens`)
                notice.append(button(`Token Review`,()=>{view.filter=`tokens`;draw();}));

            if(tokens.unused.length)
                notice.append(button(`Assign normal backs to all unused faces`,async()=>{
                    const rows=savedRows(deck);
                    for(const unused of tokens.unused) {
                        const face=tokens.faces.find(face=>face.cardId===unused.cardId);
                        rows.push({front:face.reference,back:{kind:`card-back`},quantity:face.suggestedQuantity});
                    }

                    await persist(deck,rows,tokenChanged);
                }));

            for(const row of tokens.invalid) {
                notice.append(element(`p`,`${row.name}: ${row.reason}`),button(`Remove invalid pairing`,()=>persist(deck,savedRows(deck).filter((item,index)=>index!==row.index),onChanged)));
            }

            content.append(notice);
        }

        const reviewFaces=view.filter===`attention`?deck.cards.flatMap(card=>card.faces.filter(face=>!face.error&&face.compiled?.render&&
            (face.compiled.crop?.warning||face.compiled.flags?.length)&&face.acceptedWarningKey!==face.compiled.renderKey)
            .map(face=>({cardId:card.id,faceId:face.id,renderKey:face.compiled.renderKey}))):[];
        const reviewRevision=deck.revision;
        if(view.filter===`attention`&&reviewFaces.length) {
            const approve=button(`All look good`,async()=>{
                if(approving)
                    return;

                approving=true;approve.disabled=true;
                let owner=null;
                try {
                    const confirmed=await confirmAction(`Approve all flagged artwork?`,
                        `Warning: Only click “All look good” if you have looked at every card in this deck and all artwork with warnings looks good. This approves ${reviewFaces.length} flagged card faces across the entire deck, including both sides and cards hidden by your search.`,
                        `All look good`);
                    if(!confirmed)
                        return;

                    owner=work.begin({label:`Save artwork approvals`,resources:[`deck:${deck.id}`]});
                    approve.textContent=`Saving approvals…`;approve.setAttribute(`aria-busy`,`true`);approve.setAttribute(`aria-pressed`,`true`);
                    Object.assign(approve.style,{transform:`translateY(2px)`,boxShadow:`inset 0 3px 6px #0008`,filter:`brightness(.8)`,cursor:`wait`});
                    const result=await api(`/api/decks/${deck.id}/accept-art`,{revision:reviewRevision,faces:reviewFaces},'POST',owner);
                    deck=result.deck;
                    const source=deck.settings.dataJsonSource;
                    const url=source?.kind===`github`?(source.value.startsWith(`https:`)?source.value:deck.settings.githubSetupFolder):``;
                    const document={version:1,cards:deck.cardData||[]};
                    const options={title:`Save artwork approvals`,autoSave:true,baseline:snapshot(deck),owner};
                    const saved=await offerDataSave(deck.id,result.changes,document,url,deck.cards,options).catch(error=>{
                        toast(`Saved in this deck. ${error.message}`,true);
                        return offerDataSave(deck.id,result.changes,document,url,deck.cards,{...options,autoSave:false});
                    });
                    if(saved?.github&&saved.github!==source?.value) {
                        const current=await api(`/api/decks/${deck.id}`);
                        await api(`/api/decks/${deck.id}/save`,{revision:current.revision,settings:{dataJsonSource:{kind:`github`,value:saved.github}}},'POST',owner);
                    }

                    await onChanged(await api(`/api/decks/${deck.id}`));
                    toast(`All reviewed artwork is accepted for printing.`);
                }
                finally {
                    if(owner)
                        work.finish(owner);

                    approving=false;approve.disabled=false;approve.textContent=`All look good`;
                    approve.removeAttribute(`aria-busy`);approve.removeAttribute(`aria-pressed`);approve.removeAttribute(`style`);
                    draw();
                }
            },true);
            approve.id=`approve-all-art`;approve.disabled=approving;approve.style.marginTop=`8px`;content.append(approve);
        }

        let count=0;
        if(view.filter!==`tokens`) {
            const cards=section(`Cards`,`Click a card to edit it. Hover or focus to view its back.`,`cards`);
            for(const card of deck.cards) {
                if(tokenIds.has(card.id)||!matches(card))
                    continue;

                const tile=imageTile(card,preview(card,card.faces[0]),()=>inspect(card,0),{back:backPreview(card,deck),quantity:`${card.quantity}×`,dataKey:`card`,dataValue:card.id});
                cards.items.append(tile);count++;
            }

            if(!cards.items.children.length)
                cards.node.append(element(`p`,`No non-token cards match.`));

            const substitutes=deck.settings.createDfcSubstitutes!==false?deck.cards.filter(card=>card.substitute&&!tokenIds.has(card.id)):[];
            if(substitutes.length) {
                const sectionView=section(`Double-sided card substitutes`,`One substitute per card copy, with the front's name and rules and a normal card back. Keep the matching double-sided cards beside the game.`,`substitutes`);
                for(const card of substitutes) {
                    const substitute={...card,name:card.substitute.name,faces:[card.substitute]};
                    if(!matches(substitute))
                        continue;

                    const source=preview(substitute,card.substitute);
                    const open=()=>{
                        const host=modal(card.substitute.name,``),body=$(`.modal-body`,host);
                        const image=element(`img`);image.src=source;image.alt=card.substitute.name;
                        Object.assign(image.style,{display:`block`,width:`100%`,maxHeight:`75vh`,objectFit:`contain`});
                        body.append(image,element(`p`,`Generated from this card's front. Change the original card to update its substitute.`),button(`Close`,()=>closeModal()));
                    };
                    sectionView.items.append(imageTile(substitute,source,open,{back:asset(deck.settings.backAsset||state.bootstrap.backs?.default?.id),quantity:`${card.quantity}×`,title:`${displayName(card)} · substitute`,dataKey:`substitute`,dataValue:card.id}));count++;
                }

                if(!sectionView.items.children.length)
                    sectionView.node.append(element(`p`,`No substitutes match.`));
            }
        }

        if(tokens.cardIds.length||view.filter===`tokens`) {
            const faces=section(`Token faces`,`Counts include assigned copies on either side. Faces can be reused in multiple pairings. Click a face to choose its back.`,`token-faces`);
            for(const face of tokens.faces) {
                const card=byId.get(face.cardId);
                if(!matches(card)||view.filter===`tokens`&&face.used!==0)
                    continue;

                const tile=imageTile(card,preview(card,card.faces[0]),()=>assignToken(deck,card,tokenChanged,preview),{quantity:`(${face.used})`,caption:`${face.used} assigned · ${face.suggestedQuantity} imported`,dataKey:`tokenFace`,dataValue:card.id});
                tile.append(button(`Edit face`,()=>inspect(card,0)));faces.items.append(tile);count++;
            }

            if(!faces.items.children.length)
                faces.node.append(element(`p`,view.filter===`tokens`?`Every token face is assigned.`:`No single-sided token faces match.`));

            if(view.filter!==`tokens`) {
                const assigned=section(`Assigned tokens`,`One tile per physical front/back combination. Hover or focus to flip; click to edit quantity or pairing.`,`assigned-tokens`);
                for(const pair of tokens.assigned) {
                    const front=byId.get(pair.frontCardId),other=byId.get(pair.backCardId);
                    if(!matches(front)&&!(other&&matches(other)))
                        continue;

                    const back=pair.backKind===`reverse`?preview(front,front.faces[1]):other?preview(other,other.faces[0]):asset(deck.settings.backAsset);
                    const caption=`${displayName(front)} / ${pair.backKind===`reverse`?front.faces[1].name:other?displayName(other):`Normal back`}`;
                    assigned.items.append(imageTile(front,preview(front,front.faces[0]),()=>assignToken(deck,front,tokenChanged,preview,pair,inspect),{back,quantity:`${pair.quantity}×`,caption,dataKey:`tokenPair`,dataValue:String(pair.index??`natural-${front.id}`)}));count++;
                }

                if(!assigned.items.children.length)
                    assigned.node.append(element(`p`,`No assigned tokens yet. Select a token face above to create your first pairing.`));
            }
        }

        if(!count&&view.filter!==`tokens`)
            content.append(element(`p`,`No cards match. Try a different search or filter.`));
    };
    draw();
    return {refresh:updated=>{deck=updated;draw();}};
};
//#endregion

//#region Convert an existing card
export const convertToToken=(deck,card,onChanged)=>{
    const host=modal(`Token options · ${card.name}`,``,{size:`small`}),body=$(`.modal-body`,host);
    body.append(element(`p`,`Apply token treatment to this card. Its imported quantity becomes a suggestion; assigned token pairings determine how many copies print.`));
    const options=card.tokenSpec||{};
    const label=element(`label`),nonlegendary=element(`input`);nonlegendary.type=`checkbox`;nonlegendary.checked=options.nonlegendary!==false;
    label.append(nonlegendary,document.createTextNode(` Make nonlegendary`));body.append(label);
    const fields={};
    for(const [id,title,value] of [[`subtypes`,`Creature subtypes (optional)`,Array.isArray(options.replace_creature_subtypes)?options.replace_creature_subtypes.join(` `):options.replace_creature_subtypes||``],[`pt`,`Power / toughness (optional)`,options.power_toughness||``]]) {
        const label=element(`label`,title);label.className=`field`;const field=element(`input`);field.value=value;field.setAttribute(`aria-label`,title);label.append(field);body.append(label);fields[id]=field;
    }

    const colorLabel=element(`label`,`Frame color`);colorLabel.className=`field`;
    const color=element(`select`);color.setAttribute(`aria-label`,`Token frame color`);
    for(const [value,title] of [[``,`Use source color`],[`W`,`White`],[`U`,`Blue`],[`B`,`Black`],[`R`,`Red`],[`G`,`Green`],[`M`,`Multicolor`],[`A`,`Artifact`],[`L`,`Land`]]) {
        const option=element(`option`,title);option.value=value;color.append(option);
    }

    color.value=options.frame_color||``;colorLabel.append(color);body.append(colorLabel);

    body.append(button(`Apply token treatment`,async()=>{
        const spec={...options,nonlegendary:nonlegendary.checked};
        delete spec.replace_creature_subtypes;delete spec.power_toughness;delete spec.frame_color;
        if(color.value)
            spec.frame_color=color.value;
        if(fields.subtypes.value.trim())
            spec.replace_creature_subtypes=fields.subtypes.value.trim().split(/[, ]+/).filter(Boolean);
        if(fields.pt.value.trim())
            spec.power_toughness=fields.pt.value.trim();

        await persistTokenChange(deck,onChanged,()=>api(`/api/decks/${deck.id}/cards/${card.id}`,{revision:deck.revision,tokenSpec:spec}));
        toast(`Token treatment saved. Generate images to update this face.`);
    },true),button(`Cancel`,()=>closeModal()));
};
//#endregion
