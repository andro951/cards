import copy
import pytest
from foundry.compiler import Compiler,semantic,choose_builtin
from foundry.land_frame import has_retired_land_frame
from foundry.workspace import Workspace
from foundry.domain import ValidationError
from foundry.deck_document import reusable_recipe,recipe_fingerprint
from test_pipeline import workspace
from test_class_and_enchantment_land import valgavoths_lair


@pytest.mark.parametrize('choice',['auto','land','legend-land'])
@pytest.mark.parametrize('legendary',[False,True])
@pytest.mark.parametrize('nickname',['','The Hidden Chamber'])
@pytest.mark.parametrize('types',['Enchantment Land','Artifact Land'])
def test_mixed_type_lands_cannot_bypass_the_current_frame(workspace,choice,legendary,nickname,types):
    store,art,settings=workspace;sf=valgavoths_lair()
    sf['type_line']=('Legendary ' if legendary else '')+types
    comp=Compiler(store).compile_face(sf,sf,0,
        {'templateOverride':choice,'semanticOverrides':{'nickname':nickname}},settings,art)
    assert comp['recipe']=='land_full_legendary'
    assert not has_retired_land_frame(comp['data'])
    assert types in comp['data']['text']['type']['text']
    assert any('/proxy-foundry/' in f.get('src','') for f in comp['data']['frames'])


@pytest.mark.parametrize('kind',['land','legend-land'])
def test_land_editor_seeds_use_the_current_family(workspace,kind):
    data=Workspace(workspace[0]).template_seed(kind)
    assert not has_retired_land_frame(data)
    assert any('/proxy-foundry/' in f.get('src','') for f in data['frames'])


def test_old_saved_builtin_id_redirects_before_native_recipe_selection():
    sf=valgavoths_lair();sem=semantic(sf,sf)
    assert choose_builtin(sem,'land')['layout']=='land_full_legendary'


def test_custom_helper_cannot_reuse_the_retired_land_donor(workspace):
    store,art,settings=workspace
    sf={'name':'Helper Reference','layout':'normal','type_line':'Card','colors':[],
        'oracle_text':'Keep this card beside the battlefield.','rarity':'common'}
    comp=Compiler(store).compile_face(sf,sf,0,{},settings,art,art_origin='GitHub folder')
    assert comp['recipe']=='helper_full_art'
    assert not has_retired_land_frame(comp['data'])


def test_cached_and_imported_retired_frames_rebuild_only_the_affected_card(workspace,monkeypatch):
    store,art,settings=workspace;ws=Workspace(store);deck=ws.new_deck('Retired land migration')
    deck['settings']=ws.validate_settings(settings);deck['cards']=[]
    for name in ["Valgavoth's Lair",'Unchanged Land']:
        sf=valgavoths_lair();sf.pop('id',None);sf['name']=name
        entry=ws.sources.entry(sf);entry['faces'][0]['artOverride']=art;deck['cards'].append(entry)
    store.put('decks',deck,deck['revision']);prepared=ws.prepare(deck['id'])
    untouched=prepared['cards'][1]['faces'][0]['compiled']['renderKey']
    prepared['cards'][0]['faces'][0]['compiled']['data']['frames'].insert(0,
        {'name':'Temple Title Bar','src':'/img/black.png','masks':[]})
    prepared['recipeSnapshot']={'renderer':{},'fingerprint':recipe_fingerprint(prepared)}
    assert not reusable_recipe(prepared)
    store.put('decks',prepared,prepared['revision'])
    assert ws.deck(deck['id'])['status']=='draft'
    with pytest.raises(ValidationError,match='prepare changes before rendering'):
        ws.render_targets([deck['id']])
    with pytest.raises(ValidationError,match='prepare changes before rendering'):
        ws.render_targets_for_card(deck['id'],prepared['cards'][0]['id'])
    compile=ws.compiler.compile_face;calls=[]
    def tracked(sf,*args,**kwargs):calls.append(sf['name']);return compile(sf,*args,**kwargs)
    monkeypatch.setattr(ws.compiler,'compile_face',tracked)
    fixed=ws.prepare(deck['id'])
    assert calls==["Valgavoth's Lair"]
    assert not any(has_retired_land_frame(f['compiled']['data']) for c in fixed['cards'] for f in c['faces'])
    assert fixed['cards'][1]['faces'][0]['compiled']['renderKey']==untouched


def test_legacy_raw_templates_cannot_emit_the_retired_frame(workspace):
    store,art,settings=workspace;sf=valgavoths_lair();compiler=Compiler(store)
    data=compiler.compile_face(sf,sf,0,{},settings,art)['data']
    data=copy.deepcopy(data);data['frames'].append({'name':'Temple Type Bar','src':'/img/black.png','masks':[]})
    with pytest.raises(ValidationError,match='retired rounded land frame'):
        compiler.compile_face(sf,sf,0,{'rawCard':data},settings,art)
