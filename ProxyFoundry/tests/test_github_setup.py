"""GitHub bundles stage a complete setup without ever changing a saved deck."""
import copy
import io
import json
import os
from urllib.parse import quote

import pytest
from PIL import Image

from foundry.domain import RARITIES, ValidationError
from foundry.github_setup import import_github_setup
from foundry.images import decode_image, ingest_image, rarity_variants
from foundry.network import Network
from foundry.storage import Store
from foundry.workspace import Workspace
from test_server import running, request, job_done


def png(color=(100, 140, 200, 180), size=(160, 160)):
    out = io.BytesIO()
    Image.new('RGBA', size, color).save(out, 'PNG')
    return out.getvalue()


def padded_png(size, visible_box, color=(100,140,200,180)):
    out=io.BytesIO();im=Image.new('RGBA',size,(0,0,0,0))
    im.paste(color,visible_box);im.save(out,'PNG');return out.getvalue()


class BundleRemote:
    """A bounded public GitHub-like transport; unexpected requests fail the test."""
    def __init__(self, *, art=True, folder='set_symbols', single=False, back=None,
                 project='my deck', ref='main'):
        self.repo = 'owner/repo'
        self.project, self.ref = project, ref
        self.rows, self.images, self.calls = {}, {}, []
        self.directory(project)
        if art:
            self.directory(self.child('art'))
            self.file(self.child('art/sol_ring.png'), png())
        if folder:
            self.directory(self.child(folder))
            for n, rarity in enumerate(RARITIES):
                self.file(self.child(folder + '/' + rarity + '.png'), png((40*n, 60, 90, 170)))
            self.file(self.child(folder + '/README.txt'), b'notes')
        if single:
            self.file(self.child('set_symbol.png'), png())
        if back in {'custom', 'both'}:
            self.file(self.child('back.png'), png((15, 40, 80, 255), (300, 420)))
        if back in {'icon', 'both'}:
            self.file(self.child('back_icon.png'), png((80, 150, 40, 140), (800, 400)))

    def child(self, path):
        return self.project + '/' + path if self.project else path

    def directory(self, path):
        self.rows[path] = []
        if path != self.project:
            parent, _, name = path.rpartition('/')
            self.rows[parent].append({'name': name, 'path': path, 'type': 'dir'})

    def file(self, path, raw):
        parent, _, name = path.rpartition('/')
        self.rows[parent].append({'name': name, 'path': path, 'type': 'file'})
        self.images[path] = raw

    def remove(self, path):
        parent, _, name = path.rpartition('/')
        self.rows[parent] = [r for r in self.rows[parent] if r['name'] != name]
        self.images.pop(path, None)

    @property
    def url(self):
        return 'https://github.com/' + self.repo + '/tree/' + quote(self.ref, safe='') + ('/' + quote(self.project, safe='/') if self.project else '')

    def transport(self, url):
        self.calls.append(url)
        if url == 'https://api.github.com/repos/' + self.repo:
            return json.dumps({'default_branch': self.ref}).encode(), 'application/json', {}
        for path, rows in self.rows.items():
            api = 'https://api.github.com/repos/' + self.repo + '/contents/' + quote(path, safe='/') + '?ref=' + quote(self.ref, safe='')
            if url == api:
                return json.dumps(rows).encode(), 'application/json', {}
        for path, raw in self.images.items():
            full = 'https://raw.githubusercontent.com/' + self.repo + '/' + quote(self.ref, safe='') + '/' + quote(path, safe='/')
            if url == full:
                return raw, 'image/png', {}
        raise AssertionError('Unexpected network request: ' + url)


def workspace(tmp_path, remote):
    store = Store(tmp_path)
    return Workspace(store, Network(store, transport=remote.transport, sleeper=lambda _: None))


