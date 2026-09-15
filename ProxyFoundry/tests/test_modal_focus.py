"""Deterministic component regression for modal autofocus stealing text input.

This test mounts the actual UI helper into a controlled document. Any timers
created while mounting are held until after the user has chosen another field.
The old 20ms autofocus would then change the focused input; the fixed code must not.
"""
import os
from pathlib import Path
import pytest
pytestmark=pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1' and os.environ.get('PF_DOM')!='1',reason='Opt-in Chromium component test')
ROOT=Path(__file__).resolve().parents[1]

def test_modal_does_not_steal_focus_or_type_into_quantity():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        executable=os.environ.get('PF_BROWSER_EXECUTABLE') or (os.environ.get('PF_DOM_EXECUTABLE') or '/usr/bin/chromium' if os.environ.get('PF_DOM')=='1' else None)
        browser=p.chromium.launch(headless=True,**({'executable_path':executable} if executable else {}))
        page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        try:
            page.set_content('<!doctype html><body><button id="launch">Open</button><div id="modal-host"></div><div id="toast-host"></div>')
            text=(ROOT/'site/ui.js').read_text().replace('export ','')
            page.add_script_tag(content=text)
            page.evaluate('''()=>{
              window.heldTimers=[];const nativeTimer=window.setTimeout;
              window.setTimeout=(fn,...args)=>{heldTimers.push(fn);return heldTimers.length};
              modal('Artist editor','<input id="quantity" type="number" value="1"><input id="modification" type="text">');
              window.setTimeout=nativeTimer;
            }''')
            page.locator('#modification').focus()
            page.evaluate('()=>{for(const callback of heldTimers)callback()}')
            page.keyboard.type('Extended by Isaac')
            assert page.input_value('#quantity')=='1'
            assert page.input_value('#modification')=='Extended by Isaac'
            assert page.evaluate('document.activeElement.id')=='modification'
            assert not errors,errors
        finally:browser.close()

