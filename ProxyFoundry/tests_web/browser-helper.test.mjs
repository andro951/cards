import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {parseArchidekt,parseGoldfish} from '../site/deck-adapters.mjs';

const source=readFileSync(new URL('../extension/background.js',import.meta.url),'utf8');
const sender={url:'https://andro951.github.io/cards/',tab:{id:7},frameId:0};

function helper(responses){
  let listener;
  const requested=[];
  const chrome={runtime:{onMessage:{addListener:fn=>listener=fn}},tabs:{onRemoved:{addListener:()=>{}}},storage:{session:{}}};
  const fetch=async(url,options)=>{
    requested.push({url,options});
    assert.equal(options.credentials,'omit');
    if(responses===null)return globalThis.fetch(url,options);
    const body=responses[url];
    assert.ok(body,`Unexpected deck request: ${url}`);
    return new Response(body,{headers:{'Content-Type':'text/plain'}});
  };
  runInNewContext(source,{chrome,fetch,URL,Response,AbortSignal,Date,Number,Error,setTimeout,clearTimeout});
  const request=(url,from=sender)=>new Promise(resolve=>{
    assert.equal(listener({type:'PF_DECK_FETCH',url},from,resolve),true);
  });
  return {request,requested};
}

test('the helper reads a public Archidekt deck on the user machine',async()=>{
  const card={quantity:2,categories:['Main'],card:{uid:'11111111-1111-1111-1111-111111111111'}};
  const {request,requested}=helper({'https://archidekt.com/api/decks/21700272/':JSON.stringify({name:'Example',categories:[],cards:[card]})});
  const result=await request('https://archidekt.com/decks/21700272/example');
  assert.equal(result.ok,true);
  assert.equal(result.deck.site,'archidekt');
  assert.equal(parseArchidekt(JSON.parse(result.deck.body)).rows[0].source,card.card.uid);
  assert.equal(requested.length,1);
});

test('the helper reads a public MTGGoldfish deck on the user machine',async()=>{
  const {request}=helper({
    'https://www.mtggoldfish.com/deck/download/4492960':'4 Lightning Bolt\n\nSideboard\n1 Negate',
    'https://www.mtggoldfish.com/deck/4492960':'<meta property="og:title" content="Example &amp; Friends">'
  });
  const result=await request('https://www.mtggoldfish.com/deck/4492960');
  assert.equal(result.ok,true);
  assert.equal(result.deck.title,'Example & Friends');
  assert.deepEqual(parseGoldfish(result.deck.body,result.deck.title).rows.map(row=>row.section),['mainboard','outside']);
});

test('the helper refuses arbitrary sites and untrusted tabs',async()=>{
  const {request,requested}=helper({});
  assert.equal((await request('https://archidekt.com@evil.example/decks/1')).ok,false);
  assert.equal((await request('https://www.mtggoldfish.com/deck/1',{url:'https://evil.example/',tab:{id:8},frameId:0})).ok,false);
  assert.equal(requested.length,0);
});

if(process.env.PF_LIVE_DECK_SITES==='1'){
  test('the browser helper imports a live public Archidekt deck',async()=>{
    const {request}=helper(null);
    const result=await request('https://archidekt.com/decks/21700272/cycle_of_the_five_dragon_stars');
    assert.equal(result.ok,true,result.error);
    assert.ok(parseArchidekt(JSON.parse(result.deck.body)).rows.length>50);
  });

  test('the browser helper imports a live public MTGGoldfish deck',async()=>{
    const {request}=helper(null);
    const result=await request('https://www.mtggoldfish.com/deck/4492960');
    assert.equal(result.ok,true,result.error);
    assert.ok(parseGoldfish(result.deck.body,result.deck.title).rows.length>50);
  });
}
