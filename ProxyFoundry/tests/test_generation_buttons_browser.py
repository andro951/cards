"""Generate controls reflect actual work ownership and outstanding setup uploads."""
import os
import pytest
from playwright.sync_api import expect
from test_browser import browser_app,png

pytestmark=pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1',reason='Actual generation button state')


def test_deck_buttons_follow_blockers_navigation_cancellation_and_preflight(browser_app):
    app,server,page,errors=browser_app
    deck=app.ws.new_deck('Generation availability')
    page.goto(server.origin+'/#deck/'+deck['id'])
    generate=page.locator('#generate-deck');expect(generate).to_be_enabled()
    page.evaluate("""async id=>{
        window.ui=await import('/site/ui.js');
        window.task=ui.work.begin({label:'Import artwork',resources:['deck:'+id]});
    }""",deck['id'])
    expect(generate).to_be_disabled()
    page.locator('[data-tab="setup"]').click()
    expect(page.locator('#save-generate')).to_be_disabled()
    expect(generate).to_be_disabled()
    page.evaluate('task.controller.abort()')
    expect(generate).to_be_disabled()
    page.evaluate('ui.work.finish(task)')
    expect(generate).to_be_enabled();expect(page.locator('#save-generate')).to_be_enabled()
    #Metadata is explicitly awaited by generation; unrelated decks do not conflict.
    page.evaluate("""()=>{
        window.other=ui.work.begin({resources:['deck:other']});
        window.metadata=ui.work.begin({resources:['metadata:'+ui.state.activeDeck.id]});
    }""")
    expect(generate).to_be_enabled()
    page.evaluate("""()=>{ui.work.finish(other);ui.work.finish(metadata);window.restore=ui.work.begin({label:'Restore backup',resources:['workspace']});}""")
    expect(generate).to_be_disabled();expect(page.locator('#save-generate')).to_be_disabled()
    page.evaluate('ui.work.finish(restore)')
    page.evaluate("""async()=>{
        const g=await import('/site/generation-progress.js');window.preflight=new g.GenerationScreen('Example');
        preflight.dialog.close();
    }""")
    expect(generate).to_be_disabled();expect(page.locator('#save-generate')).to_be_disabled()
    page.evaluate('preflight.close()')
    expect(generate).to_be_enabled();expect(page.locator('#save-generate')).to_be_enabled()
    assert not errors,errors


def test_setup_stays_disabled_until_all_symbol_uploads_settle_and_recovers_on_failure(browser_app):
    app,server,page,errors=browser_app
    deck=app.ws.new_deck('Pending symbol uploads')
    page.goto(server.origin+'/#deck/'+deck['id']+'/setup')
    page.locator('#save-generate').wait_for()
    pending=[];page.route('**/api/uploads?kind=symbol',lambda route:pending.append(route))
    def upload(rarity):
        with page.expect_file_chooser() as chooser:page.locator('[data-symbol="'+rarity+'"]').click()
        chooser.value.set_files({'name':rarity+'.png','mimeType':'image/png','buffer':png((60,60))})
        page.wait_for_function('() => document.querySelector("#generate-deck").disabled')
    upload('common');upload('uncommon')
    assert len(pending)==2
    expect(page.locator('#save-generate')).to_be_disabled()
    pending[0].continue_()
    expect(page.locator('[data-symbol="common"]')).to_have_class('symbol-upload has-image')
    expect(page.locator('#save-generate')).to_be_disabled()
    expect(page.locator('#generate-deck')).to_be_disabled()
    pending[1].fulfill(status=500,content_type='application/json',body='{"error":"Upload failed for test"}')
    expect(page.locator('#save-generate')).to_be_enabled()
    expect(page.locator('#generate-deck')).to_be_enabled()
    assert not errors,errors


def test_library_generation_button_tracks_selected_deck_ownership(browser_app):
    app,server,page,errors=browser_app
    first=app.ws.new_deck('First deck');second=app.ws.new_deck('Second deck')
    page.goto(server.origin+'/#decks')
    page.locator('[data-select="'+first['id']+'"]').check()
    expect(page.locator('#render-selected')).to_be_enabled()
    page.evaluate("""async id=>{window.ui=await import('/site/ui.js');window.task=ui.work.begin({label:'Save deck',resources:['deck:'+id]});}""",first['id'])
    expect(page.locator('#render-selected')).to_be_disabled()
    page.locator('[data-select="'+second['id']+'"]').check()
    expect(page.locator('#render-selected')).to_be_disabled()
    page.evaluate('ui.work.finish(task)')
    expect(page.locator('#render-selected')).to_be_enabled()
    assert not errors,errors