def test_four_symbols_live_art_and_icon_are_staged(tmp_path):
    remote = BundleRemote(back='icon')
    ws = workspace(tmp_path, remote)
    deck = ws.new_deck('Untouched')
    before = copy.deepcopy(ws.store.get('decks', deck['id']))
    result = import_github_setup(ws, {'url': remote.url})
    s = result['settings']
    assert s['source'] == {'mode': 'github', 'githubFolder': remote.url + '/art', 'ref': 'main', 'fallback': True, 'localFiles': {}}
    assert set(s['symbols']) == set(RARITIES) and len(set(s['symbols'].values())) == 4
    assert result['summary'] == {'art': 'github', 'symbols': 'folder', 'back': 'icon'}
    assert s['backAsset'] == ws.backs.icon(s['backDesign']['iconAsset'])['id']
    assert decode_image(ws.store.asset_path(s['backAsset']).read_bytes()).size == (1055, 1491)
    assert ws.store.get('decks', deck['id']) == before
    assert not any('/art/' in url or 'scryfall' in url for url in remote.calls)
    assert s['githubSetupFolder'] == remote.url


@pytest.mark.parametrize('folder', ['set_symbols', 'set_symbol'])
def test_symbol_folder_alias_no_art_enables_scryfall_and_default_back(tmp_path, folder):
    remote = BundleRemote(art=False, folder=folder)
    ws = workspace(tmp_path, remote)
    result = import_github_setup(ws, {'url': remote.url})
    assert result['settings']['source'] == {'mode': 'scryfall', 'githubFolder': '', 'ref': '', 'fallback': True, 'localFiles': {}}
    assert result['settings']['backAsset'] == ws.backs.builtin('default')['id']
    assert result['summary']['symbols'] == 'folder'


def test_no_symbol_files_use_bundled_defaults(tmp_path):
    remote=BundleRemote(art=False,folder=None,single=False)
    ws=workspace(tmp_path,remote)
    result=import_github_setup(ws,{'url':remote.url})
    assert result['settings']['symbols']==ws.symbols.defaults()
    assert result['summary']['symbols']=='default'
    assert not any('set_symbol' in url for url in remote.calls)


def test_single_symbol_uses_existing_color_generator(tmp_path):
    remote = BundleRemote(art=False, folder=None, single=True)
    ws = workspace(tmp_path, remote)
    result = import_github_setup(ws, {'url': remote.url})
    original = ingest_image(ws.store, remote.images[remote.child('set_symbol.png')])
    assert result['settings']['symbols'] == rarity_variants(ws.store, original['id'])
    assert result['summary']['symbols'] == 'generated'
    assert 'not recommended' in result['warnings'][0]
    for asset in result['settings']['symbols'].values():
        assert decode_image(ws.store.asset_path(asset).read_bytes()).getchannel('A').getextrema() == (180, 180)


def test_github_symbols_and_custom_back_trim_fully_transparent_padding(tmp_path):
    remote=BundleRemote(art=False,back='custom')
    remote.images[remote.child('set_symbols/common.png')]=padded_png((160,160),(20,30,120,110))
    remote.images[remote.child('back.png')]=padded_png((400,600),(25,40,325,460),(15,40,80,255))
    ws=workspace(tmp_path,remote);result=import_github_setup(ws,{'url':remote.url})
    common=decode_image(ws.store.asset_path(result['settings']['symbols']['common']).read_bytes())
    back=decode_image(ws.store.asset_path(result['settings']['backAsset']).read_bytes())
    assert common.size==(100,80) and back.size==(300,420)


def test_precedence_four_images_over_single_and_complete_back_over_icon(tmp_path):
    remote = BundleRemote(single=True, back='both')
    ws = workspace(tmp_path, remote)
    result = import_github_setup(ws, {'url': remote.url})
    assert result['summary']['back'] == 'custom'
    assert result['summary']['symbols'] == 'folder'
    assert not any(url.endswith('/set_symbol.png') or url.endswith('/back_icon.png') for url in remote.calls)
    assert result['settings']['backAsset'] == ingest_image(ws.store, remote.images[remote.child('back.png')])['id']
    assert any('takes priority' in x for x in result['warnings'])


def test_plural_symbol_folder_takes_priority_over_legacy_alias(tmp_path):
    remote = BundleRemote()
    remote.directory(remote.child('set_symbol'))  # Empty legacy folder is ignored.
    result = import_github_setup(workspace(tmp_path, remote), {'url': remote.url})
    assert result['summary']['symbols'] == 'folder'
    assert not any('/contents/my%20deck/set_symbol?' in u for u in remote.calls)


