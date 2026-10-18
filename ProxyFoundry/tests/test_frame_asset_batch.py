"""Frame cache writes share a durable checkpoint and roll back on failure."""
import io

import pytest
from PIL import Image

from foundry.browser import BrowserStore
from foundry.network import Network
from foundry.server import App


def test_frame_assets_batch_durability_retry_and_reuse(tmp_path):
    saves=[]
    store=BrowserStore(tmp_path/'workspace',persist=lambda path:saves.append(path))
    network=Network(store)
    image=Image.new('RGB',(8,8),'red');buffer=io.BytesIO();image.save(buffer,'PNG')
    requests=[];fail=[True]
    def transport(url):
        requests.append(url)
        if url.endswith('/second.png') and fail[0]:raise RuntimeError('Interrupted download')
        return buffer.getvalue()+url.encode(),'image/png',{}
    network.transport=transport
    app=App(store,network)
    data={'frames':[{'src':'/img/first.png','masks':[{'src':'/img/second.png'}]}, {'src':'data:image/svg+xml;utf8,test'}]}
    app.frame_assets(data)
    assert not requests #The legacy local server needs no browser checkpoint batching.
    store.storage_type='browser'
    initial=store.stats();saves.clear()
    with pytest.raises(RuntimeError,match='Interrupted download'):app.frame_assets(data)
    assert store.stats()==initial
    assert not getattr(app,'_frame_assets_ready',set())
    fail[0]=False;saves.clear();app.frame_assets(data)
    assert len(saves)==1
    assert len(app._frame_assets_ready)==2
    before=len(requests);saves.clear();app.frame_assets(data)
    assert len(requests)==before and not saves
    #A subsequent runtime read finds the durable cache, without downloading again.
    app.runtime.fetch('/img/first.png')
    assert len(requests)==before

