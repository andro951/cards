"""Independent, bounded ZIPs; original image bytes and saved order stay untouched."""
import io
import os
import random
import struct
import time
import zipfile

import pytest
from PIL import Image

from foundry.domain import ValidationError, uid
from foundry.transfer_zip import BATCH_LIMIT_BYTES, MAX_RANGE_BYTES, PairedZipTransfer
from test_server import running, request


def make_zip(path, count=5, compression=zipfile.ZIP_STORED):
    payloads = {}
    with zipfile.ZipFile(path, 'w', compression=compression) as z:
        for i in range(1, count + 1):
            for side in ('FRONT', 'BACK'):
                b = io.BytesIO()
                Image.new('RGB', (30 + i, 42 + i), (i * 20, 40 if side == 'FRONT' else 80, 150)).save(b, 'PNG')
                name = f'{side}/{i:06d}.png'
                payloads[name] = b.getvalue()
                z.writestr(name, b.getvalue())
    return payloads


def read_batch(view, index, chunk=73):
    size = view.batch(index).size
    return b''.join(view.read_range(index, offset, min(offset + chunk - 1, size - 1))
                    for offset in range(0, size, chunk))


def pair_footprint(payloads, i):
    return sum(76 + 2 * len(f'{side}/{i:06d}.png') + len(payloads[f'{side}/{i:06d}.png']) for side in ('FRONT', 'BACK'))


def test_small_transfer_preserves_the_entire_original_zip(tmp_path):
    p = tmp_path / 'order.zip';make_zip(p)
    before = p.read_bytes()
    view = PairedZipTransfer(p, 5)
    assert len(view.batches) == 1
    assert read_batch(view, 0) == before
    assert view.metadata()['batches'][0]['endCard'] == 5


@pytest.mark.parametrize('compression', [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED])
def test_multiple_complete_zips_preserve_every_byte_and_global_pair(compression, tmp_path):
    p = tmp_path / 'order.zip';payloads = make_zip(p, compression=compression)
    before = p.read_bytes()
    view = PairedZipTransfer(p, 5, limit=750)
    assert len(view.batches) > 1
    names = []
    for i, batch in enumerate(view.batches):
        raw = read_batch(view, i)
        assert len(raw) == batch.size <= 750
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            assert z.testzip() is None
            expected = [f'{s}/{n:06d}.png' for n in range(batch.start_card, batch.start_card + batch.count) for s in ('FRONT', 'BACK')]
            assert z.namelist() == expected
            for name in z.namelist():
                assert z.read(name) == payloads[name]
                with Image.open(io.BytesIO(z.read(name))) as im:
                    assert im.width == 30 + int(name.split('/')[1].split('.')[0])
            names.extend(z.namelist())
    assert names == list(payloads)
    assert sum(b.count for b in view.batches) == 5
    assert p.read_bytes() == before
    assert list(tmp_path.iterdir()) == [p], 'Transfer must not duplicate the giant ZIP on disk'


def test_exact_cap_includes_headers_and_splits_before_the_next_pair(tmp_path):
    p = tmp_path / 'order.zip';payloads = make_zip(p, 3)
    exact = 22 + pair_footprint(payloads, 1) + pair_footprint(payloads, 2)
    view = PairedZipTransfer(p, 3, limit=exact)
    assert [b.count for b in view.batches] == [2, 1]
    assert view.batches[0].size == exact
    tighter = PairedZipTransfer(p, 3, limit=exact - 1)
    assert tighter.batches[0].count == 1
    for b in tighter.batches:
        assert b.size <= exact - 1


def test_a_pair_that_cannot_fit_fails_instead_of_resizing_or_separating(tmp_path):
    p = tmp_path / 'order.zip';make_zip(p, 2)
    before = p.read_bytes()
    with pytest.raises(ValidationError, match='cannot be split'):
        PairedZipTransfer(p, 2, limit=100)
    assert p.read_bytes() == before


def test_sparse_order_over_4gb_has_bounded_views_and_large_source_offsets(tmp_path):
    """Exercise real 64-bit source seeks and the actual 1 GiB cap without 5 GB of RAM/disk.

    Sparse payloads are synthetic zero bytes, not print-ready PNGs. Small tests
    above check actual PNG CRCs/pixels; this tests ZIP64 addressing and budgeting.
    """
    p = tmp_path / 'large.zip';image_size = 300 * 1024 ** 2
    # ZipFile writes valid local/central/ZIP64 structures; seek creates sparse data.
    with zipfile.ZipFile(p, 'w', allowZip64=True) as archive:
        for i in range(1, 10):
            for side in ('FRONT', 'BACK'):
                info = zipfile.ZipInfo(f'{side}/{i:06d}.png');info.file_size = image_size
                with archive.open(info, 'w') as entry:
                    archive.fp.seek(image_size, 1)
                    entry._file_size = image_size  # Test-only sparse payload fixture.
                    entry._crc = 0
    assert p.stat().st_size > 4 * 1024 ** 3
    view = PairedZipTransfer(p, 9)
    assert len(view.batches) == 9
    assert all(b.size <= BATCH_LIMIT_BYTES for b in view.batches)
    last = view.batches[-1]
    assert view.read_range(8, 0, 3) == b'PK\x03\x04'
    assert view.read_range(8, last.size - 22, last.size - 1)[:4] == b'PK\x05\x06'
    # This payload lives beyond 4 GiB in the original file.
    payload_span = next(s for s in last.spans if isinstance(s[2], int))
    assert payload_span[2] > 4 * 1024 ** 3
    assert view.read_range(8, payload_span[0], payload_span[0] + 99) == bytes(100)


