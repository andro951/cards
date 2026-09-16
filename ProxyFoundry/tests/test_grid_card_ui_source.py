from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_grid_cards_keep_name_on_card_and_no_metadata_below():
    deck = (ROOT / 'site/deck.js').read_text(encoding='utf-8')
    start = deck.index('  function cardsGrid(){')
    end = deck.index('  cardsGrid();', start)
    grid = deck[start:end]

    assert 'class="card-name-pill"' in grid
    assert 'class="quantity-pill"' in grid
    assert 'class="card-credit"' not in grid
    assert 'class="card-item-footer"' not in grid
    assert '</button><h3' not in grid
    assert 'collector_number' not in grid
    assert "f.compiled?.render?'Rendered':'Not rendered'" not in grid

    theme = (ROOT / 'site/forge-theme.css').read_text(encoding='utf-8')
    assert '.card-name-pill{position:absolute' in theme
