from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_card_grid_uses_hover_back_without_flip_button():
    source = (ROOT / 'site' / 'tokens.js').read_text(encoding='utf-8')
    assert 'pick.onmouseenter=()=>{image.src=thumbnail(back);}' in source
    assert 'pick.onmouseleave=()=>{image.src=front;}' in source
    assert 'pick.onfocus=()=>{image.src=thumbnail(back);}' in source
    assert 'pick.onblur=()=>{image.src=front;}' in source
    assert 'flip-button' not in source
    assert 'data-flip=' not in source