@pytest.mark.parametrize('problem,match', [
    ('missing', 'missing: mythic.png'),
    ('duplicate', 'Duplicate rare'),
    ('unexpected', 'Unexpected: extra.png'),
    ('corrupt', 'rare.png: Could not decode'),
    ('svg', 'export SVG to PNG'),
    ('symlink', 'symlink'),
    ('unsafe-path', 'unsafe or unexpected'),
])
def test_bad_symbol_folder_fails_without_falling_back_or_mutating_deck(tmp_path, problem, match):
    remote = BundleRemote(single=True)
    folder = remote.child('set_symbols')
    if problem == 'missing':
        remote.remove(folder + '/mythic.png')
    elif problem == 'duplicate':
        remote.file(folder + '/rare.jpg', png())
    elif problem == 'unexpected':
        remote.file(folder + '/extra.png', png())
    elif problem == 'corrupt':
        remote.images[folder + '/rare.png'] = b'not an image'
    elif problem == 'svg':
        remote.remove(folder + '/rare.png')
        remote.file(folder + '/rare.svg', b'<svg/>')
    elif problem == 'symlink':
        remote.rows[folder][0]['target'] = '../common.png'
    elif problem == 'unsafe-path':
        remote.rows[folder][0]['path'] = '../../bad.png'
    ws = workspace(tmp_path, remote)
    deck = ws.new_deck('Must survive')
    before = ws.store.get('decks', deck['id'])
    with pytest.raises(ValidationError, match=match):
        import_github_setup(ws, {'url': remote.url})
    assert ws.store.get('decks', deck['id']) == before
    assert not any(url.endswith('/set_symbol.png') for url in remote.calls)


@pytest.mark.parametrize('problem,match', [
    ('back-corrupt', 'back.png: Could not decode'),
    ('invisible-icon', 'fully transparent'),
    ('art-file', 'art must be a regular'),
    ('file-url', 'file, not a project folder'),
    ('listing-limit', 'too many entries'),
])
def test_invalid_bundle_does_not_return_partial_settings(tmp_path, problem, match):
    remote = BundleRemote(back='custom')
    if problem == 'back-corrupt':
        remote.images[remote.child('back.png')] = b'corrupt'
    elif problem == 'invisible-icon':
        remote.remove(remote.child('back.png'))
        remote.file(remote.child('back_icon.png'), png((0, 0, 0, 0)))
    elif problem == 'art-file':
        next(r for r in remote.rows[remote.project] if r['name'] == 'art')['type'] = 'file'
    elif problem == 'file-url':
        remote.rows[remote.project] = {'name': 'not-a-folder'}
    elif problem == 'listing-limit':
        remote.rows[remote.project] = [{}] * 1000
    with pytest.raises(ValidationError, match=match):
        import_github_setup(workspace(tmp_path, remote), {'url': remote.url})


@pytest.mark.parametrize('url', ['', None, 5, 'C:\\cards\\deck', 'https://evil.example/setup', 'file:///deck'])
def test_bad_urls_never_access_network(tmp_path, url):
    remote = BundleRemote()
    with pytest.raises(ValidationError):
        import_github_setup(workspace(tmp_path, remote), {'url': url})
    assert not remote.calls


def test_reimport_fetches_changed_images_and_listing_without_stale_cache(tmp_path):
    remote = BundleRemote(back='custom')
    ws = workspace(tmp_path, remote)
    first = import_github_setup(ws, {'url': remote.url})
    first_calls = len(remote.calls)
    remote.images[remote.child('set_symbols/rare.png')] = png((255, 30, 0, 200))
    remote.images[remote.child('back.png')] = png((200, 30, 0, 255), (300, 420))
    remote.remove(remote.child('art'))
    second = import_github_setup(ws, {'url': remote.url})
    assert len(remote.calls) == 2*first_calls
    assert first['settings']['symbols']['rare'] != second['settings']['symbols']['rare']
    assert first['settings']['symbols']['common'] == second['settings']['symbols']['common']
    assert first['settings']['backAsset'] != second['settings']['backAsset']
    assert second['settings']['source']['mode'] == 'scryfall'
    assert ws.net.hits == 0


