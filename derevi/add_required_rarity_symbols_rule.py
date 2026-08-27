from pathlib import Path

path = Path('derevi/STYLE_RULES.md')
text = path.read_text(encoding='utf-8')
needle = "- Do not revert cards to the old single `derevi_set_symbol.png` source.\n"
insert = """- Do not revert cards to the old single `derevi_set_symbol.png` source.\n\n### Required rarity-symbol assets\n\n- A card is not considered correctly finished unless the project has the rarity-symbol asset matching that card's original printed rarity.\n- The complete expected set is `mythic.png`, `rare.png`, `uncommon.png`, and `common.png`.\n- Before finalizing a card, check its original printed rarity and verify that the matching rarity-symbol asset exists and is accessible.\n- If the needed rarity-symbol asset is missing, stop and ask the user for that symbol before finishing or committing the card.\n- Never substitute another rarity symbol, silently use a generic symbol, or fall back to the old single `derevi_set_symbol.png`.\n"""
if '### Required rarity-symbol assets' not in text:
    if needle not in text:
        raise SystemExit('Insertion point not found')
    text = text.replace(needle, insert, 1)
path.write_text(text, encoding='utf-8')
print('Updated STYLE_RULES.md')
