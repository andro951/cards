import {identifyDeck,parseArchidekt,parseGoldfish,goldfishTitle} from '../../web/deck-adapters.mjs';

export async function onRequestGet({request}){
  try{
    const source=new URL(request.url).searchParams.get('url')||'';
    const {site,id}=identifyDeck(source);
    const endpoint=site==='archidekt'
      ?`https://archidekt.com/api/decks/${id}/`
      :`https://www.mtggoldfish.com/deck/download/${id}`;
    const response=await fetch(endpoint,{headers:{'Accept':site==='archidekt'?'application/json':'text/plain',
      'User-Agent':'Mozilla/5.0 (compatible; BulkProxyForge/2.0; deck import)'}});
    if(!response.ok)return json({error:`${site} returned HTTP ${response.status}. Check that this deck is public.`},502);
    if(Number(response.headers.get('Content-Length')||0)>5*1024*1024)
      return json({error:'The deck export is too large.'},413);
    let deck;
    if(site==='archidekt')deck=parseArchidekt(await response.json());
    else{
      const text=await response.text();
      const page=await fetch(`https://www.mtggoldfish.com/deck/${id}`,{headers:{'User-Agent':'Mozilla/5.0'}});
      const title=page.ok?goldfishTitle(await page.text(),`MTGGoldfish deck ${id}`):`MTGGoldfish deck ${id}`;
      deck=parseGoldfish(text,title);
    }
    return json(deck,200);
  }
  catch(error){return json({error:String(error.message||error)},400);}
}

function json(value,status){return new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'}});}
