"""Real Chromium interactions against the real bundle endpoint and a fake remote."""
import os,json
import threading
from pathlib import Path

import pytest
from playwright.sync_api import expect

from test_browser import browser_app, sf
from test_github_setup import BundleRemote

pytestmark = pytest.mark.skipif(os.environ.get('PF_BROWSER') != '1', reason='Opt-in real Chromium tests')


@pytest.mark.parametrize('suffix',['','/art'],ids=['project','art-subfolder'])
def test_github_setup_one_click_populates_draft_preserves_other_edits_and_saves(browser_app,suffix):
    app, server, page, errors = browser_app
    d = app.ws.create({'name': 'Bundle import', 'source': sf()['id']})
    original_card = app.ws.deck(d['id'])['cards'][0]
    remote = BundleRemote(back='icon', data={'version':1,'cards':[
        {'name':'A Test Creature','nickname':'Dean Winchester','flavor_text':'The family business.'}
    ]})
    def transport(url):
        if '/commits/' in url:return json.dumps({'sha':'c'*40}).encode(),'application/json',{}
        raw,mime,headers=remote.transport(url.replace('?ref='+'c'*40,'?ref=main'))
        if '/contents/' in url:
            rows=json.loads(raw)
            for row in rows:
                if row['type']=='file':row['sha']='a'*40
            raw=json.dumps(rows).encode()
        return raw,mime,headers
    app.ws.net.transport = transport
    page.evaluate("import('/site/ui.js').then(m=>{m.state.bootstrap.browser=true})")
    page.goto(server.origin + '/#deck/' + d['id'] + '/setup')
    page.locator('#github-setup-button').wait_for()
    assert page.locator('#github-setup').evaluate('(el)=>el.nextElementSibling.id') == 'setup-fields'
    assert 'sol_ring.png' in page.locator('#github-setup pre').inner_text()
    page.fill('#deck-artist', 'Artist stays')
    page.fill('#github-setup-folder', remote.url+suffix)
    page.click('#github-setup-button')
    expect(page.locator('#github-setup-status')).to_contain_text('Review below, then save', timeout=20000)
    expect(page.locator('[data-mode=github]')).to_have_class('choice selected')
    expect(page.locator('#github-folder')).to_have_value(remote.url + '/art')
    expect(page.locator('#art-fallback')).not_to_be_checked()
    expect(page.locator('#fallback-line')).to_be_visible()
    expect(page.locator('.symbol-upload img')).to_have_count(4)
    expect(page.locator('[data-back-action=icon]')).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('#setup-state')).to_have_text('Unsaved changes')
    expect(page.locator('#data-json-status')).to_have_text('my deck/data.json')
    expect(page.locator('#data-json-preview')).to_have_count(0)
    assert app.ws.deck(d['id'])['settings']['symbols'] == app.ws.default_symbols()  # Existing defaults are unchanged until Save.
    assert not app.ws.deck(d['id'])['cards'][0]['faces'][0].get('semanticOverrides')  # data.json is staged too.
    expect(page.locator('#deck-artist')).to_have_value('Artist stays')
    page.click('#save-setup')
    page.locator('[data-artwork-card]').click();page.locator('[data-artwork-file]').click();page.click('#artwork-finish')
    page.get_by_role('button',name='Not now',exact=True).click()
    expect(page.locator('#setup-state')).to_have_text('Saved settings · changes stay local')
    saved = app.ws.deck(d['id'])
    assert saved['cards'][0] != original_card
    overrides=saved['cards'][0]['faces'][0]['semanticOverrides']
    assert overrides['nickname']=='Dean Winchester'
    assert overrides['flavor_text']=='The family business.'
    assert saved['settings']['artist'] == 'Artist stays'
    assert saved['settings']['templateRules'].get('standard','auto') == 'auto'
    assert saved['notes'] == ''
    assert saved['settings']['backDesign']['mode'] == 'icon'
    expect(page.locator('#github-setup-folder')).to_have_value(remote.url)
    page.evaluate('window.scrollTo(0,0)')
    (Path('test-results')).mkdir(exist_ok=True)
    page.screenshot(path='test-results/github-setup-desktop.png', full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
    page.screenshot(path='test-results/github-setup-mobile.png', full_page=True)
    assert not errors, errors


def test_single_symbol_bundle_is_rejected_without_changing_setup(browser_app):
    app, server, page, errors = browser_app
    d = app.ws.new_deck('Minimal bundle')
    app.ws.save(d['id'], {'revision': d['revision'], 'settings': {'source': {'mode': 'github', 'githubFolder': 'owner/old/art', 'fallback': False}}})
    remote = BundleRemote(art=False, folder=None, single=True)
    app.ws.net.transport = remote.transport
    page.goto(server.origin + '/#deck/' + d['id'] + '/setup')
    page.fill('#github-setup-folder', remote.url)
    page.press('#github-setup-folder', 'Enter')
    expect(page.locator('#github-setup-status')).to_contain_text('one-image symbol generation is no longer supported', timeout=20000)
    expect(page.locator('[data-mode=github]')).to_have_class('choice selected')
    expect(page.locator('#art-fallback')).not_to_be_checked()
    expect(page.locator('#fallback-line')).to_be_visible()
    expect(page.locator('[data-back-action=default]')).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('.symbol-upload img')).to_have_count(4)
    s = app.ws.deck(d['id'])['settings']
    assert s['source']['mode'] == 'github' and s['source']['fallback'] is False
    assert s['backDesign']['mode'] == 'default'
    assert not errors, errors


