import copy

import pytest

from foundry.compiler import Compiler, semantic
from foundry.workspace import Workspace
from test_pipeline import workspace


def harmonized():
    return {'name': 'Harmonized Trio // Brainstorm', 'layout': 'prepare',
            'rarity': 'rare', 'colors': ['U'], 'card_faces': [
        {'name': 'Harmonized Trio', 'type_line': 'Creature — Merfolk Bard Wizard',
         'mana_cost': '{U}', 'power': '1', 'toughness': '1',
         'oracle_text': '{T}, Tap two untapped creatures you control: This creature becomes prepared. '
                        '(While it is prepared, you may cast a copy of its spell. Doing so unprepares it.)'},
        {'name': 'Brainstorm', 'type_line': 'Instant', 'mana_cost': '{U}',
         'oracle_text': 'Draw three cards, then put two cards from your hand on top of your library in any order.'}]}


def compile_card(workspace, nickname=''):
    store, art, settings = workspace
    card = harmonized()
    options = {'semanticOverrides': {'nickname': nickname}}
    comp = Compiler(store).compile_face(card, card['card_faces'][0], 0, options, settings, art)
    sem = semantic(card, card['card_faces'][0]); sem['nickname'] = nickname
    return Workspace(store), comp, sem


@pytest.mark.parametrize('style', ['token-classic', 'token-full-art', 'token-borderless'])
def test_prepare_conversion_keeps_both_complete_panels_and_uses_arch(workspace, style):
    ws, comp, sem = compile_card(workspace)
    original = copy.deepcopy(comp['data'])
    result = ws._apply_token_spec(comp, {'token_frame_style': style}, workspace[1], 'Prepare token', sem=sem)
    data = result['data']
    assert result['group'] == 'token'
    assert data['prepareToken']
    for key in ('type', 'rules', 'title2', 'mana2', 'type2', 'rules2', 'pt'):
        assert data['text'][key] == original['text'][key]
    assert data['setSymbolBounds'] == original['setSymbolBounds']
    assert data['artBounds'] == {'x': .0767, 'y': .1248, 'width': .8476, 'height': .431}
    headers = [f for f in data['frames'] if f.get('prepareTokenHeader')]
    assert any(f['src'] == '/img/frames/token/m15/regular/u.png' for f in headers)
    assert all(any(m['name'] == 'Arched upper frame' for m in f['masks']) for f in headers)
    lower = [f for f in data['frames'] if not f.get('prepareTokenHeader')]
    assert lower
    assert all(sum(m['name'] == 'Prepare lower panels' for m in f['masks']) == 1 for f in lower)
    assert result['renderKey'] and result['render'] is None


@pytest.mark.parametrize('nickname', ['', 'The Singing Sisters'])
@pytest.mark.parametrize('force_frame', [False, True])
def test_token_options_do_not_replace_or_overwrite_the_prepared_spell(workspace, nickname, force_frame):
    ws, comp, sem = compile_card(workspace, nickname)
    spell = {k: copy.deepcopy(v) for k, v in comp['data']['text'].items() if k.endswith('2')}
    spec = {'nonlegendary': True, 'replace_creature_subtypes': 'Illusion',
            'power_toughness': '0/1', 'force_nickname_frame': force_frame}
    result = ws._apply_token_spec(comp, spec, workspace[1], 'Prepare token', sem=sem)
    data = result['data']
    assert data.get('prepareToken')
    assert any(f.get('prepareTokenHeader') for f in data['frames'])
    assert 'Illusion' in data['text']['type']['text']
    assert 'Merfolk' not in data['text']['type']['text']
    assert data['text']['pt']['text'] == '0/1'
    assert {k: v for k, v in data['text'].items() if k.endswith('2')} == spell
    if nickname:
        assert data['text']['nickname']['text'] == nickname
        assert data['text']['title']['text'] == 'Harmonized Trio'
        assert sum(f['name'] == 'Nickname Title' for f in data['frames']) == 1


def test_individual_then_deck_wide_conversion_replaces_header_without_stacking(workspace):
    ws, comp, sem = compile_card(workspace)
    original = copy.deepcopy(comp)
    spec = {'token_frame_style': 'token-classic', 'power_toughness': '0/1',
            'replace_creature_subtypes': 'Illusion'}
    once = ws._apply_token_spec(original, spec, workspace[1], 'Prepare token', sem=sem)
    staged = ws._apply_token_spec(comp, spec, workspace[1], 'Prepare token', sem=sem, finalize=False)
    twice = ws._apply_token_spec(staged, spec, workspace[1], 'Prepare token', sem=sem)
    assert twice['data'] == once['data']
    assert twice['renderKey'] == once['renderKey']


def test_explicit_token_frame_color_changes_host_panels_but_keeps_spell_color(workspace):
    ws, comp, sem = compile_card(workspace)
    result = ws._apply_token_spec(comp, {'frame_color': 'W'}, workspace[1], 'Prepare token', sem=sem)
    data = result['data']
    assert any(f['src'] == '/img/frames/token/m15/regular/w.png' for f in data['frames'])
    host_type = [f for f in data['frames'] if any(m['name'] == 'Type' for m in f['masks'])]
    assert host_type and all(f['src'] == '/img/frames/prepare/regular/w.png' for f in host_type)
    spell = [f for f in data['frames'] if any(m['name'] == 'Prepare Spell' for m in f['masks'])]
    assert spell and all(f['src'] == '/img/frames/prepare/regular/u.png' for f in spell)


@pytest.mark.parametrize('prepare,converted', [(True, True), (True, False), (False, True), (False, False)])
def test_layout_version_only_refreshes_converted_prepare_cards(workspace, monkeypatch, prepare, converted):
    import foundry.workspace as module
    ws, _, _ = compile_card(workspace)
    card = harmonized()
    if not prepare:
        card = {**card['card_faces'][0], 'layout': 'normal', 'rarity': 'rare', 'colors': ['U']}
    entry = ws.sources.entry(card)
    settings = ws.validate_settings({**workspace[2], 'allCardsTokens': converted})
    before = ws._preparation_key(entry, settings, {})
    monkeypatch.setattr(module, 'PREPARE_TOKEN_LAYOUT_VERSION', 'future-prepare-layout')
    after = ws._preparation_key(entry, settings, {})
    assert (before != after) == (prepare and converted)
