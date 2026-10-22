import copy

import pytest

import foundry.compiler as module
from foundry.compiler import Compiler, apply_gold_artifact_pt, gold_artifact_pt, semantic
from foundry.domain import type_group
from test_pipeline import workspace


def angel(**overrides):
    return {'name': 'Weeping Angel', 'layout': 'normal',
            'type_line': 'Artifact Creature — Alien Angel',
            'mana_cost': '{1}{U}{B}', 'colors': ['U', 'B'],
            'oracle_text': 'Flash\nFirst strike, vigilance', 'rarity': 'rare',
            'power': '2', 'toughness': '2', **overrides}


@pytest.mark.parametrize('choice', ['auto', 'normal'])
@pytest.mark.parametrize('legendary,nickname', [(False, False), (False, True), (True, False)])
def test_multicolor_artifact_changes_only_the_pt_material(workspace, monkeypatch, choice, legendary, nickname):
    store, art, settings = workspace
    card = angel()
    if legendary: card['type_line'] = 'Legendary ' + card['type_line']
    if nickname: card['flavor_name'] = 'Stone Guardian'
    compiler = Compiler(store)
    result = compiler.compile_face(card, card, 0, {'templateOverride': choice}, settings, art)
    with monkeypatch.context() as patch:
        patch.setattr(module, 'apply_gold_artifact_pt', lambda *args: False)
        old = compiler.compile_face(card, card, 0, {'templateOverride': choice}, settings, art)
    expected = copy.deepcopy(old['data'])
    silver = [frame for frame in expected['frames'] if frame['src'].endswith('/m15PTA.png')]
    assert len(silver) == 1
    silver[0].update(src='/img/frames/m15/regular/m15PTM.png', name='Multicolored Power/Toughness')
    assert result['data'] == expected
    assert result['data']['text']['pt']['text'] == '2/2'
    assert result['renderKey'] != old['renderKey']


@pytest.mark.parametrize('colors,cost,types,expected', [
    ([], '{3}', 'Artifact Creature — Golem', 'A'),
    (['U'], '{2}{U}', 'Artifact Creature — Golem', 'A'),
    (['U', 'B'], '{1}{U/B}{U/B}', 'Artifact Creature — Golem', 'C'),
    (['W', 'U', 'B'], '{W}{U}{B}', 'Artifact Creature — Golem', 'M'),
    (['U', 'B'], '{U}{B}', 'Artifact Creature — Vehicle', 'V'),
])
@pytest.mark.parametrize('choice', ['auto', 'normal'])
def test_other_pt_treatments_remain_correct(workspace, colors, cost, types, expected, choice):
    store, art, settings = workspace
    card = angel(colors=colors, mana_cost=cost, type_line=types)
    result = Compiler(store).compile_face(card, card, 0, {'templateOverride': choice}, settings, art)
    pt = [frame for frame in result['data']['frames'] if 'Power/Toughness' in frame['name']]
    assert len(pt) == 1
    assert pt[0]['src'].endswith('/m15PT' + expected + '.png')


def test_template_refresh_is_scoped_and_agrees_for_imported_and_semantic_faces(workspace, monkeypatch):
    store, _, _ = workspace
    compiler = Compiler(store)
    cards = [angel(), angel(colors=['U']), angel(colors=[]),
             angel(mana_cost='{1}{U/B}{U/B}'),
             angel(type_line='Artifact Creature — Vehicle'),
             angel(type_line='Creature — Alien Angel')]
    for card in cards:
        group = type_group(card, card, 0)
        for choice in ('auto', 'normal', 'godzilla-card'):
            current = compiler.template_identity(group, choice, card)
            assert current == compiler.template_identity(group, choice, semantic(card, card))
            with monkeypatch.context() as patch:
                patch.setattr(module, 'gold_artifact_pt', lambda face: False)
                old = compiler.template_identity(group, choice, card)
            changed = card == cards[0] and choice in {'auto', 'normal'}
            assert current[1] == old[1] + int(changed)
            assert current[2] == old[2] + int(changed)


def test_material_change_preserves_geometry_and_is_idempotent():
    frame = {'src': '/img/frames/m15/regular/m15PTA.png', 'name': 'Artifact Power/Toughness',
             'bounds': {'x': .75, 'y': .88, 'width': .19, 'height': .07}, 'masks': []}
    vehicle = {**copy.deepcopy(frame), 'src': '/img/frames/m15/regular/m15PTV.png'}
    data = {'frames': [copy.deepcopy(frame), vehicle], 'text': {'pt': {'text': '2/2'}}}
    assert apply_gold_artifact_pt(data, semantic(angel(), angel()))
    assert data['frames'][0]['bounds'] == frame['bounds']
    assert data['frames'][0]['masks'] == frame['masks']
    assert data['frames'][1] == vehicle
    assert not apply_gold_artifact_pt(data, semantic(angel(), angel()))


@pytest.mark.parametrize('face', [{}, {'name': 'Not hydrated'}, {'type_line': None}, {'types': ['Creature']}])
def test_partial_metadata_does_not_fail_template_refresh(face):
    assert not gold_artifact_pt(face)
    compiler = Compiler(None)
    assert compiler.template_identity('standard', 'auto', face) == compiler.template_identity('standard', 'auto')
