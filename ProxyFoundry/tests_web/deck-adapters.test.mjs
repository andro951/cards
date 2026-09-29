import test from 'node:test';
import assert from 'node:assert/strict';
import {identifyDeck,parseArchidekt,parseGoldfish} from '../web/deck-adapters.mjs';
import {onRequestGet} from '../functions/gateway/deck.js';

test('only supported public deck URLs are accepted',()=>{
  assert.deepEqual(identifyDeck('https://archidekt.com/decks/21700272/example'),{site:'archidekt',id:'21700272'});
  assert.deepEqual(identifyDeck('https://www.mtggoldfish.com/deck/4492960'),{site:'mtggoldfish',id:'4492960'});
  assert.throws(()=>identifyDeck('https://archidekt.com@evil.example/decks/1'));
  assert.throws(()=>identifyDeck('http://archidekt.com/decks/1'));
});

test('Archidekt preserves exact printings and outside sections',()=>{
  const card=uid=>({quantity:2,categories:['Main'],card:{uid,oracleCard:{name:'Sol Ring'}}});
  const data={name:'Example',categories:[{name:'Main',includedInDeck:true},{name:'Maybeboard',includedInDeck:false}],
    cards:[card('11111111-1111-1111-1111-111111111111'),{...card(''),categories:['Maybeboard']} ]};
  assert.deepEqual(parseArchidekt(data),{name:'Example',rows:[
    {source:'11111111-1111-1111-1111-111111111111',quantity:2,section:'mainboard'},
    {source:'Sol Ring',quantity:2,section:'outside'}]});
});

test('MTGGoldfish parses main and sideboard cards',()=>{
  assert.deepEqual(parseGoldfish('4 Lightning Bolt\n2 Island\n\nSideboard\n1 Negate').rows,[
    {source:'Lightning Bolt',quantity:4,section:'mainboard'},
    {source:'Island',quantity:2,section:'mainboard'},
    {source:'Negate',quantity:1,section:'outside'}]);
});

if(process.env.PF_LIVE_DECK_SITES==='1'){
  for(const [site,url] of [
    ['Archidekt','https://archidekt.com/decks/21700272/cycle_of_the_five_dragon_stars'],
    ['MTGGoldfish','https://www.mtggoldfish.com/deck/4492960']]){
    test(`${site} live public deck import`,async()=>{
      const response=await onRequestGet({request:new Request('https://foundry.example/gateway/deck?url='+encodeURIComponent(url))});
      assert.equal(response.status,200);
      const deck=await response.json();
      assert.ok(deck.name);
      assert.ok(deck.rows.length>50);
      assert.ok(deck.rows.every(row=>row.source&&row.quantity>0));
    });
  }
}
