import io

from PIL import Image

from foundry.domain import RARITIES
from foundry.images import ingest_image, decode_image
from foundry.storage import Store
from foundry.workspace import Workspace


EXPECTED_SIZES = {
    'common': (92, 128),
    'uncommon': (92, 128),
    'rare': (93, 128),
    'mythic': (93, 128),
}


def png(color='#556677'):
    out=io.BytesIO();Image.new('RGBA',(80,80),color).save(out,'PNG');return out.getvalue()


def test_new_deck_uses_bundled_symbols_without_user_action(tmp_path):
    ws=Workspace(Store(tmp_path))
    defaults=ws.symbols.defaults()
    deck=ws.new_deck('Defaults')
    assert deck['settings']['symbols']==defaults
    assert set(defaults)==set(RARITIES)
    assert len(set(defaults.values()))==4
    for rarity,ident in defaults.items():
        asset=ws.store.asset(ident)
        assert asset and asset['mime']=='image/png'
        assert decode_image(ws.store.asset_path(ident).read_bytes()).size==EXPECTED_SIZES[rarity]


def test_one_explicit_rarity_override_keeps_other_builtins(tmp_path):
    ws=Workspace(Store(tmp_path));defaults=ws.symbols.defaults()
    custom=ingest_image(ws.store,png('#aa3300'))['id']
    settings=ws.validate_settings({'symbols':{'rare':custom}})
    assert settings['symbols']['rare']==custom
    for rarity in ('common','uncommon','mythic'):
        assert settings['symbols'][rarity]==defaults[rarity]


def test_existing_complete_symbol_set_is_not_silently_replaced(tmp_path):
    ws=Workspace(Store(tmp_path));custom={}
    for i,rarity in enumerate(RARITIES):
        custom[rarity]=ingest_image(ws.store,png((30+i*40,80,120,255)))['id']
    first=ws.validate_settings({'symbols':custom})
    second=ws.validate_settings(first)
    assert first['symbols']==custom
    assert second['symbols']==custom


def test_legacy_deck_with_no_symbols_reads_with_defaults_then_persists_on_save(tmp_path):
    ws=Workspace(Store(tmp_path))
    old=ws.store.put('decks',{'name':'Legacy','cards':[],'settings':{},'status':'draft','notes':'','importedSource':''})
    opened=ws.deck(old['id'])
    assert opened['settings']['symbols']==ws.symbols.defaults()
    saved=ws.save(old['id'],{'revision':old['revision'],'settings':opened['settings']})
    assert saved['settings']['symbols']==ws.symbols.defaults()
