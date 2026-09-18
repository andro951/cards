import hashlib
import io

from PIL import Image

from foundry.domain import RARITIES
from foundry.images import ingest_image, decode_image
from foundry.storage import Store
from foundry.symbols import ASSET_ROOT, BUILTINS
from foundry.workspace import Workspace


EXPECTED_SIZES = {
    'common': (92, 128),
    'uncommon': (92, 128),
    'rare': (93, 128),
    'mythic': (93, 128),
}
EXPECTED_SHA256 = {
    'common': 'edf28920933fae71a7a8a3c404bb3ded697412126b07d9f3a45a56a6a1973f87',
    'uncommon': 'cf2d3bc00d4f280b1819a6b32f6edff8d470717cfb82a740afcc761e1557a40c',
    'rare': 'cc554cbc4e32b3f5b86b578f5b3945f3c2871ee1e333933451e9959cf8e96497',
    'mythic': '7c8fd85c9009a3918679dd09b3b5355d17ef51b486ce929b569de933d869dfeb',
}


def test_bundled_files_are_exact_uploaded_defaults():
    for rarity in RARITIES:
        path=ASSET_ROOT/BUILTINS[rarity]['file']
        raw=path.read_bytes()
        assert hashlib.sha256(raw).hexdigest()==EXPECTED_SHA256[rarity]
        with Image.open(path) as image:
            image.load()
            assert image.format=='WEBP'
            assert image.size==EXPECTED_SIZES[rarity]


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


def test_saved_symbol_override_survives_reopen_without_touching_other_defaults(tmp_path):
    ws=Workspace(Store(tmp_path));defaults=ws.symbols.defaults()
    deck=ws.new_deck('Persist override')
    custom=ingest_image(ws.store,png('#4455aa'))['id']
    saved=ws.save(deck['id'],{'revision':deck['revision'],'settings':{'symbols':{**deck['settings']['symbols'],'uncommon':custom}}})
    reopened=ws.deck(saved['id'])
    assert reopened['settings']['symbols']['uncommon']==custom
    for rarity in ('common','rare','mythic'):
        assert reopened['settings']['symbols'][rarity]==defaults[rarity]
