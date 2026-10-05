"""Creator workflows and real production import for Template Studio."""
import json
import time
from pathlib import Path
import pytest
from PIL import Image,ImageDraw
from playwright.sync_api import sync_playwright
from test_editor import origin,upload

ROOT=Path(__file__).resolve().parents[3]


@pytest.fixture
def page(origin):
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1500,'height':1050},accept_downloads=True)
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(origin)
        page.locator('canvas[data-ready]').wait_for(timeout=120000)
        yield page
        assert not errors
        browser.close()


def ready(page):
    page.wait_for_function('() => document.querySelector("canvas[data-ready]")?.dataset.ready === String(TemplateEditor.epoch)',timeout=120000)


def test_frame_controls_preserve_text_and_real_name_bar_is_independent(page):
    before=page.evaluate('({...TemplateEditor.model.preview})')
    page.get_by_role('button',name='Legendary · two colors',exact=True).click()
    ready(page)
    after=page.evaluate('({...TemplateEditor.model.preview})')
    assert after['variant']=='M' and after['accentColors']==['U','R'] and after['legendary']
    for field in ['name','nickname','type','mana','rules','flavor','pt']:
        assert after[field]==before[field]
    toggle=page.get_by_role('button',name='Real-name bar',exact=True)
    assert toggle.get_attribute('aria-pressed')=='false'
    toggle.click()
    ready(page)
    assert toggle.get_attribute('aria-pressed')=='true'
    nickname=page.evaluate('TemplateEditor.model.preview.nickname')
    page.get_by_role('button',name='Green',exact=True).click()
    ready(page)
    assert page.evaluate('TemplateEditor.model.preview.nickname')==nickname
    assert page.evaluate('TemplateEditor.model.preview.rules')==before['rules']
    toggle.click()
    ready(page)
    assert toggle.get_attribute('aria-pressed')=='false'
    assert page.evaluate('TemplateEditor.model.preview.variant')=='G'


def test_native_guided_workflow_and_review(page):
    page.get_by_role('button',name='Start from CardConjurer M15',exact=True).click()
    page.get_by_role('button',name='Title bar',exact=True).click()
    page.get_by_label('Left (%)',exact=True).fill('12')
    page.get_by_label('Left (%)',exact=True).press('Tab')
    page.wait_for_function('() => TemplateEditor.model.anchors.Title.rect.x === .12')
    assert page.evaluate('TemplateEditor.model.parts.find(p=>p.id === "TitleText").placement.relativeTo')=='Title'
    page.get_by_role('button',name='Undo',exact=True).click()
    ready(page)
    assert page.evaluate('TemplateEditor.model.anchors.Title.rect.x')==.0767
    page.get_by_role('button',name='5 Review',exact=True).click()
    page.get_by_role('button',name='Check representative cards',exact=True).click()
    page.wait_for_function('() => document.body.textContent.includes("Ready to export.")',timeout=120000)
    assert page.get_by_role('button',name='Download importable template').is_enabled()
    assert page.locator('figure').count()==25
    output=ROOT/'test-results';output.mkdir(exist_ok=True)
    page.screenshot(path=str(output/'studio-review.png'),full_page=True)


