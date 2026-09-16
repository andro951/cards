"""Byte-exact, bounded transfer archives (no renderer or artwork changes)."""
import hashlib
import io
import struct
import zipfile

import pytest
from foundry.domain import ValidationError
from foundry.transfer_batches import TransferBatches, MAX_BATCH_BYTES, MAX_CHUNK_BYTES
from test_server import running, request


def make_order(path, count=5, payload_size=600):
    files = {}
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_STORED) as z:
        for i in range(1, count + 1):
            for side in ('FRONT', 'BACK'):
                name = f'{side}/{i:06d}.png'
                raw = (f'{side}-{i}'.encode() * payload_size)[:payload_size]
                files[name] = raw
                z.writestr(name, raw)
    return files


def read_all(plan, batch, chunk=131):
    out = bytearray()
    for offset in range(0, plan.views[batch].size, chunk):
        out.extend(plan.read(batch, offset, chunk))
    return bytes(out)


def test_single_batch_is_the_original_archive_byte_for_byte(tmp_path):
    path = tmp_path/'order.zip';make_order(path)
    plan = TransferBatches(path, 5)
    assert len(plan.views) == 1
    assert read_all(plan, 0) == path.read_bytes()


def test_multiple_zips_preserve_all_copies_pairs_and_source_bytes(tmp_path):
    path = tmp_path/'order.zip';files = make_order(path)
    original = hashlib.sha256(path.read_bytes()).hexdigest()
    plan = TransferBatches(path, 5, limit=3000)
    assert [b['count'] for b in plan.metadata()] == [2, 2, 1]
    assert [b['firstCard'] for b in plan.metadata()] == [1, 3, 5]
    recovered = {}
    for batch, view in enumerate(plan.views):
        raw = read_all(plan, batch)
        assert len(raw) == view.size <= 3000
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            assert z.testzip() is None
            names = z.namelist()
            assert len(names) == 2*view.count
            for n in names:
                partner = n.replace('FRONT/', 'BACK/') if n.startswith('FRONT/') else n.replace('BACK/', 'FRONT/')
                assert partner in names and n not in recovered
                recovered[n] = z.read(n)
    assert recovered == files
    assert hashlib.sha256(path.read_bytes()).hexdigest() == original
    assert list(tmp_path.iterdir()) == [path]  # Virtual batches: no extra disk copies.


def test_exact_limit_includes_zip_headers_and_never_splits_a_pair(tmp_path):
    path=tmp_path/'order.zip';make_order(path, count=3)
    pair_bytes = 1200 + 2*(30+46) + 2*(len('FRONT/000001.png')+len('BACK/000001.png'))
    limit = 22 + 2*pair_bytes
    plan=TransferBatches(path,3,limit=limit)
    assert [v.count for v in plan.views] == [2,1]
    assert plan.views[0].size == limit
    assert [v.count for v in TransferBatches(path,3,limit=limit-1).views] == [1,1,1]
    with pytest.raises(ValidationError,match='cannot fit'):
        TransferBatches(path,3,limit=pair_bytes)


@pytest.mark.parametrize('batch,offset,length',[(-1,0,1),(9,0,1),(True,0,1),(0,-1,1),(0,0,0),(0,0,MAX_CHUNK_BYTES+1),(0,10**10,1)])
def test_invalid_ranges_are_rejected(tmp_path,batch,offset,length):
    path=tmp_path/'order.zip';make_order(path)
    with pytest.raises(ValidationError):TransferBatches(path,5).read(batch,offset,length)


def test_reject_missing_duplicate_or_unexpected_pairs(tmp_path):
    path=tmp_path/'order.zip';make_order(path,1)
    with pytest.raises(ValidationError,match='pairs'):TransferBatches(path,2)
    with zipfile.ZipFile(path,'a') as z:z.writestr('other.txt','ignored? no')
    with pytest.raises(ValidationError,match='pairs'):TransferBatches(path,1)


def test_source_modified_after_planning_cannot_be_transferred(tmp_path):
    path=tmp_path/'order.zip';make_order(path)
    plan=TransferBatches(path,5,limit=3000)
    with path.open('ab') as f:f.write(b'changed')
    with pytest.raises(ValidationError,match='changed'):plan.read(0,0,1)


