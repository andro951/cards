from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_card_grid_uses_hover_back_without_flip_button():
    source = (ROOT / 'site' / 'deck.js').read_text(encoding='utf-8')
    assert 'data-hover-back' in source
    assert 'data-hover-front' in source
    assert 'card.onmouseenter' in source
    assert 'card.onmouseleave' in source
    assert 'backPreview(c,d)' in source
    assert 'flip-button' not in source
    assert 'data-flip=' not in source
    assert 'v.flipped' not in source