def test_recolor_custom_sheet_preserves_transparency(page,tmp_path):
    path=tmp_path/'neutral.png'
    image=Image.new('RGBA',(500,700),(0,0,0,0))
    draw=ImageDraw.Draw(image);draw.rectangle((0,0,499,699),outline=(220,220,220,255),width=24)
    draw.rectangle((40,36,459,75),fill=(220,220,220,255))
    image.save(path)
    page.get_by_label('Split sheet with existing M15 masks').uncheck()
    page.get_by_label('Image colors').select_option('recolor')
    upload(page,'Upload frame sheet',path)
    page.wait_for_function('() => TemplateEditor.model.parts.find(p=>p.id === "Frame").colorSource != null')
    ready(page)
    assert page.evaluate('TemplateEditor.model.parts.filter(p=>["Border","Rules","Title","Type","Pinline"].includes(p.id)).every(p=>!p.visible)')
    pixels=page.evaluate('''async () => {
        const part=TemplateEditor.model.parts.find(p=>p.id === "Frame"),image=await TemplateEditor.renderer.loadImage(TemplateEditor.renderer.sourceFor(TemplateEditor.model,part,"R"));
        const c=document.createElement("canvas");c.width=image.width;c.height=image.height;const x=c.getContext("2d");x.drawImage(image,0,0);
        return [Array.from(x.getImageData(5,5,1,1).data),Array.from(x.getImageData(250,350,1,1).data)];
    }''')
    assert pixels[0][0]>pixels[0][1]*2
    assert pixels[1][3]==0
    #A complete-sheet export omits unused native masks; reopening restores the mask bank.
    portable=page.evaluate('async () => (await import("/exporter.js")).Exporter.Portable(TemplateEditor.model)')
    saved=tmp_path/'editable.json';saved.write_text(json.dumps(portable),encoding='utf-8')
    upload(page,'Open template',saved)
    ready(page)
    assert page.evaluate('Object.keys(TemplateEditor.model.assets).includes("Mask_Title")')
    page.get_by_role('button',name='1 Start',exact=True).click()
    page.get_by_label('Split sheet with existing M15 masks').check()
    page.get_by_label('Image colors').select_option('same')
    upload(page,'Upload frame sheet',path)
    page.wait_for_function('() => TemplateEditor.model.parts.find(p=>p.id === "Title").mask === "Mask_Title"')
    ready(page)
    assert page.evaluate('TemplateEditor.model.parts.find(p=>p.id === "Title").mask')=='Mask_Title'


def test_per_color_missing_coverage_blocks_export_and_fallback(page,tmp_path):
    path=tmp_path/'pt_blue.png';Image.new('RGBA',(120,60),'#5c9bce').save(path)
    page.get_by_role('button',name='2 Parts',exact=True).click()
    page.locator('button[data-part="PT_Box"]').click()
    page.get_by_label('Image colors').select_option('individual')
    page.get_by_label('Assign to color').select_option('U')
    upload(page,'Upload replacement image',path)
    page.wait_for_function('() => TemplateEditor.model.parts.find(p=>p.id === "PT_Box").colorAssignments?.assigned.includes("U")')
    page.get_by_role('button',name='5 Review',exact=True).click()
    assert page.get_by_role('button',name='Check representative cards').is_disabled()
    assert 'PT box: assign White' in page.locator('body').inner_text()
    page.get_by_role('button',name='2 Parts',exact=True).click()
    page.get_by_label('Use a shared image for unassigned colors').check()
    page.get_by_role('button',name='5 Review',exact=True).click()
    assert page.get_by_role('button',name='Check representative cards').is_enabled()


def test_export_imports_in_real_workspace_and_binds_cards(page,tmp_path):
    #Use the actual image exporter, importer and compiler, without touching user decks.
    page.get_by_role('button',name='5 Review',exact=True).click()
    page.get_by_role('button',name='Check representative cards').click()
    page.wait_for_function('() => document.body.textContent.includes("Ready to export.")',timeout=120000)
    page.get_by_role('button',name='Inspect Ordinary',exact=True).click()
    assert page.get_by_role('button',name='Download importable template').is_enabled()
    started=time.monotonic()
    with page.expect_download(timeout=120000) as event:
        page.get_by_role('button',name='Download importable template').click()
    exported=tmp_path/'export.json';event.value.save_as(str(exported))
    model=json.loads(exported.read_text(encoding='utf-8'))
    report=ROOT/'test-results/studio-export.json'
    report.write_text(json.dumps({'seconds':time.monotonic()-started,'bytes':exported.stat().st_size}),encoding='utf-8')
    upload(page,'Open template',exported)
    page.wait_for_function('() => TemplateStudio.step === 1')
    ready(page)
    assert page.evaluate('TemplateEditor.model.parts.find(p=>p.id === "TitleText").field')=='displayName'
    from foundry.workspace import Workspace
    from foundry.storage import Store
    from foundry.compiler import custom_data
    workspace=Workspace(Store(tmp_path/'workspace'))
    imported=workspace.import_template_file(model)
    assert imported['legendary']
    sem={'name':'Aria','nickname':'Stormcaller','colors':['U','R'],'types':['Creature'],'subtypes':['Wizard'],'supertypes':['Legendary'],'legendary':True,'mana_cost':'{3}{U}{R}','power':'4','toughness':'4','oracle_text':'Flying','flavor_text':'Test flavor.'}
    data=custom_data(imported,sem)
    assert data['text']['title']['text']=='Stormcaller'
    assert data['text']['subtitle']['text']=='Aria'
    assert data['text']['pt']['text']=='4/4'
    assert '{flavor}' in data['text']['rules']['text']
    assert data['frames'][0]['name']=='PT box'
    assert all(frame['src'].startswith('/api/assets/') for frame in data['frames'])
    assert len(json.dumps(data))<30000
    plain=custom_data(imported,{**sem,'nickname':'','legendary':False,'power':None,'toughness':None})
    assert not any(frame['name'] in {'Legendary crown','Real-name bar','PT box'} for frame in plain['frames'])
    assert plain['text']['subtitle']['text']==''
    portable=tmp_path/'app-export.json'
    portable.write_text(json.dumps(workspace.export_template_file(imported['id'])),encoding='utf-8')
    upload(page,'Open template',portable)
    ready(page)
    assert page.evaluate('Object.entries(TemplateEditor.model.assets).every(([id,src])=>id.startsWith("Mask_") || src.startsWith("data:"))')
    artifact=ROOT/'test-results';artifact.mkdir(exist_ok=True)
    (artifact/'studio-importable.json').write_text(json.dumps(model),encoding='utf-8')
    (artifact/'studio-compiled.json').write_text(json.dumps(data),encoding='utf-8')