def test_failed_import_preserves_existing_draft_and_allows_retry(browser_app):
    app, server, page, errors = browser_app
    d = app.ws.new_deck('Failure then retry')
    remote = BundleRemote(art=False, back='custom', single=False)
    missing = remote.child('set_symbols/mythic.png')
    raw = remote.images[missing]
    remote.remove(missing)
    app.ws.net.transport = remote.transport
    page.goto(server.origin + '/#deck/' + d['id'] + '/setup')
    page.fill('#deck-artist', 'Unsaved artist')
    page.fill('#github-setup-folder', remote.url)
    page.click('#github-setup-button')
    expect(page.locator('#github-setup-status')).to_contain_text('missing: mythic.png', timeout=20000)
    expect(page.locator('#github-setup-status')).to_contain_text('Your setup was not changed')
    expect(page.locator('#github-setup-button')).to_be_enabled()
    expect(page.locator('#deck-artist')).to_be_enabled()
    expect(page.locator('#deck-artist')).to_have_value('Unsaved artist')
    expect(page.locator('#setup-state')).to_have_text('Unsaved changes')
    assert page.locator('.symbol-upload img').count() == 4  # Bundled defaults remain visible after the failed import.
    assert app.ws.deck(d['id'])['settings']['symbols'] == app.ws.default_symbols()
    remote.file(missing, raw)
    page.click('#github-setup-button')
    expect(page.locator('#github-setup-status')).to_contain_text('Review below, then save', timeout=20000)
    expect(page.locator('[data-back-action=custom]')).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('#deck-artist')).to_have_value('Unsaved artist')
    assert not errors, errors


def test_import_locks_manual_setup_and_cancel_restores_saved_state(browser_app):
    app, server, page, errors = browser_app
    d = app.ws.new_deck('Cancel bundle')
    remote = BundleRemote()
    release = threading.Event()
    def transport(url):
        if '/contents/' in url:
            assert release.wait(15), 'test must release the remote request'
        return remote.transport(url)
    app.ws.net.transport = transport
    page.goto(server.origin + '/#deck/' + d['id'] + '/setup')
    page.fill('#github-setup-folder', remote.url)
    try:
        page.click('#github-setup-button')
        expect(page.locator('#save-setup')).to_be_disabled()
        expect(page.locator('#deck-artist')).to_be_disabled()
        expect(page.locator('#github-setup-button')).to_be_disabled()
        expect(page.locator('#activity-cancel')).to_have_text('Cancel')
        page.click('#activity-cancel')
        expect(page.locator('#activity-cancel')).to_be_disabled()
        release.set()
        expect(page.locator('#github-setup-status')).to_contain_text('cancelled', timeout=20000)
        expect(page.locator('#save-setup')).to_be_enabled()
        assert not page.evaluate("document.querySelector('#setup-fields').inert")
        assert not page.evaluate("import('/site/ui.js').then(m=>m.state.dirty||m.state.busy)")
        assert page.locator('.symbol-upload img').count() == 4
        assert app.ws.deck(d['id'])['revision'] == d['revision']
        assert not errors, errors
    finally:
        release.set()


def test_one_click_without_symbols_uses_bundled_defaults(browser_app):
    app,server,page,errors=browser_app
    d=app.ws.create({'name':'Default symbols bundle','source':sf()['id']})
    remote=BundleRemote(art=False,folder=None,single=False,data={'version':1,'cards':[]})
    app.ws.net.transport=remote.transport
    page.goto(server.origin+'/#deck/'+d['id']+'/setup')
    page.fill('#github-setup-folder',remote.url)
    page.click('#github-setup-button')
    expect(page.locator('#github-setup-status')).to_contain_text('bundled default rarity symbols',timeout=20000)
    expect(page.locator('.symbol-upload img')).to_have_count(4)
    page.click('#save-setup')
    saved=app.ws.deck(d['id'])
    assert saved['settings']['symbols']==app.ws.default_symbols()
    assert not errors,errors
