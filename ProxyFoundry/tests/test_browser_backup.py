import pytest

from foundry.backup import Backups
from foundry.domain import ConflictError
from foundry.storage import Store
from foundry.workspace import Workspace


def test_selective_backup_import_replaces_only_confirmed_objects(tmp_path):
    source=Workspace(Store(tmp_path/'source'))
    chosen=source.new_deck('Chosen deck')
    untouched=source.new_deck('Untouched deck')
    style=source.save_style_preset(chosen['id'],'Warm orange')
    backups=Backups(source)
    exported=backups.export(include_renders=False)
    path=source.store.home/'backups'/exported['filename']
    catalog=backups.catalog(path)
    assert catalog['includesRenders'] is False
    assert {item['name'] for item in catalog['objects']['style-presets']}=={'Warm orange'}

    changed=source.store.put('decks',{**chosen,'name':'Changed deck'},chosen['revision'])
    selected={'decks':[chosen['id']],'style-presets':[],'templates':[]}
    with pytest.raises(ConflictError):backups.import_selected(path,selected)
    assert source.deck(chosen['id'])['name']=='Changed deck'

    result=backups.import_selected(path,selected,replace=[chosen['id']])
    assert result=={'decks':1,'templates':0,'style-presets':0}
    assert source.deck(chosen['id'])['name']=='Chosen deck'
    assert source.deck(untouched['id'])['name']=='Untouched deck'


def test_style_presets_are_portable_with_bundled_assets(tmp_path):
    source=Workspace(Store(tmp_path/'source'))
    deck=source.new_deck('Styled')
    preset=source.save_style_preset(deck['id'],'My style')
    target=Workspace(Store(tmp_path/'target'))
    package=Backups(source).export(include_renders=False)
    path=source.store.home/'backups'/package['filename']
    result=Backups(target).import_selected(path,{'decks':[],'templates':[],'style-presets':[preset['id']]})
    assert result['style-presets']==1
    target.set_global_settings({'defaultStylePresetId':preset['id']})
    imported=target.new_deck('New deck')
    assert imported['settings']['symbols']==preset['settings']['symbols']



def test_backup_restoration_checks_dynamic_template_variants_before_mutating(tmp_path):
    import json,zipfile
    from foundry.domain import ValidationError
    from foundry.template_model import convert_cardconjurer
    source=Workspace(Store(tmp_path/'source'))
    template=source.save_template(convert_cardconjurer(source.template_seed('normal'),'Safe','standard'))
    exported=Backups(source).export(include_renders=False);path=source.store.home/'backups'/exported['filename']
    with zipfile.ZipFile(path) as archive:
        files={name:archive.read(name) for name in archive.namelist()}
    manifest=json.loads(files['workspace.json']);manifest['documents']['templates'][0]['variants']=[{'when':{},'frames':[{'src':'javascript:bad'}]}]
    files['workspace.json']=json.dumps(manifest).encode();corrupt=tmp_path/'bad.zip'
    with zipfile.ZipFile(corrupt,'w') as archive:
        for name,raw in files.items():archive.writestr(name,raw)
    target=Workspace(Store(tmp_path/'target'));backups=Backups(target)
    with pytest.raises(ValidationError):backups.import_selected(corrupt,{'templates':[template['id']]})
    assert not target.store.list('templates')
