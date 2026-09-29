const deckSites=[
  {host:/^(?:www\.)?archidekt\.com$/,path:/^\/decks\/(\d+)(?:\/[^?#]*)?$/},
  {host:/^(?:www\.)?mtggoldfish\.com$/,path:/^\/deck\/(\d+)(?:\/[^?#]*)?$/}
];

export function identifyDeck(raw){
  const url=new URL(raw);
  if(url.protocol!=='https:'||url.username||url.password||url.port)
    throw new Error('Use a public HTTPS deck link.');
  const site=deckSites.find(item=>item.host.test(url.hostname)&&item.path.test(url.pathname));
  if(!site)throw new Error('Supported deck links: Scryfall, Archidekt, and MTGGoldfish.');
  const id=url.pathname.match(site.path)[1];
  return {site:site===deckSites[0]?'archidekt':'mtggoldfish',id};
}

export function parseArchidekt(data){
  if(!data||!Array.isArray(data.cards))throw new Error('Archidekt did not return a public deck.');
  const categories=new Map((data.categories||[]).map(item=>[item.name,item]));
  const rows=data.cards.filter(item=>!item.deletedAt).map(item=>{
    const labels=item.categories||[];
    const outside=labels.some(label=>categories.get(label)?.includedInDeck===false);
    const section=labels.includes('Commander')?'commanders':item.companion?'companion':outside?'outside':'mainboard';
    const card=item.card||{};
    const source=/^[0-9a-f-]{36}$/i.test(card.uid||'')?card.uid:card.oracleCard?.name;
    return {source,quantity:Number(item.quantity)||1,section};
  }).filter(item=>item.source&&item.quantity>0);
  if(!rows.length)throw new Error('The Archidekt deck has no importable cards.');
  return {name:data.name||'Archidekt deck',rows};
}

export function parseGoldfish(text,title='MTGGoldfish deck'){
  const rows=[];
  let section='mainboard';
  let sawCards=false;
  for(const raw of text.split(/\r?\n/)){
    const line=raw.trim();
    if(!line){if(sawCards)section='outside';continue;}
    if(/^(sideboard|maybeboard|commander|companion)\s*:?$/i.test(line)){
      section=/commander/i.test(line)?'commanders':'outside';
      continue;
    }
    const match=line.match(/^(\d+)\s+(.+)$/);
    if(!match)throw new Error(`Unrecognized MTGGoldfish card line: ${line.slice(0,80)}`);
    rows.push({source:match[2],quantity:Number(match[1]),section});
    sawCards=true;
  }
  if(!rows.length)throw new Error('The MTGGoldfish deck has no importable cards.');
  return {name:title,rows};
}

export function goldfishTitle(html,fallback){
  const match=html.match(/<meta\s+property=["']og:title["']\s+content=["']([^"']+)["']/i)
    ||html.match(/<title>([^<]+)<\/title>/i);
  return (match?.[1]||fallback).replace(/&amp;/g,'&').replace(/&#39;/g,"'").replace(/&quot;/g,'"').trim();
}
