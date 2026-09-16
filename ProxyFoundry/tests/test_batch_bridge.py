"""Shipped printer bridge against deterministic multi-upload DOM/messaging fixtures."""
import base64
import io
import os
from pathlib import Path
import zipfile

import pytest
from test_print_bridge import bridge_page, ROOT

pytestmark=pytest.mark.skipif(not(os.environ.get('PF_DOM')=='1' or os.environ.get('PF_BROWSER')=='1'),reason='Opt-in Chromium component tests')


def start_batches(page,existing=0,fail_batch=None,wrong_count=False,cancel_after_first=False):
    archives=[]
    for i in range(3):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:
            for side in ('FRONT','BACK'):z.writestr(f'{side}/{i+1:06d}.png',bytes([i])*100)
        archives.append(b.getvalue())
    page.set_content('''<html><body><h1>Editor</h1><div id="counter"></div>
    <label>Upload Front<input id="front" type="file" accept="image/*"></label>
    <label>Upload Deck ZIP<input id="zip" type="file" accept=".zip"></label>
    <button id="clear">Clear all cards</button><button id="back">Next Customize Back</button>
    <button id="preview">Next Preview</button><button id="checkout">Checkout</button>
    <style>button{min-width:50px;min-height:40px}</style></body></html>''')
    page.evaluate('''({archives,existing,failBatch,wrongCount,cancelAfterFirst})=>{
      window.tc={count:existing,uploads:[],requests:[],cleared:0,finished:0,preview:0,checkout:0};
      const draw=()=>document.querySelector('#counter').textContent=tc.count+' Cards';draw();
      document.querySelector('#clear').onclick=()=>{tc.count=0;tc.cleared++;draw()};
      document.querySelector('#preview').onclick=()=>tc.preview++;
      document.querySelector('#checkout').onclick=()=>tc.checkout++;
      document.querySelector('#zip').onchange=async e=>{
        const raw=[...new Uint8Array(await e.target.files[0].arrayBuffer())];tc.uploads.push(raw);
        const busy=document.createElement('div');busy.textContent='Processing card';document.body.append(busy);
        setTimeout(()=>{tc.count+=wrongCount?2:1;draw();busy.remove();
          if(cancelAfterFirst)document.querySelector('#pph-close').click();},300);
      };
      window.chrome={runtime:{sendMessage:async msg=>{
        if(msg.type==='PF_ORDER_METADATA')return {ok:true,protocolVersion:2,count:3,zipBytes:9999,batches:archives.map((b,index)=>({index,count:1,zipBytes:atob(b).length,filename:'batch-'+index+'.zip'}))};
        if(msg.type==='PF_ORDER_FINISHED'){tc.finished++;return {ok:true}};
        if(msg.type==='PF_ORDER_CHUNK'){
          tc.requests.push({batch:msg.batch,uploads:tc.uploads.length,count:tc.count});
          if(msg.batch===failBatch)return {ok:false,error:'Injected transfer failure'};
          const b=archives[msg.batch];return {ok:true,batch:msg.batch,offset:msg.offset,total:atob(b).length,length:atob(b).length,base64:b};
        }
        throw Error('Unexpected message');
      }}};
    }''',{'archives':[base64.b64encode(b).decode() for b in archives],'existing':existing,'failBatch':fail_batch,'wrongCount':wrong_count,'cancelAfterFirst':cancel_after_first})
    script=(ROOT/'extension/bridge.js').read_text().replace('new URLSearchParams(location.search)',"new URLSearchParams('?proxyFoundryOrder=fixture')")
    page.add_script_tag(content=script)
    return archives


@pytest.mark.parametrize('existing,action,expected,clears',[(0,None,3,0),(2,'add',5,0),(2,'replace',3,1)])
def test_batches_append_in_sequence_and_choose_once(bridge_page,existing,action,expected,clears):
    from playwright.sync_api import expect
    page,errors=bridge_page;raw=start_batches(page,existing)
    if action:
        page.locator('#pph-'+action).wait_for()
        assert page.evaluate('tc.uploads.length===0&&tc.cleared===0')
        page.click('#pph-'+action)
    expect(page.locator('#pph-line')).to_contain_text('Uploaded 3 paired cards',timeout=35000)
    result=page.evaluate('tc')
    assert [bytes(b) for b in result['uploads']]==raw
    assert result['count']==expected and result['cleared']==clears
    assert [(r['batch'],r['uploads']) for r in result['requests']]==[(0,0),(1,1),(2,2)]
    assert result['preview']==1 and result['checkout']==0 and result['finished']==1
    assert page.evaluate("document.querySelector('#zip').files.length") == 0
    assert not errors


def test_second_batch_failure_does_not_retry_or_send_third(bridge_page):
    from playwright.sync_api import expect
    page,errors=bridge_page;start_batches(page,fail_batch=1)
    expect(page.locator('#pph-line')).to_contain_text('Injected transfer failure',timeout=20000)
    result=page.evaluate('tc')
    assert [r['batch'] for r in result['requests']]==[0,1]
    assert len(result['uploads'])==1 and result['count']==1
    assert result['finished']==result['checkout']==result['preview']==0
    assert not errors


def test_count_mismatch_stops_before_next_batch(bridge_page):
    from playwright.sync_api import expect
    page,errors=bridge_page;start_batches(page,wrong_count=True)
    expect(page.locator('#pph-line')).to_contain_text('higher than expected',timeout=20000)
    assert page.evaluate('tc.uploads.length===1&&tc.requests.length===1&&tc.checkout===0')
    assert not errors


def test_cancel_stops_before_next_batch(bridge_page):
    page,errors=bridge_page;start_batches(page,cancel_after_first=True)
    page.wait_for_function('tc.uploads.length===1');page.wait_for_timeout(4000)
    assert page.evaluate('tc.uploads.length===1&&tc.requests.length===1&&tc.checkout===0&&tc.finished===0')
    assert not errors
