"""Shipped batching bridge in a controlled importer: append, stop and release."""
import base64
import io
import json
import os
import zipfile
from pathlib import Path

import pytest
from PIL import Image
from test_print_bridge import bridge_page

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not (os.environ.get('PF_DOM') == '1' or os.environ.get('PF_BROWSER') == '1'), reason='Opt-in Chromium component tests')


def start_batches(page, existing=0, failure_batch=None):
    batches = []
    raw_zips = []
    start = 1
    for index, count in enumerate([2, 1, 2]):
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w') as z:
            for n in range(start, start + count):
                for side in ('FRONT', 'BACK'):
                    im = io.BytesIO();Image.new('RGB', (20, 28), (n * 20, 30, 60)).save(im, 'PNG')
                    z.writestr(f'{side}/{n:06d}.png', im.getvalue())
        raw_zips.append(out.getvalue())
        batches.append({'index': index, 'count': count, 'startCard': start, 'endCard': start + count - 1,
                        'zipBytes': len(out.getvalue()), 'filename': f'Batch_{index}.zip'})
        start += count
    page.set_content('''<!doctype html><html><body>
    <h1>Card editor</h1><div id="counter">0 Cards</div>
    <label>Upload Front<input id="front" type="file" accept="image/*"></label>
    <label>Upload Deck ZIP<input id="zip" type="file" accept="application/zip,.zip"></label>
    <div id="cards"></div>
    <button id="next-back">Next — Customize Back</button>
    <button id="next-preview" hidden>Next — Preview</button><button id="checkout">Checkout</button>
    <style>button{min-width:30px;min-height:30px}[data-card-index]{width:90px;height:126px;display:inline-block;margin:6px;background:#ddd}
    [role=dialog]{position:fixed;left:400px;top:220px;background:white;padding:30px}</style>
    </body></html>''')
    page.evaluate('''({existing,batches,zips,failure})=>{
      window.tc={count:existing,uploads:[],requests:[],deleted:0,finished:0,preview:0,checkout:0,busy:false,overlap:0,retained:0};
      function draw(){
        document.querySelector('#counter').textContent=tc.count+' Cards';
        const cards=document.querySelector('#cards');cards.replaceChildren();
        for(let i=0;i<tc.count;i++){
          const tile=document.createElement('div');tile.dataset.cardIndex=i;
          const button=document.createElement('button');button.textContent='Remove card';
          button.onclick=()=>{
            const dialog=document.createElement('div');dialog.setAttribute('role','dialog');
            dialog.innerHTML='<h2>Delete this card?</h2><button class="delete">Delete card</button>';
            dialog.querySelector('button').onclick=()=>{tc.count--;tc.deleted++;dialog.remove();draw();};
            document.body.append(dialog);
          };tile.append(button);cards.append(tile);
        }
      }draw();
      document.querySelector('#zip').onchange=async e=>{
        if(tc.busy)tc.overlap++;
        tc.busy=true;
        const file=e.target.files[0];
        const data=[...new Uint8Array(await file.arrayBuffer())];
        const index=tc.uploads.length;tc.uploads.push({name:file.name,bytes:data});
        const busy=document.createElement('div');busy.textContent='Processing card';document.body.append(busy);
        await new Promise(resolve=>setTimeout(resolve,700));
        tc.count+=batches[index].count;draw();tc.busy=false;busy.remove();
      };
      document.querySelector('#next-back').onclick=()=>document.querySelector('#next-preview').hidden=false;
      document.querySelector('#next-preview').onclick=()=>tc.preview++;
      document.querySelector('#checkout').onclick=()=>tc.checkout++;
      window.chrome={runtime:{sendMessage:async msg=>{
        if(msg.type==='PF_ORDER_METADATA')return {ok:true,protocol:2,count:5,zipBytes:2*1024**3,batches};
        if(msg.type==='PF_ORDER_CHUNK'){
          tc.requests.push(msg.batch);
          if(msg.batch>0&&document.querySelector('#zip').files.length)tc.retained++;
          if(tc.busy)tc.overlap++;
          if(msg.batch===failure)return {ok:false,error:'Fixture transfer failure'};
          const b64=zips[msg.batch],n=atob(b64).length;
          return {ok:true,batch:msg.batch,offset:msg.offset,total:n,length:n,base64:b64};
        }
        if(msg.type==='PF_ORDER_FINISHED'){tc.finished++;return {ok:true};}
        throw new Error('Unexpected message');
      }}};
    }''', {'existing': existing, 'batches': batches, 'zips': [base64.b64encode(b).decode() for b in raw_zips], 'failure': failure_batch})
    page.add_script_tag(content=(ROOT / 'extension/transfer-protocol.js').read_text())
    script = (ROOT / 'extension/bridge.js').read_text().replace('new URLSearchParams(location.search)', "new URLSearchParams('?proxyFoundryOrder=fixture')")
    page.add_script_tag(content=script)
    return raw_zips


@pytest.mark.parametrize('existing,action,expected,deleted', [(0,None,5,0), (2,'add',7,0), (2,'replace',5,2)])
def test_batches_are_sequential_paired_and_add_replace_only_once(bridge_page,existing,action,expected,deleted):
    from playwright.sync_api import expect
    page, errors = bridge_page
    originals = start_batches(page, existing)
    if action:
        page.locator('#pph-' + action).wait_for()
        assert page.evaluate('tc.uploads.length===0&&tc.deleted===0')
        page.click('#pph-' + action)
    expect(page.locator('#pph-line')).to_contain_text('Uploaded 5 paired cards in 3 ZIP batches', timeout=40000)
    result = page.evaluate('tc')
    assert [bytes(u['bytes']) for u in result['uploads']] == originals
    assert result['requests'] == [0, 1, 2]
    assert result['count'] == expected and result['deleted'] == deleted
    assert result['preview'] == result['finished'] == 1 and result['checkout'] == 0
    assert result['overlap'] == result['retained'] == 0
    assert page.locator('#zip').evaluate('(el)=>el.files.length') == 0
    assert not errors


def test_second_batch_failure_does_not_send_third_or_retry_first(bridge_page):
    from playwright.sync_api import expect
    page, errors = bridge_page;originals = start_batches(page, failure_batch=1)
    expect(page.locator('#pph-line')).to_contain_text('FAILED', timeout=25000)
    result = page.evaluate('tc')
    assert result['requests'] == [0, 1]
    assert [bytes(u['bytes']) for u in result['uploads']] == originals[:1]
    assert result['count'] == 2 and result['preview'] == result['checkout'] == result['deleted'] == 0
    expect(page.locator('#pph-sub')).to_contain_text('1 ZIP batches (2 cards) confirmed')
    assert not errors


def test_cancel_during_first_upload_stops_all_later_batches(bridge_page):
    page, errors = bridge_page;start_batches(page)
    page.wait_for_function('tc.uploads.length===1')
    page.click('#pph-close')
    page.wait_for_timeout(1500)
    result = page.evaluate('tc')
    assert result['requests'] == [0] and len(result['uploads']) == 1
    assert result['preview'] == result['checkout'] == result['finished'] == 0
    assert not errors