@pytest.mark.parametrize('ref', ['main', 'art/v2', '1234567abc'])
def test_root_repository_default_ref_and_encoded_branch_are_preserved(tmp_path, ref):
    remote = BundleRemote(project='', ref=ref)
    ws = workspace(tmp_path, remote)
    result = import_github_setup(ws, {'url': 'https://github.com/owner/repo' if ref != '1234567abc' else remote.url})
    assert result['settings']['source']['ref'] == ref
    assert result['settings']['source']['githubFolder'] == remote.url + '/art'


@pytest.mark.parametrize('stage', ['start', 'download'])
def test_cancelled_import_cannot_change_saved_deck(tmp_path, stage):
    remote = BundleRemote()
    ws = workspace(tmp_path, remote)
    deck = ws.new_deck('Keep')
    before = ws.store.get('decks', deck['id'])
    def cancelled():
        return stage == 'start' or any(url.startswith('https://raw.') for url in remote.calls)
    with pytest.raises(ValidationError, match='cancelled'):
        import_github_setup(ws, {'url': remote.url}, cancel=cancelled)
    assert ws.store.get('decks', deck['id']) == before


def test_http_bundle_import_stages_then_revision_save_preserves_cards_and_options(running):
    app, server = running
    remote = BundleRemote(back='icon')
    # First create an exact-printing deck through the existing mock Scryfall transport.
    d = job_done(server, '/api/decks/import', {'name': 'Exact deck', 'source': '11111111-1111-4111-8111-111111111111'})
    original = copy.deepcopy(app.ws.deck(d['id']))
    app.ws.net.transport = remote.transport
    result = job_done(server, '/api/setup/github-import', {'url': remote.url})
    assert app.ws.deck(d['id']) == original  # Import itself is nonmutating.
    result['settings'].update(artist='Preserve artist', templateRules={'standard': 'normal'}, modificationCredit='Modified by ChatGPT')
    status, saved, _ = request(server, '/api/decks/' + d['id'] + '/save', {'revision': d['revision'], 'settings': result['settings']})
    assert status == 200
    assert saved['cards'] == original['cards']
    assert saved['settings']['artist'] == 'Preserve artist'
    assert saved['settings']['templateRules'] == {'standard': 'normal'}
    assert request(server, '/api/decks/' + d['id'] + '/save', {'revision': d['revision'], 'settings': result['settings']})[0] == 409
    assert request(server, '/api/setup/github-import', {'url': remote.url}, headers={'X-Proxy-CSRF': 'wrong'})[0] == 403
    assert request(server.runtime_server, '/api/setup/github-import', {'url': remote.url})[0] == 403
    assert all('scryfall' not in u for u in remote.calls)


@pytest.mark.skipif(os.environ.get('PF_LIVE_GITHUB_SETUP', os.environ.get('PF_LIVE_CC')) != '1', reason='Opt-in real GitHub source smoke test (full CI)')
def test_live_existing_eggs_fall_folder(tmp_path):
    """Fetch the actual legacy-named folder at a fixed commit, not a mock or fixture."""
    import hashlib
    ws = Workspace(Store(tmp_path))
    ref = '2e4181cfac724ef52fa4ed1719ab6593361539f0'
    url = 'https://github.com/andro951/cards/tree/' + ref + '/eggs_fall'
    result = import_github_setup(ws, {'url': url})
    assert result['summary'] == {'art': 'github', 'symbols': 'folder', 'back': 'custom'}
    assert result['settings']['source']['githubFolder'] == url + '/art'
    assert len(set(result['settings']['symbols'].values())) == 4
    raw_url = 'https://raw.githubusercontent.com/andro951/cards/' + ref + '/eggs_fall/back.png'
    cached = ws.store.cache_get(raw_url)
    raw = ws.store.asset_path(cached['asset_id']).read_bytes()
    assert hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == '917b086452111d0501e6ac011a2a9d70505291a8'