def test_authenticated_batch_api_and_legacy_archive(running,monkeypatch):
    import foundry.transfer_batches as mod
    app,server=running
    order=app.store.put('orders',{'count':5,'cards':[],'decks':[]})
    path=app.store.home/'orders'/(order['id']+'.zip');make_order(path)
    monkeypatch.setattr(mod,'MAX_BATCH_BYTES',3000)
    status,t,_=request(server,'/api/orders/'+order['id']+'/transfer',{})
    assert status==200,t
    prefix='/api/transfer/'+t['id']
    assert request(server,prefix+'/metadata')[0]==403
    h={'X-Proxy-Transfer-Token':t['secret']}
    status,m,_=request(server,prefix+'/metadata',headers=h)
    assert status==200 and m['protocolVersion']==2
    assert [b['count'] for b in m['batches']]==[2,2,1]
    assert request(server,prefix+'/zip?batch=0',headers={'Range':'bytes=0-99'},raw=True)[0]==403
    for i,b in enumerate(m['batches']):
        status,data,headers=request(server,prefix+f'/zip?batch={i}',headers={**h,'Range':'bytes=0-9999'},raw=True)
        assert status==206 and len(data)==b['zipBytes']
        assert headers['Content-Range']==f'bytes 0-{len(data)-1}/{len(data)}'
        with zipfile.ZipFile(io.BytesIO(data)) as z:assert z.testzip() is None
    for suffix in ['?batch=-1','?batch=9','?batch=0&batch=1','?batch=../../x']:
        assert request(server,prefix+'/zip'+suffix,headers={**h,'Range':'bytes=0-9'})[0]==400
    assert request(server,prefix+'/zip?batch=0',headers=h)[0]==400
    assert request(server,prefix+'/zip?batch=0',headers={**h,'Range':f'bytes=0-{MAX_CHUNK_BYTES}'})[0]==400
    status,data,_=request(server,prefix+'/zip',headers={**h,'Range':'bytes=0-99'},raw=True)
    assert status==206 and data==path.read_bytes()[:100]


@pytest.mark.skipif(__import__('os').environ.get('PF_LARGE_TRANSFER')!='1',reason='Opt-in 2.3 GiB disk/stream stress test')
def test_real_278_card_multi_gigabyte_archive(tmp_path):
    import random
    from PIL import Image
    originals={}
    for side,seed in [('FRONT',501),('BACK',502)]:
        image=io.BytesIO()
        Image.frombytes('RGB',(1220,1220),random.Random(seed).randbytes(1220*1220*3)).save(image,'PNG')
        originals[side]=image.getvalue()
    path=tmp_path/'large-order.zip'
    with zipfile.ZipFile(path,'w',zipfile.ZIP_STORED) as z:
        for i in range(1,279):
            for side,raw in originals.items():z.writestr(f'{side}/{i:06d}.png',raw)
    def digest_file(p):
        h=hashlib.sha256()
        with p.open('rb') as stream:
            while chunk:=stream.read(MAX_CHUNK_BYTES):h.update(chunk)
        return h.hexdigest()
    before=digest_file(path)
    plan=TransferBatches(path,278)
    assert len(plan.views)==3 and path.stat().st_size>2*MAX_BATCH_BYTES
    recovered=0
    for i,view in enumerate(plan.views):
        dest=tmp_path/'part.zip'
        with dest.open('wb') as out:
            for offset in range(0,view.size,MAX_CHUNK_BYTES):out.write(plan.read(i,offset,MAX_CHUNK_BYTES))
        assert dest.stat().st_size==view.size<=MAX_BATCH_BYTES
        with zipfile.ZipFile(dest) as z:
            for name in z.namelist():
                side=name.split('/')[0]
                assert hashlib.sha256(z.read(name)).digest()==hashlib.sha256(originals[side]).digest()
                recovered+=1
        dest.unlink()
    assert recovered==556 and digest_file(path)==before
    print({'cards':278,'sourceBytes':path.stat().st_size,'batches':plan.metadata(),'verifiedImages':recovered})
