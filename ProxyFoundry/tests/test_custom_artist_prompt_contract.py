from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_custom_artist_prompt_and_no_printing_fallback_contract():
    credits=(ROOT/'site/credits.js').read_text(encoding='utf-8')
    deck=(ROOT/'site/deck.js').read_text(encoding='utf-8')
    setup=(ROOT/'site/setup.js').read_text(encoding='utf-8')
    assert 'ensureCustomArtCredits' in credits
    assert 'One artist for all custom artwork' in credits
    assert 'Specify the artist for each card' in credits
    assert "(deckArtist||'')" in credits
    assert 'await ensureCustomArtCredits(d)' in deck
    assert 'Generate images will ask' in setup
