"""Isolated browser regressions for the separate template editor."""
import importlib.util
import json
from pathlib import Path
import threading
import urllib.request

from PIL import Image, ImageDraw
import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('template_editor_server', ROOT / 'server.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


@pytest.fixture(scope='module')
def origin():
    server = host.create_server(0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown()
    server.server_close()


@pytest.fixture
def page(origin):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1500, 'height': 1050}, accept_downloads=True)
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(origin+'/classic')
        page.locator('canvas[data-ready]').wait_for(timeout=90000)
        yield page
        assert not errors
        browser.close()


def choose(page, part):
    page.locator(f'button[data-part="{part}"]').click()


def upload(page, button, path):
    with page.expect_file_chooser() as chooser:
        page.get_by_role('button', name=button, exact=True).click()
    chooser.value.set_files(str(path))


def ready(page, timeout=120000):
    page.wait_for_function('() => document.querySelector("canvas[data-ready]")?.dataset.ready === String(TemplateEditor.epoch)', timeout=timeout)


def test_native_preview_text_collision_and_history(page):
    assert 'Preview ready' in page.get_by_role('status').inner_text()
    choose(page, 'TitleText')
    page.get_by_label('Anchor x', exact=True).fill('0.12')
    page.get_by_label('Anchor x', exact=True).press('Tab')
    page.wait_for_function('() => TemplateEditor.model.anchors.Title.rect.x === .12')
    page.get_by_role('button', name='Undo', exact=True).click()
    page.wait_for_function('() => TemplateEditor.model.anchors.Title.rect.x === .0767')
    page.get_by_role('button', name='Redo', exact=True).click()
    page.wait_for_function('() => TemplateEditor.model.anchors.Title.rect.x === .12')
    page.get_by_label('Real name', exact=True).fill('An Extremely Long Title That Must Fit Beside Mana')
    page.wait_for_function('() => TemplateEditor.model.preview.name.startsWith("An Extremely")')
    ready(page)
    snapshot = page.evaluate('''() => {
        const e = TemplateEditor, title = e.lastPositions.get('TitleText'), mana = e.lastPositions.get('ManaCost');
        return {titleRight:title.x+title.width,manaLeft:mana.x};
    }''')
    assert snapshot['titleRight'] < snapshot['manaLeft']


def test_tiny_pt_on_full_card_canvas_is_cropped_and_fitted(page, tmp_path):
    image = Image.new('RGBA', (100, 140))
    image.putpixel((0, 0), (255, 0, 0, 1))
    ImageDraw.Draw(image).rectangle((30, 70, 69, 73), fill=(255, 0, 200, 255))
    source = tmp_path / 'tiny-pt.png'
    image.save(source)
    choose(page, 'PT_Box')
    upload(page, 'Upload standalone piece (all colors)', source)
    page.wait_for_function('() => TemplateEditor.model.parts.find(p=>p.id==="PT_Box").asset !== null')
    result = page.evaluate('''async () => {
        const e = TemplateEditor, model = structuredClone(e.model);
        model.parts.forEach(p=>p.visible = p.id === 'PT_Box'); model.preview.pt='2/3';
        const canvas = e.renderer.makeCanvas(); await e.renderer.render(model, canvas);
        const pixels=canvas.getContext('2d').getImageData(0,0,1000,1400).data;
        let l=1000,r=-1,t=1400,b=-1;
        for(let y=0;y<1400;y++) for(let x=0;x<1000;x++) {
            const i=(y*1000+x)*4;
            if(pixels[i]>20&&pixels[i+1]<10&&pixels[i+2]>10){l=Math.min(l,x);r=Math.max(r,x);t=Math.min(t,y);b=Math.max(b,y);}
        }
        const part=model.parts.find(p=>p.id==='PT_Box');
        return {width:r-l+1,height:b-t+1,scale:part.scale,mask:part.mask,alignment:part.alignment,metadata:Object.values(model.assetMetadata)[0]};
    }''')
    assert 186 <= result['width'] <= 189
    assert 17 <= result['height'] <= 20
    assert result['scale'] == 1 and result['mask'] is None and result['alignment'] == 'piece'
    assert result['metadata']['alphaBounds'] == {'x': 30, 'y': 70, 'width': 40, 'height': 4}
    assert result['metadata']['width'] == 100


