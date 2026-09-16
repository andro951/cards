from pathlib import Path


def test_scryfall_source_hides_custom_art_fallback_control():
    source=Path("site/setup.js").read_text(encoding="utf-8")
    assert 'class="check-line ${s.source.mode===\'scryfall\'?\'hidden\':\'\'}" id="fallback-line"' in source
    assert "$('#fallback-line',root).classList.toggle('hidden',s.source.mode==='scryfall')" in source
