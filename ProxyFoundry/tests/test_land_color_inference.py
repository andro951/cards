from foundry.compiler import semantic


def land(name,type_line,oracle_text,produced_mana=None):
    return {
        'object':'card',
        'id':'11111111-1111-4111-8111-111111111111',
        'oracle_id':'22222222-2222-4222-8222-222222222222',
        'name':name,
        'layout':'normal',
        'type_line':type_line,
        'oracle_text':oracle_text,
        'colors':[],
        'mana_cost':'',
        'rarity':'rare',
        'set':'tst',
        'collector_number':'1',
        'artist':'Test Artist',
        'produced_mana':produced_mana or [],
    }


def colors(card):
    return semantic(card,card,0).get('land_colors',[])


def test_world_tree_uses_its_printed_green_mana_ability_not_conditional_wubrg_access():
    card=land(
        'The World Tree',
        'Legendary Land',
        '{T}: Add {G}.\n'
        'As long as you control six or more lands, lands you control have “{T}: Add one mana of any color.”\n'
        '{W}{W}{U}{U}{B}{B}{R}{R}{G}{G}, {T}, Sacrifice The World Tree: '
        'Search your library for any number of God cards, put them onto the battlefield, then shuffle.',
        ['W','U','B','R','G'],
    )
    assert colors(card)==['G']


def test_activation_cost_colors_do_not_color_the_land_frame():
    card=land(
        'Cost Symbol Test',
        'Land',
        '{T}: Add {G}.\n{W}{U}{B}{R}{G}, {T}: Draw a card.',
        ['W','U','B','R','G'],
    )
    assert colors(card)==['G']


def test_direct_any_color_mana_ability_is_five_color():
    card=land(
        'Mana Confluence Test',
        'Land',
        '{T}, Pay 1 life: Add one mana of any color.',
        ['W','U','B','R','G'],
    )
    assert colors(card)==list('WUBRG')


def test_basic_land_subtype_and_direct_extra_outputs_are_combined():
    card=land(
        'Murmuring Bosk Test',
        'Land — Forest',
        '{T}: Add {G}.\n{T}: Add {W} or {B}. This land deals 1 damage to you.',
        ['W','B','G'],
    )
    assert colors(card)==['G','W','B']


def test_fetch_land_infers_colors_from_basic_land_types_it_searches_for():
    card=land(
        'Verdant Catacombs Test',
        'Land',
        '{T}, Pay 1 life, Sacrifice this land: Search your library for a Swamp or Forest card, '
        'put it onto the battlefield, then shuffle.',
        [],
    )
    assert colors(card)==['B','G']


def test_conditional_choose_a_color_effect_does_not_turn_nykthos_gold():
    card=land(
        'Nykthos Test',
        'Legendary Land',
        '{T}: Add {C}.\n{2}, {T}: Choose a color. Add an amount of mana of that color equal to your devotion to that color.',
        ['W','U','B','R','G','C'],
    )
    assert colors(card)==[]


def test_nonbasic_land_subtypes_do_not_crash_color_inference():
    card=land(
        'Desert Test',
        'Land — Desert',
        '{T}: Add {C}.',
        ['C'],
    )
    assert colors(card)==[]


def test_academy_ruins_is_colorless_despite_blue_nonmana_activation_cost():
    card=land(
        'Academy Ruins',
        'Legendary Land',
        '{T}: Add {C}.\n{1}{U}, {T}: Put target artifact card from your graveyard on top of your library.',
        ['C'],
    )
    assert colors(card)==[]
