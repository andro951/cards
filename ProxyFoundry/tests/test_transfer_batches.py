"""Independent ZIP readers validate streamed batches, not just size estimates."""
import hashlib
import io
import random
import zipfile

import pytest
from foundry.domain import ValidationError, uid
from foundry.transfer_batches import plan_batches, HELPER_ZIP_LIMIT, MAX_RANGE, LOCAL, CENTRAL, END
from test_server import running, request


def make_zip(path, count=5, compression=zipfile.ZIP_STORED):
    payloads = {}
    with zipfile.ZipFile(path, 'w', compression=compression) as z:
        for i in range(1, count + 1):
            for side in ('FRONT', 'BACK'):
                name = f'{side}/{i:06d}.png'
                payloads[name] = random.Random(i + len(side)).randbytes(127 + i)
                z.writestr(name, payloads[name])
    return payloads


def batch_bytes(batch, chunk=83):
    return b''.join(batch.read_range(i, min(chunk, batch.size - i))
                    for i in range(0, batch.size, chunk))


@pytest.mark.parametrize('compression', [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED])
def test_batches_are_complete_zip_files_with_exact_original_images(tmp_path, compression):
    path = tmp_path / 'source.zip'; payloads = make_zip(path, compression=compression)
    original = path.read_bytes()
    batches = plan_batches(path, 5, 1060)
    assert len(batches) > 1
    assert sum(b.metadata['count'] for b in batches) == 5
    seen = []
    for b in batches:
        assert b.size <= 1060
        raw = batch_bytes(b)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            assert z.testzip() is None
            for name in z.namelist():
                assert z.read(name) == payloads[name]
                seen.append(name)
            fronts = {n.split('/')[1] for n in z.namelist() if n.startswith('FRONT/')}
            backs = {n.split('/')[1] for n in z.namelist() if n.startswith('BACK/')}
            assert fronts == backs
        # Exercise random ranges, including boundaries between headers/payloads/tail.
        rng = random.Random(b.index)
        for _ in range(40):
            start = rng.randrange(b.size)
            length = rng.randint(1, b.size - start)
            assert b.read_range(start, length) == raw[start:start + length]
    assert len(seen) == len(set(seen)) == 10
    assert set(seen) == set(payloads)
    assert path.read_bytes() == original  # original downloadable order never rewritten


def test_cutoff_includes_headers_and_accepts_exact_limit(tmp_path):
    p = tmp_path / 'source.zip'; make_zip(p, 3)
    # First two pairs cost 948 bytes including every local/central header and EOCD.
    with zipfile.ZipFile(p) as z:
        first_two = 22 + sum(76 + 2 * len(i.filename) + i.compress_size for i in z.infolist()[:4])
    exact = plan_batches(p, 3, first_two)
    assert exact[0].size == first_two and exact[0].metadata['count'] == 2
    below = plan_batches(p, 3, first_two - 1)
    assert all(b.metadata['count'] == 1 for b in below)
    with pytest.raises(ValidationError, match='pair cannot be split'):
        plan_batches(p, 3, 100)


def test_small_archive_keeps_exact_bytes(tmp_path):
    p = tmp_path / 'source.zip'; make_zip(p, 2)
    b, = plan_batches(p, 2)
    assert batch_bytes(b) == p.read_bytes()


@pytest.mark.parametrize('start,length', [(-1, 1), (0, 0), (0, MAX_RANGE + 1), (2 ** 40, 1), (True, 1)])
def test_ranges_are_bounded(tmp_path, start, length):
    p = tmp_path / 'source.zip'; make_zip(p, 2)
    with pytest.raises(ValidationError):
        plan_batches(p, 2)[0].read_range(start, length)


def test_source_changes_cannot_silently_switch_order(tmp_path):
    p = tmp_path / 'source.zip'; make_zip(p)
    b = plan_batches(p, 5, 1060)[0]
    p.write_bytes(b'changed')
    with pytest.raises(ValidationError, match='changed'):
        b.read_range(0, 10)


def test_missing_duplicate_or_unpaired_files_rejected(tmp_path):
    p = tmp_path / 'source.zip'
    with zipfile.ZipFile(p, 'w') as z:
        z.writestr('FRONT/000001.png', b'x')
    with pytest.raises(ValidationError, match='exactly once'):
        plan_batches(p, 1)
    with zipfile.ZipFile(p, 'w') as z:
        z.writestr('FRONT/000001.png', b'x')
        z.writestr('BACK/000002.png', b'y')
    with pytest.raises(ValidationError, match='exactly once'):
        plan_batches(p, 1)


