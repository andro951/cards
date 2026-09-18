"""Real Chromium interactions against the real bundle endpoint and a fake remote."""
import os
import threading
from pathlib import Path

import pytest
from playwright.sync_api import expect

from test_browser import browser_app, sf
from test_github_setup import BundleRemote

pytestmark = pytest.mark.skipif(os.environ.get('PF_BROWSER') != '1', reason='Opt-in real Chromium tests')


def test_github_setup_one_click_populates_draft_preserves_other_edits_and_saves(browser_app):
    app, server, page, errors = browser_app
    d = app.ws.create({'name': 'Bundle import', 'source': sf()['id']})
    original_deck = app.ws.deck(d['id'])
    original_card = original_deck['cards'][0]
    original_symbols = dict(original_deck['settings']['symbols'])
    remote = BundleRemote(back='icon')
    app.ws.net.transport = remote.transport
    page.goto(server.origin + '/#deck/' + d['id'] + '/setup')
    page.locator('#github-setup-button').wait_for()
    assert page.locator('#github-setup').evaluate('(el)=>el.nextElementSibling.id') == 'setup-fields'
    assert 'sol_ring.png' in page.locator('#github-setup pre').inner_text()
    page.fill('#deck-artist', 'Artist stays')
    page.fill('#deck-modification', 'Modified by ChatGPT')
    page.fill('#deck-notes', 'Do not replace my notes')
    page.select_option('[data-rule=standard]', 'normal')
    page.fill('#github-setup-folder', remote.url)
    page.click('#github-setup-button')
    expect(page.locator('#github-setup-status')).to_contain_text('Review below, then save', timeout=20000)
    expect(page.locator('[data-mode=github]')).to_have_class('choice selected')
    expect(page.locator('#github-folder')).to_have_value(remote.url + '/art')
    expect(page.locator('#github-ref')).to_have_value('main')
    expect(page.locator('#art-fallback')).to_be_checked()
    expect(page.locator('#fallback-line')).to_be_visible()
    expect(page.locator('.symbol-upload img')).to_have_count(4)
    expect(page.locator('[data-back-action=icon]')).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('#setup-state')).to_have_text('Unsaved changes')
    assert app.ws.deck(d['id'])['settings']['symbols'] == original_symbols  # GitHub import is staged until Save.
    expect(page.locator('#deck-artist')).to_have_value('Artist stays')
    expect(page.locator('#deck-notes')).to_have_value('Do not replace my notes')
    page.click('#save-setup')
    expect(page.locator('#setup-state')).to_have_text('Saved settings · changes stay local')
    saved = app.ws.deck(d['id'])
    assert saved['cards'][0] == original_card
    assert saved['settings']['artist'] == 'Artist stays'
    assert saved['settings']['modificationCredit'] == 'Modified by ChatGPT'
    assert saved['settings']['templateRules']['standard'] == 'normal'
    assert saved['notes'] == 'Do not replace my notes'
    assert saved['settings']['backDesign']['mode'] == 'icon'
    expect(page.locator('#github-setup-folder')).to_have_value(remote.url)
    page.evaluate('window.scrollTo(0,0)')
    (Path('test-results')).mkdir(exist_ok=True)
    page.screenshot(path='test-results/github-setup-desktop.png', full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
    page.screenshot(path='test-results/github-setup-mobile.png', full_page=True)
    assert not errors, errors


def test_no_art_single_symbol_import_selects_scryfall_and_checks_hidden_fallback(browser_app):
    app, server, page, errors = browser_app
    d = app.ws.new_deck('Minimal bundle')
    app.ws.save(d['id'], {'revision': d['revision'], 'settings': {'source': {'mode': 'github', 'githubFolder': 'owner/old/art', 'fallback': False}}})
    remote = BundleRemote(art=False, folder=None, single=True)
    app.ws.net.transport = remote.transport
    page.goto(server.origin + '/#deck/' + d['id'] + '/setup')
    page.fill('#github-setup-folder', remote.url)
    page.press('#github-setup-folder', 'Enter')
    expect(page.locator('#github-setup-status')).to_contain_text('Scryfall artwork (no art folder)', timeout=20000)
    expect(page.locator('#github-setup-warnings')).to_contain_text('not recommended')
    expect(page.locator('[data-mode=scryfall]')).to_have_class('choice selected')
    expect(page.locator('#art-fallback')).to_be_checked()
    expect(page.locator('#fallback-line')).to_be_hidden()
    expect(page.locator('[data-back-action=default]')).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('.symbol-upload img')).to_have_count(4)
    page.click('#save-setup')
    expect(page.locator('#setup-state')).to_have_text('Saved settings · changes stay local')
    s = app.ws.deck(d['id'])['settings']
    assert s['source']['mode'] == 'scryfall' and s['source']['fallback'] is True
    assert s['backDesign']['mode'] == 'default'
    assert not errors, errors


def test_failed_import_preserves_existing_draft_and_allows_retry(browser_app):
    app, server, page, errors = browser_app
    d = app.ws.new_deck('Failure then retry')
    default_symbols = dict(d['settings']['symbols'])
    remote = BundleRemote(art=False, back='custom', single=True)
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
    assert page.locator('.symbol-upload img').count() == 4
    assert app.ws.deck(d['id'])['settings']['symbols'] == default_symbols
    remote.file(missing, raw)
    page.click('#github-setup-button')
    expect(page.locator('#github-setup-status')).to_contain_text('Review below, then save', timeout=20000)
    expect(page.locator('[data-back-action=custom]')).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('#deck-artist')).to_have_value('Unsaved artist')
    assert not errors, errors


def test_import_locks_manual_setup_and_cancel_restores_saved_state(browser_app):
    app, server, page, errors = browser_app
    d = app.ws.new_deck('Cancel bundle')
    default_symbols = dict(d['settings']['symbols'])
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
        assert app.ws.deck(d['id'])['settings']['symbols'] == default_symbols
        assert app.ws.deck(d['id'])['revision'] == d['revision']
        assert not errors, errors
    finally:
        release.set()
