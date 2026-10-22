import pytest

from foundry.compiler import Compiler, colorless_land_frame_refresh, semantic
from foundry.domain import type_group
from foundry.legacy import compiler as native
from test_land_color_inference import land
from test_pipeline import workspace


def seaside():
    return land('Seaside Haven', 'Land', '{T}: Add {C}.\n{W}{U}, {T}, Sacrifice a Bird: Draw a card.', ['C'])


def test_resolved_colorless_list_is_authoritative_in_the_native_fallback():
    card = seaside()
    sem = semantic(card, card)
    assert sem['land_colors'] == []
    assert native.infer_land_colors(sem, native.get_type_info(sem)) == []
    # The preserved fallback remains available only for unresolved native input.
    unresolved = {**sem, 'land_colors': None}
    assert native.infer_land_colors(unresolved, native.get_type_info(unresolved)) == ['W', 'U']


@pytest.mark.parametrize('name,types,cost', [('Seaside Haven', 'Land', '{W}{U}'),
                                         ('Academy Ruins', 'Legendary Land', '{1}{U}'),
                                         ('Other cost test', 'Land', '{W}{U}{B}{R}{G}')])
@pytest.mark.parametrize('choice', ['auto', 'normal', 'legend-land', 'godzilla-land'])
def test_cost_only_colors_do_not_reach_the_rendered_land_frame(workspace, name, types, cost, choice):
    store, art, settings = workspace
    card = land(name, types, '{T}: Add {C}.\n' + cost + ', {T}: Draw a card.', ['C'])
    compiler = Compiler(store)
    result = compiler.compile_face(card, card, 0, {'templateOverride': choice}, settings, art)
    if choice == 'normal':
        bars = [frame for frame in result['data']['frames'] if any(mask.get('name') in {'Title', 'Type', 'Rules'} for mask in frame['masks'])]
        assert bars and all(frame['src'].endswith('/m15FrameL.png') for frame in bars)
    else:
        sources = [frame['src'] for frame in result['data']['frames']]
        assert any(source.endswith('/TitleL.png') or source.endswith('/CrownL.png')
                   or source.endswith('/m15CrownLFloating.png') for source in sources)
    assert not any('Gradient Pinline' in frame['name'] or 'Right Blend' in frame['name'] for frame in result['data']['frames'])
    assert cost in result['data']['text']['rules']['text']
    assert colorless_land_frame_refresh(card)
    sem = semantic(card, card)
    group = type_group(card, card, 0)
    assert compiler.template_identity(group, choice, card) == compiler.template_identity(group, choice, sem)
    no_cost = {**card, 'oracle_text': '{T}: Add {C}.'}
    assert result['templateVersion'] == compiler.template_identity(group, choice, no_cost)[1] + 1


@pytest.mark.parametrize('card', [
    land('Colorless land', 'Land', '{T}: Add {C}.', ['C']),
    land('Colored land with costs', 'Land', '{T}: Add {G}.\n{W}{U}{B}{R}{G}, {T}: Draw a card.', ['G']),
    land('Three Tree City', 'Legendary Land', '{T}: Add {C}.', list('WUBRGC')),
    land('Nykthos, Shrine to Nyx', 'Legendary Land', '{T}: Add {C}.', list('WUBRGC')),
])
def test_unaffected_land_templates_do_not_receive_another_version(card):
    assert not colorless_land_frame_refresh(card)
