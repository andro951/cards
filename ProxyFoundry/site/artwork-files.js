import {downloadBlob} from './ui.js';
import {recordDiagnostic} from './diagnostics.js';

//#region Saved handles and connections
let database;
const credentials=new Map();
const openStore=()=>database||=new Promise((resolve,reject)=>{
    const request=indexedDB.open(`BulkProxyForge artwork sources`,1);
    request.onupgradeneeded=()=>request.result.createObjectStore(`sources`);
    request.onsuccess=()=>resolve(request.result);
    request.onerror=()=>reject(request.error);
});
export const sourceRecord=async(key,value)=>{
    const db=await openStore();
    return new Promise((resolve,reject)=>{
        const tx=db.transaction(`sources`,value===undefined?`readonly`:`readwrite`);
        const store=tx.objectStore(`sources`);
        const request=value===undefined?store.get(key):value===null?store.delete(key):store.put(value,key);
        let result;
        request.onsuccess=()=>{result=request.result;};
        tx.oncomplete=()=>resolve(result);
        tx.onerror=()=>reject(tx.error);
        tx.onabort=()=>reject(tx.error||new Error(`Could not save artwork choices in this browser.`));
    });
};
export const rememberFile=async(deckId,handle,document,fileSource=`picked`)=>{
    const previous=await sourceRecord(`deck:${deckId}`)||{};
    await sourceRecord(`deck:${deckId}`,{...previous,file:handle,document,github:null,fileSource,tokenData:null,sourceBaseline:null});
};
export const rememberFolder=async(deckId,folder)=>{
    const previous=await sourceRecord(`deck:${deckId}`)||{};
    await sourceRecord(`deck:${deckId}`,{...previous,...(previous.fileSource!==`picked`?{file:null,document:null,tokenData:null,sourceBaseline:null}:{}),folder,github:null});
};
export const rememberGithub=async(deckId,url,document=null)=>{
    await sourceRecord(`deck:${deckId}`,{github:url,document});
};
export const pickArtworkFiles=async(deckId)=>{
    if(!window.showDirectoryPicker)
        return null;

    const folder=await window.showDirectoryPicker({id:`bulk-proxy-art`,mode:`read`});
    await rememberFolder(deckId,folder);
    const files=[];
    const walk=async(directory,prefix)=>{
        for await(const [name,handle] of directory.entries()) {
            if(name.startsWith(`.`))
                continue;

            const path=prefix+name;
            if(handle.kind===`directory`)
                await walk(handle,path+`/`);
            else if(/\.(png|jpe?g|webp|gif|json)$/i.test(name)) {
                const file=await handle.getFile();
                Object.defineProperty(file,`artworkPath`,{value:path});
                Object.defineProperty(file,`sourceHandle`,{value:handle});
                files.push(file);
            }

            if(files.length>5001)
                throw new Error(`Select at most 5,000 artwork images.`);
        }
    };
    await walk(folder,``);
    return files;
};
//#endregion

