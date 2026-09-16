from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def test_modal_clips_header_and_footer_to_rounded_outline():
    css=(ROOT/'site/forge-theme.css').read_text()
    assert '.modal{overflow:hidden}' in css
