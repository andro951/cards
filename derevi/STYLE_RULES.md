# Derevi proxy layout rules

Card Conjurer source of truth: `derevi_cards.cardconjurer`.

- Type text box width: **1560 px** on every card.
- Title text box width: **1680 - (95 × number of mana symbols) px**.
  - 0 symbols: 1680 px
  - 1 symbol: 1585 px
  - 2 symbols: 1490 px
  - 3 symbols: 1395 px
- Do not crop or resize source artwork files. Framing/cropping is handled with Card Conjurer `artX`, `artY`, and `artZoom` values.
- Artist footer: ChatGPT with the Card Conjurer artist/paintbrush glyph.
- Footer notice: `Custom Proxy • Personal Use Only`.
- No collector number, rarity, set code, language metadata, Wizards legal line, or CardConjurer.com footer.
- Shared Derevi assets: `derevi_set_symbol.png` and `wings_emblem.png`.
