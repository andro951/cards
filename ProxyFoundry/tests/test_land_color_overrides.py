import copy

import pytest

from foundry.compiler import Compiler, LAND_FRAME_COLOR_OVERRIDES, frame_treatment_code, semantic
from foundry.domain import type_group
from test_land_color_inference import land, colors
from test_pipeline import workspace


def example(name):
    if name == 'Myriad Landscape':
        return land(name, 'Land', 'This land enters tapped.\n{T}: Add {C}.\n'
                    '{2}, {T}, Sacrifice this land: Search your library for up to two basic land cards '
                    'that share a land type, put them onto the battlefield tapped, then shuffle.', ['C'])
    if name == 'Nykthos, Shrine to Nyx':
        return land(name, 'Legendary Land', '{T}: Add {C}.\n{2}, {T}: Choose a color. '
                    'Add an amount of mana of that color equal to your devotion to that color. '
                    '(Your devotion to a color is the number of mana symbols of that color in '
                    'the mana costs of permanents you control.)', list('WUBRGC'))
    return land(name, 'Legendary Land', 'As this land enters, choose a creature type.\n{T}: Add {C}.\n'
                '{2}, {T}: Choose a color. Add an amount of mana of that color equal to the number '
                'of creatures you control of the chosen type.', list('WUBRGC'))


@pytest.mark.parametrize('name,expected', [('Myriad Landscape', []), ('Three Tree City', list('WUBRG')),
                                         ('Nykthos, Shrine to Nyx', list('WUBRG'))])
def test_only_the_exact_named_land_gets_the_override(name, expected):
    card = example(name)
    assert semantic(card, card)['land_colors'] == expected
    unnamed = {**card, 'name': 'Other Land'}
    assert colors(unnamed) == (list('WUBRG') if name == 'Myriad Landscape' else [])
    assert semantic({**card, 'flavor_name': 'A nickname'}, {**card, 'flavor_name': 'A nickname'})['land_colors'] == expected
    nonland = {**card, 'type_line': 'Creature — Shapeshifter'}
    assert not semantic(nonland, nonland).get('land_colors')


@pytest.mark.parametrize('name,code', [('Myriad Landscape', 'L'), ('Three Tree City', 'M'),
                                     ('Nykthos, Shrine to Nyx', 'M')])
@pytest.mark.parametrize('choice', ['auto', 'normal', 'legend-land', 'godzilla-land'])
def test_land_color_exceptions_reach_the_actual_frame_and_only_refresh_those_cards(workspace, name, code, choice):
    store, art, settings = workspace
    card = example(name)
    compiler = Compiler(store)
    sem = semantic(card, card)
    group = type_group(card, card, 0)
    assert frame_treatment_code(sem) == code
    result = compiler.compile_face(card, card, 0, {'templateOverride': choice}, settings, art)
    if choice == 'normal':
        bars = [frame for frame in result['data']['frames'] if any(mask.get('name') in {'Title', 'Type'} for mask in frame['masks'])]
        assert bars and all(frame['src'].endswith(f'/m15Frame{code}.png') for frame in bars)
    else:
        sources = [frame['src'] for frame in result['data']['frames']]
        assert any(source.endswith(f'/m15Crown{code}Floating.png') or source.endswith(f'/Title{code}.png')
                   or source.endswith(f'/Crown{code}.png') for source in sources)
    assert result['templateVersion'] == compiler.template_identity(group, choice, {**sem, 'name': 'Other Land'})[1] + 1
    before = compiler.template_identity(group, choice, {**sem, 'name': 'Other Land'})
    # Removing the exception must not alter unrelated card identities.
    saved = copy.deepcopy(LAND_FRAME_COLOR_OVERRIDES)
    try:
        LAND_FRAME_COLOR_OVERRIDES.clear()
        assert compiler.template_identity(group, choice, {**sem, 'name': 'Other Land'}) == before
    finally:
        LAND_FRAME_COLOR_OVERRIDES.update(saved)
