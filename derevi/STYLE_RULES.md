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

## Art fitting
- New hosted art should default to Card Conjurer's built-in centered **Auto Fit Art** behavior.
- Preserve the original image file; cropping is controlled only by `artX`, `artY`, and `artZoom`.
- Manual repositioning is only needed when the centered crop is compositionally undesirable.

## Typography / character safety
- Use Derevi's text-box geometry as the canonical template for every card; only card-specific text, title width, and rules font size should normally differ.
- Visible card text must use ASCII punctuation for Card Conjurer compatibility.
- Use a normal hyphen with spaces (` - `) instead of em/en dashes in type lines and ability labels.
- Use straight apostrophes (`'`) and straight double quotes (`"`), not smart/curly quotes.
- Do not allow replacement/square characters in title, mana, type, rules, or power/toughness text.

## Enchantment frames
- Enchantments use the M15 Nyx frame by default.
- This includes enchantment creatures.
- Keep Derevi-derived text/art geometry unless the card itself requires a small adjustment.

## Legendary crowns
- Every permanent whose current type line contains `Legendary` uses the appropriate M15 legendary crown.
- Nonlegendary cards never use a legendary crown, regardless of rarity.
- Crown color/type follows the active base frame (white, blue, black, red, green, multicolored, artifact, or land).
- Nyx treatment and legendary crowns are independent: a legendary enchantment would use both.