@pytest.mark.parametrize('start,end', [(-1, 10), (1, 0), (0, MAX_RANGE_BYTES), (True, 10), (10 ** 8, 10 ** 8)])
def test_invalid_ranges_are_rejected(tmp_path, start, end):
    p = tmp_path / 'order.zip';make_zip(p)
    with pytest.raises(ValidationError):
        PairedZipTransfer(p, 5).read_range(0, start, end)


def test_random_ranges_cross_headers_payloads_and_central_directory(tmp_path):
    p = tmp_path / 'order.zip';make_zip(p)
    view = PairedZipTransfer(p, 5, limit=750)
    randomizer = random.Random(32)
    for i, batch in enumerate(view.batches):
        raw = read_batch(view, i)
        for _ in range(50):
            start = randomizer.randrange(batch.size)
            end = randomizer.randrange(start, batch.size + 100)
            assert view.read_range(i, start, end) == raw[start:end + 1]


def test_missing_duplicate_or_extra_pair_members_fail(tmp_path):
    p = tmp_path / 'order.zip'
    with zipfile.ZipFile(p, 'w') as z:
        z.writestr('FRONT/000001.png', b'front')
        z.writestr('BACK/000002.png', b'back')
    with pytest.raises(ValidationError, match='exactly one front and back'):
        PairedZipTransfer(p, 1)


def test_modified_snapshot_is_not_streamed(tmp_path):
    p = tmp_path / 'order.zip';make_zip(p)
    view = PairedZipTransfer(p, 5)
    with p.open('ab') as f: f.write(b'changed')
    with pytest.raises(ValidationError, match='changed during transfer'):
        view.read_range(0, 0, 50)


def test_batch_http_authorization_ranges_and_legacy_download(running, monkeypatch):
    from foundry import transfer_zip
    app, server = running
    ident = uid();p = app.store.home / 'orders' / (ident + '.zip')
    payloads = make_zip(p);before = p.read_bytes()
    app.store.put('orders', {'id': ident, 'count': 5, 'cards': [], 'decks': []})
    monkeypatch.setattr(transfer_zip, 'BATCH_LIMIT_BYTES', 750)
    status, t, _ = request(server, '/api/orders/' + ident + '/transfer', {})
    assert status == 200
    base = '/api/transfer/' + t['id']
    h = {'X-Proxy-Transfer-Token': t['secret']}
    assert request(server, base + '/batches/0/zip', headers={'Range': 'bytes=0-99'})[0] == 403
    assert request(server, base + '/batches/0/zip', headers={**h, 'Range': 'bytes=0-99', 'X-Proxy-Transfer-Token': 'wrong'})[0] == 403
    status, meta, _ = request(server, base + '/metadata', headers=h)
    assert status == 200 and meta['protocol'] == 2 and len(meta['batches']) > 1
    names = []
    for b in meta['batches']:
        data = bytearray()
        for offset in range(0, b['zipBytes'], 79):
            status, raw, headers = request(server, base + f"/batches/{b['index']}/zip", headers={**h, 'Range': f'bytes={offset}-{offset + 78}'}, raw=True)
            assert status == 206
            assert headers['Content-Range'] == f"bytes {offset}-{offset + len(raw) - 1}/{b['zipBytes']}"
            data.extend(raw)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names.extend(z.namelist())
            for name in z.namelist(): assert z.read(name) == payloads[name]
    assert names == list(payloads)
    assert request(server, base + '/batches/0/zip', headers=h)[0] == 400
    assert request(server, base + '/batches/999/zip', headers={**h, 'Range':'bytes=0-99'})[0] == 400
    assert request(server, base + '/batches/0/zip', headers={**h, 'Range':'bytes=0-9999999'})[0] == 400
    assert request(server, base + '/zip', headers=h, raw=True)[1] == before
    app.transfers[t['id']]['expires'] = time.time() + 1
    request(server, base + '/metadata', headers=h)
    assert app.transfers[t['id']]['expires'] > time.time() + 3500
    app.transfers[t['id']]['expires'] = time.time() - 1
    assert request(server, base + '/batches/0/zip', headers={**h, 'Range':'bytes=0-99'})[0] == 403