//#region Data file merge
const entryKey=entry=>JSON.stringify([entry.oracle_id?.toLowerCase()||``,entry.scryfall_id?.toLowerCase()||``,entry.name||``]);
const tokenReferenceKey=face=>{
    if(!face||typeof face!==`object`||Array.isArray(face)||typeof face.name!==`string`||!face.name.trim()||Object.keys(face).some(key=>![`name`,`oracle_id`,`scryfall_id`,`copy`,`art_variant`].includes(key)))
        throw new Error(`The existing data.json has an invalid token face. It was not changed.`);

    for(const [key,value] of Object.entries(face)) {
        if(typeof value!==`string`||value.length>300||/[\x00-\x1f]/.test(value)||(key.endsWith(`_id`)||key===`art_variant`)&&!/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value))
            throw new Error(`The existing data.json has an invalid token face. It was not changed.`);
    }

    return JSON.stringify([(face.oracle_id||``).toLowerCase(),(face.scryfall_id||``).toLowerCase(),face.name.trim(),(face.copy||``).trim(),(face.art_variant||``).toLowerCase()]);
};
const tokenRowKey=(field,row)=>{
    if(field===`artVariants`)
        return row.id;
    if(field===`tokenTreatments`)
        return tokenReferenceKey(row.face);

    const front=tokenReferenceKey(row.front);
    return JSON.stringify(row.back.kind?[front,row.back.kind]:[front,tokenReferenceKey(row.back)].sort());
};
export const equalDataValues=(left,right)=>{
    if(left===right)
        return true;

    if(!left||!right||typeof left!==`object`||typeof right!==`object`||Array.isArray(left)!==Array.isArray(right))
        return false;

    const keys=Object.keys(left);
    return keys.length===Object.keys(right).length&&keys.every(key=>Object.hasOwn(right,key)&&equalDataValues(left[key],right[key]));
};
const validateTokenFields=document=>{
    validateArtVariants(Object.hasOwn(document,`artVariants`)?document.artVariants:[]);
    for(const field of [`tokenAssignments`,`tokenTreatments`]) {
        if(!Object.hasOwn(document,field))
            continue;

        if(!Array.isArray(document[field])||document[field].length>10000)
            throw new Error(`The existing data.json has invalid token data. It was not changed.`);

        const seen=new Set();
        for(const row of document[field]) {
            if(!row||typeof row!==`object`||Array.isArray(row))
                throw new Error(`Invalid token entry in data.json.`);

            let key;
            if(field===`tokenAssignments`) {
                if(Object.keys(row).some(key=>![`front`,`back`,`quantity`].includes(key))||!Number.isInteger(row.quantity)||row.quantity<1||row.quantity>9999)
                    throw new Error(`Invalid token quantity in data.json.`);

                const front=tokenReferenceKey(row.front),back=row.back;
                const kind=back&&Object.keys(back).length===1&&[`card-back`,`reverse`].includes(back.kind)?back.kind:null;
                const backKey=kind||tokenReferenceKey(back);
                if(!kind&&front===backKey)
                    throw new Error(`A token cannot use the same face on both sides.`);

                key=JSON.stringify(kind?[front,kind]:[front,backKey].sort());
            }
            else {
                if(Object.keys(row).length!==2||!row.options||typeof row.options!==`object`||Array.isArray(row.options)||Object.keys(row.options).some(key=>![`nonlegendary`,`replace_creature_subtypes`,`power_toughness`,`frame_color`,`color_override`,`token_key_suffix`].includes(key)))
                    throw new Error(`Invalid token treatment in data.json.`);

                key=tokenReferenceKey(row.face);
            }

            if(seen.has(key))
                throw new Error(`Duplicate token combination in data.json. Adjust the existing quantity.`);

            seen.add(key);
        }
    }
};
export const validateArtVariants=rows=>{
    if(!Array.isArray(rows)||rows.length>10000)
        throw new Error(`Invalid alternate artwork in data.json.`);

    const seen=new Set(),uuid=/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
    for(const row of rows) {
        if(!row||Object.keys(row).sort().join(`,`)!==`card,faces,id,quantity`||!uuid.test(row.id)||seen.has(row.id.toLowerCase())||!Number.isInteger(row.quantity)||row.quantity<1||row.quantity>9999||!row.card?.name||!Array.isArray(row.faces)||!row.faces.length||row.faces.length>2)
            throw new Error(`Invalid alternate artwork in data.json.`);

        seen.add(row.id.toLowerCase());
        for(const [key,value] of Object.entries(row.card)) {
            if(![`name`,`oracle_id`,`scryfall_id`,`section`].includes(key)||typeof value!==`string`||!value.trim()||value.length>300||/[\x00-\x1f]/.test(value)||key.endsWith(`_id`)&&!uuid.test(value))
                throw new Error(`Invalid alternate-art card reference.`);
        }

        const names=new Set();
        for(const face of row.faces) {
            if(!face||Object.keys(face).sort().join(`,`)!==`art,name`||typeof face.name!==`string`||!face.name.trim()||face.name.length>300||names.has(face.name)||typeof face.art!==`string`||face.art.length>1000||/[\x00-\x1f\\:]/.test(face.art)||face.art.startsWith(`/`)||face.art.split(`/`).some(part=>!part||part===`.`||part===`..`)||! /\.(png|jpe?g|webp|gif)$/i.test(face.art))
                throw new Error(`Invalid alternate-art filename or face.`);

            names.add(face.name);
        }
    }

    return rows;
};
const validateDocument=document=>{
    if(!document||![1,2].includes(document.version)||!Array.isArray(document.cards)||document.cards.length>10000||Object.keys(document).some(key=>![`version`,`cards`,`artist`,`tokenAssignments`,`tokenTreatments`,`artVariants`,...(document.version===2?[`format`,`deck`,`templates`,`images`,`vectors`,`renderer`,`includesRenders`]:[])].includes(key)))
        throw new Error(`The existing data.json is invalid. It was not changed.`);
    if(document.version===2&&(document.format!==`bulk-proxy-forge-deck`||!document.deck||!document.images||document.includesRenders!==false))
        throw new Error(`The complete data.json is invalid. It was not changed.`);
    if(Object.hasOwn(document,`artist`)&&(typeof document.artist!==`string`||document.artist.length>300))
        throw new Error(`The existing data.json has an invalid deck artist. It was not changed.`);
    validateTokenFields(document);
    for(const entry of document.cards) {
        if(!entry||typeof entry!==`object`||Object.keys(entry).some(key=>![`name`,`oracle_id`,`scryfall_id`,`nickname`,`flavor_text`,`oracle_text`,`artist`,`art`,`scryfall_url`,`accepted_art`].includes(key)))
            throw new Error(`The existing data.json has an invalid card entry. It was not changed.`);
        for(const [key,value] of Object.entries(entry)) {
            if(key===`accepted_art`) {
                if(!Array.isArray(value)||value.length>1000||value.some(hash=>typeof hash!==`string`||!/^[a-f0-9]{64}$/.test(hash)))
                    throw new Error(`Invalid artwork approval in data.json. It was not changed.`);

                continue;
            }

            if(value!=null&&typeof value!==`string`)throw new Error(`The existing data.json has invalid card data. It was not changed.`);
            if(key===`oracle_text`&&value&&(value.length>20000||/[\x00-\x08\x0b-\x1f\x7f]/.test(value)))
                throw new Error(`The rules text is too long or contains unsupported control characters. It was not changed.`);
            if([`oracle_id`,`scryfall_id`].includes(key)&&value&&!/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value))
                throw new Error(`The existing data.json has an invalid UUID. It was not changed.`);
            if(key===`scryfall_url`&&value&&!/^https:\/\/scryfall\.com\/[^\s]+$/.test(value))
                throw new Error(`The existing data.json has an invalid Scryfall link. It was not changed.`);
            if(key===`art`&&value&&(/^[\/]|[\\:]/.test(value)||value.split(`/`).some(part=>!part||part===`.`||part===`..`)||! /\.(png|jpe?g|webp|gif)$/i.test(value)))
                throw new Error(`The existing data.json has an invalid artwork filename. It was not changed.`);
        }
    }
};
export const mergeDataDocument=(original,changes,baseline=null)=>{
    validateDocument(original);validateDocument({version:1,cards:changes});

    const result=structuredClone(original);
    const keys=new Set();
    for(const entry of result.cards) {
        if(!entry||typeof entry!==`object`||![`name`,`oracle_id`,`scryfall_id`].some(key=>typeof entry[key]===`string`&&entry[key]))
            throw new Error(`The existing data.json has an invalid card entry. It was not changed.`);
        const key=entryKey(entry);
        if(keys.has(key))throw new Error(`The existing data.json has duplicate card entries. It was not changed.`);
        keys.add(key);
    }
    const positions=new Map(result.cards.map((entry,index)=>[entryKey(entry),index]));
    const before=new Map((baseline?.cards||[]).map(entry=>[entryKey(entry),entry]));
    for(const change of changes) {
        const key=entryKey(change),position=positions.get(key);
        if(baseline&&position===undefined&&before.has(key))
            throw new Error(`A card entry was removed from the original data.json. Reimport it before saving.`);
        if(position!==undefined) {
            const current=result.cards[position],old=before.get(key);
            for(const field of Object.keys(change)) {
                if([`name`,`oracle_id`,`scryfall_id`,`scryfall_url`].includes(field))
                    continue;

                if(baseline&&!equalDataValues(current[field],old?.[field])&&!equalDataValues(current[field],change[field]))
                    throw new Error(`The ${field===`art`?`artwork mapping`:field===`oracle_text`?`rules text`:field} changed in the original data.json. Reimport it before saving.`);
            }

            result.cards[position]={...current,...change};
        }
        else {
            positions.set(key,result.cards.length);
            result.cards.push({...change});
        }
    }

    return result;
};
export const enrichDataDocument=(document,cards=[],changes=[])=>{
    validateDocument(document);
    const targets=new Map(),selectors=new Map(),variants=new Map();
    for(const card of cards) {
        const sf=card.scryfall||{},rawFaces=sf.card_faces||[sf];
        for(const face of card.faces||[]) {
            const raw=rawFaces[Math.min(face.index||0,rawFaces.length-1)]||sf;
            const name=raw.name||face.name||card.name,oracle_id=raw.oracle_id||sf.oracle_id,scryfall_id=sf.id;
            const identity={name,...(oracle_id?{oracle_id:oracle_id.toLowerCase()}:{}),...(scryfall_id?{scryfall_id:scryfall_id.toLowerCase()}: {})};
            const key=entryKey(identity),variant=JSON.stringify([identity.oracle_id||identity.scryfall_id||card.id,name]);
            if(!targets.has(key)){
                targets.set(key,{identity,variant,url:sf.scryfall_uri||raw.scryfall_uri,entries:[],updates:[]});
                variants.set(variant,(variants.get(variant)||0)+1);
            }
            for(let mask=1;mask<8;mask++) {
                const selector=entryKey({...(mask&1?{oracle_id:identity.oracle_id}:{}),...(mask&2?{scryfall_id:identity.scryfall_id}:{}),...(mask&4?{name}: {})});
                if(!selectors.has(selector))selectors.set(selector,new Set());
                selectors.get(selector).add(key);
            }
        }
    }

    const unmatched=[];
    for(const entry of document.cards) {
        const matches=selectors.get(entryKey(entry));
        if(!matches?.size)unmatched.push(structuredClone(entry));
        else {
            for(const key of matches)targets.get(key).entries.push(entry);
        }
    }

    for(const change of changes) {
        for(const key of selectors.get(entryKey(change))||[])targets.get(key).updates.push(change);
    }

    const result={...structuredClone(document),cards:unmatched};
    for(const {identity,variant,url,entries,updates} of targets.values()) {
        entries.sort((a,b)=>Number(!!a.oracle_id)*2+Number(!!a.scryfall_id)*2+Number(!!a.name)-Number(!!b.oracle_id)*2-Number(!!b.scryfall_id)*2-Number(!!b.name));
        const merged=Object.assign({},...entries,...updates,{name:identity.name});
        if(identity.oracle_id)merged.oracle_id=identity.oracle_id;
        if(identity.scryfall_id&&(!identity.oracle_id||variants.get(variant)>1))merged.scryfall_id=identity.scryfall_id;
        else if(identity.oracle_id)delete merged.scryfall_id;
        if(url)merged.scryfall_url=url;
        result.cards.push(merged);
    }

    validateDocument(result);
    return result;
};
export const dataBlob=document=>new Blob([JSON.stringify(document,null,2)+`\n`],{type:`application/json`});
export const mergeTokenData=(document,tokenData,baseline=null,localBaseline=baseline)=>{
    if(!tokenData)
        return document;

    validateTokenFields(document);validateTokenFields(tokenData);
    if(baseline)
        validateTokenFields(baseline);
    if(localBaseline)
        validateTokenFields(localBaseline);

    const result=structuredClone(document);
    for(const field of [`tokenAssignments`,`tokenTreatments`,`artVariants`]) {
        if(!Object.hasOwn(tokenData,field))
            continue;

        if(!Array.isArray(tokenData[field]))
            throw new Error(`Invalid saved token data.`);

        if(!baseline) {
            result[field]=structuredClone(tokenData[field]);
            continue;
        }

        //Merge each physical pair separately; other decks can share this data.json.
        const rows=values=>new Map((values||[]).map(row=>[tokenRowKey(field,row),row]));
        const current=rows(document[field]),before=rows(baseline[field]),localBefore=rows(localBaseline?.[field]),desired=rows(tokenData[field]);
        const value=row=>row&&(field===`tokenAssignments`?row.quantity:field===`artVariants`?row:row.options);
        for(const key of new Set([...localBefore.keys(),...desired.keys()])) {
            const old=before.get(key),next=desired.get(key),remote=current.get(key);
            if(equalDataValues(value(localBefore.get(key)),value(next)))
                continue;

            if(!equalDataValues(value(remote),value(old))&&!equalDataValues(value(remote),value(next))) {
                const row=next||old,label=field===`artVariants`?row.card.name:field===`tokenTreatments`?row.face.name:row.front.name+(row.back.kind?``:` / ${row.back.name}`);
                throw new Error(`${field===`artVariants`?`Alternate artwork`:field===`tokenAssignments`?`Token assignments`:`Token treatment`} for ${label} changed in the original data.json. Reimport it before saving.`);
            }

            if(next)
                current.set(key,structuredClone(next));
            else
                current.delete(key);
        }

        result[field]=[...current.values()];
    }

    validateTokenFields(result);
    return result;
};
export const mergeCardDataDocument=(original,changes,baseline=null,cards=[],tokenData=null,tokenBaseline=baseline)=>{
    if(!cards.length)
        return mergeTokenData(mergeDataDocument(original,changes,baseline),tokenData,baseline,tokenBaseline);

    //Compare equivalent selectors before merging, including face and printing IDs.
    const current=enrichDataDocument(original,cards);
    const before=baseline?enrichDataDocument(baseline,cards):null;
    const edits=enrichDataDocument({version:1,cards:changes},cards).cards.filter(entry=>
        [`nickname`,`flavor_text`,`oracle_text`,`artist`,`art`,`accepted_art`].some(field=>Object.hasOwn(entry,field)));
    return mergeTokenData(mergeDataDocument(current,edits,before),tokenData,baseline,tokenBaseline);
};
export const dataChangesPending=async(deckId,changes,document,cards=[])=>{
    const record=await sourceRecord(`deck:${deckId}`);
    const saved=record?.document||document;
    const current=enrichDataDocument(saved,cards);
    return JSON.stringify(current)!==JSON.stringify(mergeCardDataDocument(saved,changes,null,cards));
};
export const downloadData=document=>downloadBlob(dataBlob(document),`data.json`);
export const completeDataDocument=(merged,complete,original=null,baseline=null)=>{
    if(!complete)return merged;
    validateDocument(complete);
    if(original?.version===2){
        const identity=value=>value.deck.recipeId||value.deck.id;
        if(identity(original)!==identity(complete))throw new Error(`This data.json contains a different complete deck. Choose a separate file for this deck.`);
        if(baseline?.version===2&&!equalDataValues(original.deck,baseline.deck)&&!equalDataValues(original.deck,complete.deck))
            throw new Error(`The complete deck recipe changed on disk or GitHub. Import its latest version before saving.`);
    }
    const result=structuredClone(complete);
    for(const field of [`cards`,`artist`,`tokenAssignments`,`tokenTreatments`,`artVariants`])
        if(Object.hasOwn(merged,field))result[field]=structuredClone(merged[field]);
    return result;
};
export const saveLocalData=async(record,changes,cards=[],tokenData=null,complete=null)=>{
    const permissionHandle=record.file||record.folder;
    if(!permissionHandle)
        throw new Error(`This browser did not retain access to the original file or folder. Download data.json instead.`);

    if(await permissionHandle.queryPermission({mode:`readwrite`})!==`granted`&&await permissionHandle.requestPermission({mode:`readwrite`})!==`granted`)
        throw new Error(`Permission was not granted. Your original file was not changed.`);

    let handle=record.file;
    if(!handle) {
        try{handle=await record.folder.getFileHandle(`data.json`);}
        catch(error){if(error.name!==`NotFoundError`)throw error;}
    }

    let original={version:1,cards:[]};
    if(handle) {
        const file=await handle.getFile();
        original=JSON.parse(await file.text());
    }

    const merged=completeDataDocument(mergeCardDataDocument(original,changes,record.document,cards,tokenData,record.tokenData||record.document),complete,original,record.document);
    // Read and validate before creating a new file or opening the atomic writer.
    handle||=await record.folder.getFileHandle(`data.json`,{create:true});
    const writer=await handle.createWritable();
    try{await writer.write(JSON.stringify(merged,null,2)+`\n`);await writer.close();}
    catch(error){await writer.abort().catch(()=>{});throw error;}
    return {...record,file:handle,document:merged,...(tokenData?{tokenData:{...record.tokenData,...structuredClone(tokenData)}}:{})};
};
//#endregion