def test_standalone_rules_and_masked_frame_can_both_be_used(page, tmp_path):
    image = Image.new('RGBA', (500, 700))
    ImageDraw.Draw(image).rectangle((20, 400, 479, 599), fill=(220, 190, 160, 220))
    path = tmp_path / 'rules.png'; image.save(path)
    choose(page, 'Rules')
    upload(page, 'Upload standalone piece (all colors)', path)
    page.wait_for_function('() => TemplateEditor.model.parts.find(p=>p.id==="Rules").alignment === "piece"')
    part = page.evaluate('() => TemplateEditor.model.parts.find(p=>p.id==="Rules")')
    assert part['mask'] is None and part['placement']['relativeTo'] == 'Rules'
    page.get_by_label('Existing image set', exact=True).select_option('FrameImages')
    page.wait_for_function('() => TemplateEditor.model.parts.find(p=>p.id==="Rules").alignment === "full-card"')
    part = page.evaluate('() => TemplateEditor.model.parts.find(p=>p.id==="Rules")')
    assert part['mask'] == 'Mask_Rules' and part['placement']['relativeTo'] == 'Canvas'


def test_json_download_round_trip_png_size_and_autosave(page, tmp_path):
    page.get_by_label('Nickname', exact=True).fill('A Saved Nickname')
    page.wait_for_function('() => TemplateEditor.model.preview.nickname === "A Saved Nickname"')
    ready(page)
    with page.expect_download() as pending:
        page.get_by_role('button', name='Download template JSON', exact=True).click()
    download = pending.value; path = tmp_path / 'template.json'; download.save_as(path)
    saved = json.loads(path.read_text())
    assert saved['canvas'] == 'card-5x7' and saved['preview']['nickname'] == 'A Saved Nickname'
    page.get_by_role('button', name='Reset to M15', exact=True).click()
    page.wait_for_function('() => TemplateEditor.model.preview.nickname === ""')
    upload(page, 'Import template JSON', path)
    page.wait_for_function('() => TemplateEditor.model.preview.nickname === "A Saved Nickname"')
    with page.expect_download() as pending:
        page.get_by_role('button', name='Download preview PNG', exact=True).click()
    output = tmp_path / 'preview.png'; pending.value.save_as(output)
    assert Image.open(output).size == (2000, 2800)
    page.get_by_text('Prototype draft saved in this browser', exact=True).wait_for(timeout=10000)
    page.reload(); page.locator('canvas[data-ready]').wait_for(timeout=30000)
    assert page.get_by_label('Nickname', exact=True).input_value() == 'A Saved Nickname'


def test_all_native_variants_and_dual_crown(page):
    for code in 'WUBRGMALCV':
        page.get_by_label('Preview color / image variant', exact=True).select_option(code)
        page.wait_for_function('(code) => TemplateEditor.model.preview.variant === code', arg=code)
        ready(page)
    page.get_by_label('Preview color / image variant', exact=True).select_option('M')
    page.get_by_label('Second accent color', exact=True).select_option('R')
    page.get_by_label('Legendary', exact=True).check()
    ready(page)
    assert page.evaluate('() => TemplateEditor.model.preview.accentColors') == ['U', 'R']


def test_bad_json_is_rejected_without_losing_current_template(page, tmp_path):
    path = tmp_path / 'bad.json'; path.write_text('{"format":"other"}')
    with page.expect_file_chooser() as pending:
        page.get_by_role('button', name='Import template JSON', exact=True).click()
    pending.value.set_files(str(path))
    page.get_by_role('status').filter(has_text='Choose a version 2').wait_for()
    assert page.evaluate('() => TemplateEditor.model.name') == 'Normal M15'


def test_uploaded_variant_does_not_replace_other_frame_parts(page, tmp_path):
    path = tmp_path / 'sheet.png'
    Image.new('RGBA', (100, 140), (80, 120, 200, 255)).save(path)
    choose(page, 'Title')
    upload(page, 'Replace U variant image', path)
    page.wait_for_function('() => TemplateEditor.model.parts.find(p=>p.id==="Title").map !== "FrameImages"')
    maps = page.evaluate('''() => {
        const m=TemplateEditor.model, title=m.parts.find(p=>p.id==='Title'), type=m.parts.find(p=>p.id==='Type');
        return { title:m.maps[title.map].U, type:m.maps[type.map].U, red:m.maps[title.map].R };
    }''')
    assert maps['title'].startswith('upload_')
    assert maps['type'] == 'FrameImages_U' and maps['red'] == 'FrameImages_R'


