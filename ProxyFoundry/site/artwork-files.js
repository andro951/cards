import {downloadBlob} from './ui.js';

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
    await sourceRecord(`deck:${deckId}`,{...previous,file:handle,document,github:null,fileSource});
};
export const rememberFolder=async(deckId,folder)=>{
    const previous=await sourceRecord(`deck:${deckId}`)||{};
    await sourceRecord(`deck:${deckId}`,{...previous,...(previous.fileSource!==`picked`?{file:null,document:null}:{}),folder,github:null});
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
const validateDocument=document=>{
    if(!document||document.version!==1||!Array.isArray(document.cards)||document.cards.length>10000||Object.keys(document).some(key=>![`version`,`cards`,`artist`].includes(key)))
        throw new Error(`The existing data.json is invalid. It was not changed.`);
    if(Object.hasOwn(document,`artist`)&&(typeof document.artist!==`string`||document.artist.length>300))
        throw new Error(`The existing data.json has an invalid deck artist. It was not changed.`);
    for(const entry of document.cards) {
        if(!entry||typeof entry!==`object`||Object.keys(entry).some(key=>![`name`,`oracle_id`,`scryfall_id`,`nickname`,`flavor_text`,`artist`,`art`,`scryfall_url`].includes(key)))
            throw new Error(`The existing data.json has an invalid card entry. It was not changed.`);
        for(const [key,value] of Object.entries(entry)) {
            if(value!=null&&typeof value!==`string`)throw new Error(`The existing data.json has invalid card data. It was not changed.`);
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
            if(baseline&&current.art!==old?.art&&current.art!==change.art)
                throw new Error(`An artwork mapping changed in the original data.json. Reimport it before saving.`);

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
        if(url)merged.scryfall_url=url;
        result.cards.push(merged);
    }

    validateDocument(result);
    return result;
};
export const dataBlob=document=>new Blob([JSON.stringify(document,null,2)+`\n`],{type:`application/json`});
export const downloadData=document=>downloadBlob(dataBlob(document),`data.json`);
export const saveLocalData=async(record,changes,cards=[])=>{
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

    const merged=enrichDataDocument(mergeDataDocument(original,changes,record.document),cards,changes);
    // Read and validate before creating a new file or opening the atomic writer.
    handle||=await record.folder.getFileHandle(`data.json`,{create:true});
    const writer=await handle.createWritable();
    try{await writer.write(JSON.stringify(merged,null,2)+`\n`);await writer.close();}
    catch(error){await writer.abort().catch(()=>{});throw error;}
    return {...record,file:handle,document:merged};
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
export const saveGithubData=async(location,token,changes,baseline=null,fetcher=fetch,cards=[])=>{
    if(!/^[^/]+\/[^/]+$/.test(location.repo)||!location.branch||location.path.split(`/`).at(-1)!==`data.json`||location.path.split(`/`).some(part=>!part||part===`.`||part===`..`))
        throw new Error(`Choose the repository’s data.json file.`);
    const url=`https://api.github.com/repos/${location.repo.split(`/`).map(encodeURIComponent).join(`/`)}/contents/${location.path.split(`/`).map(encodeURIComponent).join(`/`)}`;
    const headers={Accept:`application/vnd.github+json`,Authorization:`Bearer ${token}`,'Content-Type':`application/json`};
    const response=await fetcher(url+`?ref=`+encodeURIComponent(location.branch),{headers});
    if(!response.ok&&response.status!==404)
        throw new Error(`GitHub could not read data.json (${response.status}). Check your connection.`);

    const existing=response.status===404?null:await response.json();
    if(existing&&(!existing.sha||existing.encoding!==`base64`||typeof existing.content!==`string`))
        throw new Error(`GitHub returned an unreadable data.json. It was not changed.`);

    const original=existing?JSON.parse(decodeContent(existing.content)):{version:1,cards:[]};
    const merged=enrichDataDocument(mergeDataDocument(original,changes,baseline),cards,changes);
    const update=await fetcher(url,{method:`PUT`,headers,body:JSON.stringify({message:`Update BulkProxyForge artwork mappings`,branch:location.branch,
        content:encodeContent(JSON.stringify(merged,null,2)+`\n`),...(existing?{sha:existing.sha}:{})})});
    if(!update.ok)
        throw new Error(update.status===409?`data.json changed on GitHub. Reimport it before saving.`:`GitHub could not update data.json (${update.status}). Your mappings are saved in the deck.`);

    return merged;
};
//#endregion
