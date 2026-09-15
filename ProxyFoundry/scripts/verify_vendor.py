"""Fail rather than silently change the approved Card Tools v58 templates."""
from pathlib import Path
import hashlib
ROOT = Path(__file__).resolve().parents[1] / 'vendor/card_tools'
EXPECTED = {
    'pipeline/card_data_to_cardconjurer.py': '0bc9c2a0c5cb15b71316dfeb092723362160bd2b',
    'pipeline/scryfall_to_card_data.py': '773e95f16ac28d53b0a0791efb04bb3cc34293ec',
    'pipeline/scryfall_deck_to_cardconjurer.py': '65f4ccfd069546ebc1e704c2e89c880554d9a5fc',
    'tools/make_copy_tokens.py': '21ca6e6cd0761a648659a707e6264c75e9c382c7',
}
def verify():
    for name, expected in EXPECTED.items():
        raw = (ROOT / name).read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if actual != expected:
            raise RuntimeError(f'Approved Card Tools source was modified: {name} ({actual})')
    return len(EXPECTED)
if __name__ == '__main__':
    print(f'{verify()} approved Card Tools files verified byte-for-byte.')