def test_svg_upload_and_mask_cutout_preserves_artwork(page, tmp_path):
    path = tmp_path / 'box.svg'
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="140"><rect x="20" y="70" width="60" height="20" fill="red"/></svg>')
    choose(page, 'PT_Box')
    upload(page, 'Upload standalone piece (all colors)', path)
    page.wait_for_function('() => TemplateEditor.model.parts.find(p=>p.id==="PT_Box").asset !== null')
    pixels = page.evaluate('''async () => {
        const e=TemplateEditor, m=structuredClone(e.model);
        m.parts.forEach(p=>p.visible=false);
        const art=m.parts.find(p=>p.kind==='artwork'); art.visible=true; art.placement.relativeTo='Canvas';
        const fill=m.parts.find(p=>p.id==='Crown_BorderCover');fill.visible=true;fill.when='always';fill.placement={relativeTo:'Canvas',rect:{x:0,y:0,width:1,height:1}};fill.color='#00ff00';
        const cut=m.parts.find(p=>p.id==='Crown_Cutout');cut.visible=true;cut.when='always';cut.mask='Mask_Rules';
        const c=e.renderer.makeCanvas();await e.renderer.render(m,c);
        return {cut:Array.from(c.getContext('2d').getImageData(500,1000,1,1).data),outside:Array.from(c.getContext('2d').getImageData(500,500,1,1).data)};
    }''')
    assert pixels['outside'] == [0, 255, 0, 255]
    assert pixels['cut'][3] == 255 and pixels['cut'][1] < 200


def test_portable_export_prunes_unused_maps_and_embeds_native_mask(page, tmp_path):
    page.evaluate('''() => {
        const m=TemplateEditor.model;
        m.parts=m.parts.filter(p=>p.kind==='artwork'||p.id==='Rules');
        const p=m.parts.find(p=>p.id==='Rules');p.map='PortableTest';p.mask=null;
        m.maps.PortableTest={C:'Mask_Rules'};
    }''')
    page.get_by_label('Embed all template images in downloaded JSON (larger file)', exact=True).check()
    with page.expect_download() as pending:
        page.get_by_role('button', name='Download template JSON', exact=True).click()
    output = tmp_path / 'portable.json'; pending.value.save_as(output)
    model = json.loads(output.read_text())
    assert list(model['maps']) == ['PortableTest']
    assert model['assets']['Mask_Rules'].startswith('data:image/png;base64,')
    assert list(model['assets']) == ['Mask_Rules']


def test_dragging_selected_text_region_and_undo(page):
    choose(page, 'TitleText'); ready(page)
    old = page.evaluate('() => TemplateEditor.model.parts.find(p=>p.id==="TitleText").placement.rect.x')
    target = page.evaluate('''() => {
        const e=TemplateEditor,b=e.canvas.getBoundingClientRect(),r=e.lastPositions.get('TitleText');
        return {x:b.x+(r.x+30)*b.width/1000,y:b.y+(r.y+20)*b.height/1400};
    }''')
    page.mouse.move(target['x'], target['y']); page.mouse.down()
    page.mouse.move(target['x'] + 25, target['y'] + 5, steps=4); page.mouse.up(); ready(page)
    new = page.evaluate('() => TemplateEditor.model.parts.find(p=>p.id==="TitleText").placement.rect.x')
    assert new > old
    page.get_by_role('button', name='Undo', exact=True).click()
    page.wait_for_function('(old) => TemplateEditor.model.parts.find(p=>p.id==="TitleText").placement.rect.x === old', arg=old)


def test_cached_composite_invalidates_and_png_uses_full_resolution(page):
    result = page.evaluate('''async () => {
        const e=TemplateEditor,m=structuredClone(e.model);
        m.parts=m.parts.filter(p=>p.kind==='artwork'||p.kind==='fill');
        m.parts.find(p=>p.kind==='artwork').visible=false;
        const fill=m.parts.find(p=>p.kind==='fill');fill.when='always';fill.visible=true;fill.color='#ff0000';fill.placement={relativeTo:'Canvas',rect:{x:0,y:0,width:1,height:1}};
        const small=e.renderer.makeCanvas(); await e.renderer.render(m,small);
        const red=Array.from(small.getContext('2d').getImageData(500,500,1,1).data);
        fill.color='#00ff00'; await e.renderer.render(m,small);
        const green=Array.from(small.getContext('2d').getImageData(500,500,1,1).data);
        const large=e.renderer.makeCanvas(2000,2800); await e.renderer.render(m,large);
        return {red,green,large:Array.from(large.getContext('2d').getImageData(1500,2000,1,1).data),compositeWidth:e.renderer.frameCache.width};
    }''')
    assert result['red'] == [255, 0, 0, 255]
    assert result['green'] == result['large'] == [0, 255, 0, 255]
    assert result['compositeWidth'] == 2000


def test_host_only_serves_prototype_files_and_rejects_traversal(origin):
    with urllib.request.urlopen(origin + '/') as response:
        assert b'studio.js' in response.read()
    from urllib.error import HTTPError
    for path in ['/server.py', '/%2e%2e/foundry/server.py', '/img/../server.py']:
        with pytest.raises(HTTPError):
            urllib.request.urlopen(origin + path)