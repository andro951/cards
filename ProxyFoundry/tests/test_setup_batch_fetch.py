"""The browser setup batch downloads concurrently and preserves binary bytes."""
from pathlib import Path
from test_review_export import review_browser


def test_browser_setup_batch_protocol_and_concurrency(review_browser):
    page=review_browser[0]
    source=(Path(__file__).resolve().parents[1]/'web/service-worker.js').read_text(encoding='utf-8')
    result=page.evaluate("""async source=>{
        const run=new Function(source+';return handleRequest;')();
        const original=window.fetch;let active=0,peak=0;
        window.fetch=async url=>{
            active++;peak=Math.max(peak,active);
            await new Promise(resolve=>setTimeout(resolve,20));active--;
            return new Response(new Uint8Array([0,128,255]),{headers:{'Content-Type':'image/png'}});
        };
        try {
            const urls=Array.from({length:6},(_,i)=>'https://raw.githubusercontent.com/o/r/main/'+i+'.png');
            const response=await run({request:new Request(location.origin+'/github-setup-fetch',{method:'POST',body:JSON.stringify(urls)})});
            const bytes=new Uint8Array(await response.arrayBuffer()),length=new DataView(bytes.buffer).getUint32(0);
            const rows=JSON.parse(new TextDecoder().decode(bytes.slice(4,4+length)));
            let rejected=false;
            try {await run({request:new Request(location.origin+'/github-setup-fetch',{method:'POST',body:JSON.stringify(['https://example.com/a'])})});}
            catch(error){rejected=true;}
            return {peak,rows,body:[...bytes.slice(4+length)],rejected};
        } finally {window.fetch=original;}
    }""",source)
    assert result['peak']==6 and result['rejected']
    assert result['rows']==[{'size':3,'mime':'image/png'}]*6
    assert result['body']==[0,128,255]*6