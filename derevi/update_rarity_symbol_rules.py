from pathlib import Path

path = Path('derevi/STYLE_RULES.md')
text = path.read_text(encoding='utf-8')
old = """Shared assets:\n- Set symbol: `https://raw.githubusercontent.com/andro951/cards/main/derevi/derevi_set_symbol.png`\n- Do not add a bottom wings emblem; it was intentionally removed from all cards.\n"""
new = """Shared assets:\n- Set symbols are rarity-specific and use each card's original printed rarity:\n  - Mythic: `https://raw.githubusercontent.com/andro951/cards/main/derevi/mythic.png`\n  - Rare: `https://raw.githubusercontent.com/andro951/cards/main/derevi/rare.png`\n  - Uncommon: `https://raw.githubusercontent.com/andro951/cards/main/derevi/uncommon.png`\n  - Common: `https://raw.githubusercontent.com/andro951/cards/main/derevi/common.png`\n- Do not revert cards to the old single `derevi_set_symbol.png` source.\n- Do not add a bottom wings emblem; it was intentionally removed from all cards.\n"""
if old not in text:
    raise SystemExit('Shared-assets block not found')
text = text.replace(old, new, 1)
text = text.replace('Preserve artist/footer/set-symbol/no-metadata conventions; do not restore the removed bottom wings emblem.', 'Preserve artist/footer/rarity-specific set-symbol/no-metadata conventions; do not restore the removed bottom wings emblem.', 1)
path.write_text(text, encoding='utf-8')