def test_real_one_gib_boundary_with_sparse_large_order(tmp_path):
    # Real >1 GB on-disk ZIP layout without allocating gigabytes of RAM or disk.
    # Payload CRC is immaterial to the planner; small fixtures above validate CRCs.
    p = tmp_path / 'large.zip'
    per_image = 300 * 1024 ** 2
    directory = []
    with p.open('wb') as f:
        for i in (1, 2):
            for side in ('FRONT', 'BACK'):
                name = f'{side}/{i:06d}.png'.encode(); offset = f.tell()
                common = (0, 0, 0, 33, 0, per_image, per_image, len(name))
                f.write(LOCAL.pack(0x04034B50, 20, *common, 0) + name)
                f.seek(per_image, 1)
                directory.append(CENTRAL.pack(0x02014B50, 20, 20, *common, 0, 0, 0, 0, 0, offset) + name)
        central_offset = f.tell(); central = b''.join(directory)
        f.write(central); f.write(END.pack(0x06054B50, 0, 0, 4, 4, len(central), central_offset, 0))
    assert p.stat().st_size > HELPER_ZIP_LIMIT
    batches = plan_batches(p, 2)
    assert len(batches) == 2
    assert all(b.size <= HELPER_ZIP_LIMIT for b in batches)
    assert all(b.metadata['count'] == 1 for b in batches)
    assert batches[1].read_range(LOCAL.size + len('FRONT/000002.png'), 16) == b'\0' * 16
    assert sum(len(s.source) for b in batches for s in b.segments if isinstance(s.source, bytes)) < 2000


def test_authenticated_batch_ranges_and_legacy_download(running, monkeypatch):
    from foundry import transfer_batches
    app, server = running
    ident = uid(); path = app.store.home / 'orders' / (ident + '.zip')
    payloads = make_zip(path, 5)
    app.store.put('orders', {'id':ident, 'count':5, 'cards':[], 'decks':[]})
    monkeypatch.setattr(transfer_batches, 'HELPER_ZIP_LIMIT', 1060)
    status, t, _ = request(server, '/api/orders/' + ident + '/transfer', {})
    assert status == 200
    base = '/api/transfer/' + t['id']
    h = {'X-Proxy-Transfer-Token': t['secret']}
    status, m, _ = request(server, base + '/metadata', headers=h)
    assert status == 200 and m['protocol'] == 2 and m['count'] == 5
    assert len(m['batches']) > 1
    assert 'path' not in json_text(m) and t['secret'] not in json_text(m)
    seen = set()
    for b in m['batches']:
        url = base + f"/batches/{b['index']}/zip"
        assert request(server, url, headers={'Range':'bytes=0-9'})[0] == 403
        assert request(server, url, headers=h)[0] == 400
        assert request(server, url, headers={**h, 'Range':f'bytes=0-{MAX_RANGE}'})[0] == 400
        status, raw, rh = request(server, url, headers={**h, 'Range':'bytes=0-9999'}, raw=True)
        assert status == 206 and len(raw) == b['zipBytes']
        assert rh['Content-Range'] == f"bytes 0-{len(raw)-1}/{len(raw)}"
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            assert z.testzip() is None
            for n in z.namelist():
                assert z.read(n) == payloads[n]; seen.add(n)
    assert seen == set(payloads)
    assert request(server, base + '/batches/999/zip', headers=h)[0] == 400
    assert request(server, base + '/zip', headers={**h, 'Range':'bytes=0-99'}, raw=True)[1] == path.read_bytes()[:100]
    old_expiry = app.transfers[t['id']]['expires']
    app.transfers[t['id']]['expires'] -= 3500
    request(server, base + '/metadata', headers=h)
    assert app.transfers[t['id']]['expires'] >= old_expiry


def json_text(value):
    import json
    return json.dumps(value)


def test_zip64_source_offsets_do_not_limit_total_order_size(tmp_path):
    p = tmp_path/'zip64.zip'
    with p.open('w+b') as stream:
        stream.seek(2**32 + 123)  # Sparse prefix forces genuine ZIP64 offsets.
        with zipfile.ZipFile(stream, 'w', allowZip64=True) as z:
            for side in ('FRONT', 'BACK'):
                z.writestr(side+'/000001.png', side.encode())
    assert p.stat().st_size > 2**32
    batch, = plan_batches(p, 1)
    assert batch.size < 1024
    with zipfile.ZipFile(io.BytesIO(batch_bytes(batch))) as z:
        assert z.testzip() is None
        assert z.read('FRONT/000001.png') == b'FRONT'
        assert z.read('BACK/000001.png') == b'BACK'