//#region GitHub data.json updates
export const githubDataLocation=url=>{
    const parsed=new URL(url);
    if(parsed.hostname===`raw.githubusercontent.com`) {
        const parts=parsed.pathname.split(`/`).filter(Boolean);
        parsed.hostname=`github.com`;parsed.pathname=`/${parts[0]}/${parts[1]}/blob/${parts.slice(2).join(`/`)}`;
    }
    if(parsed.protocol!==`https:`||![`github.com`,`www.github.com`].includes(parsed.hostname))
        throw new Error(`Choose a GitHub data.json file or project folder.`);

    const parts=parsed.pathname.split(`/`).filter(Boolean).map(decodeURIComponent);
    if(parts.length<4||![`tree`,`blob`].includes(parts[2]))
        throw new Error(`Choose a GitHub file or folder URL with a branch.`);

    const [owner,repository,,branch,...folder]=parts;
    if(folder.some(part=>part===`..`||part===`.`)||[owner,repository,branch,...folder].some(part=>/[\\\0]/.test(part)))
        throw new Error(`Invalid GitHub data.json path.`);

    if(folder.at(-1)!==`data.json`)
        folder.push(`data.json`);

    return {repo:owner+`/`+repository,branch,path:folder.join(`/`)};
};
export const githubCredential=async repo=>credentials.get(repo)||await sourceRecord(`github:${repo}`);
export const connectGithub=async(repo,token,remember)=>{
    token=token.trim();
    if(!token||/[\r\n]/.test(token))
        throw new Error(`Enter your GitHub connection token.`);

    credentials.set(repo,token);
    if(remember)
        await sourceRecord(`github:${repo}`,token);
    else
        await sourceRecord(`github:${repo}`,null);
};
export const disconnectGithub=async repo=>{
    credentials.delete(repo);
    await sourceRecord(`github:${repo}`,null);
};
const decodeContent=content=>new TextDecoder().decode(Uint8Array.from(atob(content.replace(/\s/g,``)),character=>character.charCodeAt(0)));
const encodeContent=content=>{
    const bytes=new TextEncoder().encode(content);
    let binary=``;
    for(let i=0;i<bytes.length;i+=32768) {
        binary+=String.fromCharCode(...bytes.subarray(i,i+32768));
    }

    return btoa(binary);
};
export const saveGithubData=async(location,token,changes,baseline=null,fetcher=fetch,cards=[],tokenData=null,tokenBaseline=baseline,complete=null)=>{
    if(!/^[^/]+\/[^/]+$/.test(location.repo)||!location.branch||location.path.split(`/`).at(-1)!==`data.json`||location.path.split(`/`).some(part=>!part||part===`.`||part===`..`))
        throw new Error(`Choose the repository’s data.json file.`);
    const url=`https://api.github.com/repos/${location.repo.split(`/`).map(encodeURIComponent).join(`/`)}/contents/${location.path.split(`/`).map(encodeURIComponent).join(`/`)}`;
    const headers={Accept:`application/vnd.github+json`,Authorization:`Bearer ${token}`,'Content-Type':`application/json`};
    const requestId=`${Date.now()}-${Math.random().toString(36).slice(2)}`;
    for(let attempt=0;attempt<3;attempt++) {
        //A previous successful save can leave the branch URL cached with an old SHA.
        const response=await fetcher(url+`?ref=`+encodeURIComponent(location.branch)+`&_bpf_save=${requestId}-${attempt}`,{headers,cache:`no-store`});
        if(!response.ok&&response.status!==404)
            throw new Error(`GitHub could not read data.json (${response.status}). Check your connection.`);

        const existing=response.status===404?null:await response.json();
        if(existing&&(!existing.sha||![`base64`,`none`].includes(existing.encoding)))
            throw new Error(`GitHub returned an unreadable data.json. It was not changed.`);

        let original={version:1,cards:[]};
        if(existing?.encoding===`base64`)original=JSON.parse(decodeContent(existing.content));
        else if(existing){
            //The contents API omits base64 for files over 1 MB. Read the same
            //immutable blob via raw media, retaining the SHA used for the PUT.
            const large=await fetcher(`https://api.github.com/repos/${location.repo}/git/blobs/${existing.sha}`,{headers:{...headers,Accept:`application/vnd.github.raw+json`},cache:`no-store`});
            if(!large.ok)throw new Error(`GitHub could not read the complete data.json (${large.status}).`);
            const text=await large.text();if(text.length>20*1024**2)throw new Error(`Complete data.json exceeds 20 MB.`);
            original=JSON.parse(text);
        }
        //Recheck the edited fields on every retry; never replace a concurrent rules edit.
        const merged=completeDataDocument(mergeCardDataDocument(original,changes,baseline,cards,tokenData,tokenBaseline),complete,original,baseline);
        if(complete)merged.deck.settings.dataJsonSource={kind:`github`,value:`https://github.com/${location.repo}/blob/${encodeURIComponent(location.branch)}/${location.path}`};
        if(complete&&equalDataValues(original,merged))return merged;
        const update=await fetcher(url,{method:`PUT`,headers,body:JSON.stringify({message:`Update BulkProxyForge card data`,branch:location.branch,
            content:encodeContent(JSON.stringify(merged,null,2)+`\n`),...(existing?{sha:existing.sha}:{})})});
        recordDiagnostic(`GitHub data save`,JSON.stringify({repo:location.repo,path:location.path,branch:location.branch,
            attempt:attempt+1,sha:existing?.sha||null,status:update.status||(update.ok?200:0)}));
        if(update.ok)
            return merged;

        if(update.status!==409)
            throw new Error(`GitHub could not update data.json (${update.status}). Your changes are saved in the deck.`);
    }

    throw new Error(`data.json kept changing on GitHub during saving. Your changes are saved in the deck. Try Save again.`);
};
//#endregion