def test_small_screen_and_warm_typing_stays_responsive(page):
    page.set_viewport_size({'width':760,'height':900})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    elapsed=page.evaluate('''async () => {
        const times=[];
        for(let i=0;i<5;i++) {
            const start=performance.now();TemplateEditor.model.preview.name="Typing "+i;
            await TemplateEditor.renderer.render(TemplateEditor.model,TemplateEditor.canvas);
            times.push(performance.now()-start);
        }
        return times;
    }''')
    assert max(elapsed)<1000,elapsed
    output=ROOT/'test-results';output.mkdir(exist_ok=True)
    (output/'studio-performance.json').write_text(json.dumps({'warmPreviewMilliseconds':elapsed,'viewport':[760,900]}),encoding='utf-8')
    page.screenshot(path=str(output/'studio-small-screen.png'),full_page=True)


def test_batch_color_upload_confirms_filename_suggestions(page,tmp_path):
    paths=[]
    for color,name in [('#527abc','pt_blue.png'),('#ac493b','pt_red.png')]:
        path=tmp_path/name;Image.new('RGBA',(120,60),color).save(path);paths.append(str(path))
    page.get_by_role('button',name='2 Parts',exact=True).click()
    page.locator('button[data-part="PT_Box"]').click()
    page.get_by_label('Image colors').select_option('individual')
    with page.expect_file_chooser() as chooser:
        page.get_by_role('button',name='Upload several color images',exact=True).click()
    chooser.value.set_files(paths)
    assert page.get_by_label('pt_blue.png',exact=True).input_value()=='U'
    assert page.get_by_label('pt_red.png',exact=True).input_value()=='R'
    page.get_by_role('button',name='Apply color images',exact=True).click()
    page.wait_for_function('() => TemplateEditor.model.parts.find(p=>p.id === "PT_Box").colorAssignments?.assigned.length === 2')
    ready(page)
    assert page.evaluate('TemplateEditor.model.parts.find(p=>p.id === "PT_Box").colorAssignments.assigned')==['U','R']
    page.get_by_role('button',name='Undo',exact=True).click()
    assert page.evaluate('TemplateEditor.model.parts.find(p=>p.id === "PT_Box").colorAssignments') is None


def test_new_start_wins_over_an_older_slow_open(page,tmp_path):
    seed=json.loads((Path(__file__).resolve().parents[1]/'default-template.json').read_text(encoding='utf-8'))
    saved={**seed,'name':'Older import'}
    path=tmp_path/'older.json';path.write_text(json.dumps(saved),encoding='utf-8')
    held=[]
    def route(request):
        if not held:held.append(request)
        else:request.continue_()
    page.route('**/default-template.json',route)
    upload(page,'Open template',path)
    page.wait_for_timeout(100)
    assert held
    page.get_by_role('button',name='Start from CardConjurer M15',exact=True).click()
    page.wait_for_function('() => TemplateStudio.step === 1')
    held[0].fulfill(json=seed)
    page.wait_for_function('() => TemplateEditor.model.name === "Normal M15"')
    ready(page)
    assert page.evaluate('TemplateEditor.model.name')=='Normal M15'