import io
from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import Image

from foundry import classic_token_frame
from foundry.compiler import Compiler, semantic
from foundry.network import Network
from foundry.runtime import Runtime
from foundry.storage import Store
from foundry.workspace import Workspace
from test_pipeline import workspace


def source_png():
    image = Image.new('RGBA', (5, 1))
    image.putdata([(240, 220, 160, 255), (120, 130, 140, 127), (0, 0, 0, 255),
                   (255, 255, 255, 0), (64, 64, 64, 200)])
    output = io.BytesIO()
    image.save(output, 'PNG')
    return output.getvalue()


def test_desaturation_retains_geometry_alpha_black_and_neutral_shading():
    source = Image.open(io.BytesIO(source_png())).convert('RGBA')
    raw = classic_token_frame.desaturate_white_png(source_png())
    result = Image.open(io.BytesIO(raw)).convert('RGBA')
    assert result.size == source.size
    assert result.getchannel('A').tobytes() == source.getchannel('A').tobytes()
    assert result.getchannel('R').tobytes() == source.convert('L').tobytes()
    assert result.getchannel('R').tobytes() == result.getchannel('G').tobytes() == result.getchannel('B').tobytes()
    assert result.getpixel((2, 0)) == (0, 0, 0, 255)
    assert result.getpixel((4, 0)) == (64, 64, 64, 200)
    assert classic_token_frame.desaturate_white_png(source_png()) == raw


@pytest.mark.parametrize('family', ['regular', 'textless'])
def test_runtime_generates_once_then_reuses_persisted_cache_without_reading_source(tmp_path, family):
    calls = []
    def transport(url):
        calls.append(url)
        assert any(url.endswith(f'/img/frames/token/m15/{family}/{code}.png') for code in ('w', 'a'))
        return source_png(), 'image/png', {}
    store = Store(tmp_path)
    runtime = Runtime(Network(store, transport=transport))
    path = classic_token_frame.PREFIX + family + '-c.png'
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: runtime.fetch(path), range(6)))
    assert len(calls) == 1
    assert all(result == (classic_token_frame.desaturate_white_png(source_png()), 'image/png') for result in results)
    assert runtime.cached(path)
    def fail(*args, **kwargs):
        raise AssertionError('Cached material must not reload its source')
    restarted = Runtime(Network(store, transport=fail))
    restarted.ensure(path)
    assert restarted.fetch(path) == results[0]
    assert restarted.requested[path]['cache']
    assert runtime.fetch(f'/img/frames/token/m15/{family}/w.png')[0] == source_png()
    assert runtime.fetch(f'/img/frames/token/m15/{family}/a.png')[0] == source_png()
    assert len(calls) == 2


def token(type_line='Token Creature — Eldrazi', colors=None, short=False):
    return {'name': 'Neutral test', 'layout': 'token', 'type_line': type_line,
            'colors': colors or [], 'mana_cost': '', 'rarity': 'common', 'power': '3', 'toughness': '3',
            'oracle_text': 'Flying' if short else '{2}: Draw a card.'}


@pytest.mark.parametrize('short', [False, True])
def test_native_colorless_tokens_select_white_derived_frame_and_white_title(workspace, short):
    store, art, settings = workspace
    card = token(short=short)
    compiler = Compiler(store)
    comp = compiler.compile_face(card, card, 0, {'templateOverride': 'token-classic'}, settings, art)
    family = 'textless' if short else 'regular'
    assert any(frame['src'] == classic_token_frame.PREFIX + family + '-c.png' for frame in comp['data']['frames'])
    assert comp['data']['text']['title']['color'] == 'white'
    assert comp['data']['text']['rules']['color'] == 'black'
    assert comp['templateVersion'] == compiler.template_identity('token', 'token-classic')[1] + 1


@pytest.mark.parametrize('style', ['token-classic', 'token-full-art', 'token-borderless'])
@pytest.mark.parametrize('types,colors', [('Token Artifact Creature — Construct', []),
                                        ('Token Creature — Spirit', ['W']),
                                        ('Token Creature — Spirit', ['W', 'U'])])
def test_other_materials_and_layouts_keep_their_identity(workspace, style, types, colors):
    store, art, settings = workspace
    card = token(types, colors)
    compiler = Compiler(store)
    comp = compiler.compile_face(card, card, 0, {'templateOverride': style}, settings, art)
    assert not any(frame['src'].startswith(classic_token_frame.PREFIX) for frame in comp['data']['frames'])
    assert compiler.template_identity('token', style, card) == compiler.template_identity('token', style)


@pytest.mark.parametrize('explicit', [False, True])
def test_converted_normal_colorless_card_uses_neutral_unless_frame_explicitly_overridden(workspace, explicit):
    store, art, settings = workspace
    card = token('Creature — Eldrazi')
    card.update(layout='normal', mana_cost='{4}', colors=[])
    ws = Workspace(store)
    comp = ws.compiler.compile_face(card, card, 0, {}, settings, art)
    spec = {'token_frame_style': 'token-classic'}
    if explicit:
        spec['frame_color'] = 'A'
    converted = ws._apply_token_spec(comp, spec, art, 'Copy token', sem=semantic(card, card))
    sources = [frame['src'] for frame in converted['data']['frames']]
    expected = '/img/frames/token/m15/regular/a.png' if explicit else classic_token_frame.PREFIX + 'regular-c.png'
    assert expected in sources
    assert converted['data']['text']['title']['color'] == ('#fde367' if explicit else 'white')


@pytest.mark.parametrize('types,colors,style,changes', [
    ('Creature — Eldrazi', [], 'token-classic', True),
    ('Artifact Creature — Construct', [], 'token-classic', False),
    ('Creature — Spirit', ['W'], 'token-classic', False),
    ('Creature — Eldrazi', [], 'token-full-art', False),
])
def test_conversion_material_version_only_invalidates_affected_preparation(workspace, monkeypatch, types, colors, style, changes):
    store, art, settings = workspace
    ws = Workspace(store)
    card = token(types, colors)
    card.update(layout='normal')
    entry = {'scryfall': card, 'faces': [{'index': 0, 'name': card['name']}]}
    settings = ws.validate_settings({**settings, 'allCardsTokens': True, 'templateRules': {'token': style}})
    before = ws._preparation_key(entry, settings, {})
    monkeypatch.setattr(classic_token_frame, 'VERSION', 'future-material')
    after = ws._preparation_key(entry, settings, {})
    assert (before != after) == changes
