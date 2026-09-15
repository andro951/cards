# Artist credits in Proxy Foundry 1.1

## Use the real printing artist

Scryfall artwork always uses the artist credited on the selected printing. When Scryfall supplies face-specific artists, the front and reverse each use their own artist. A Scryfall fallback used for missing custom art follows the same rule.

Your deck's custom-art artist does not overwrite these credits. The card inspector displays the original printing artist separately and disables custom-artist replacement while original Scryfall art is selected. Missing Scryfall artist metadata stays blank instead of being attributed to another artist.

## Set an artist for your own art

Open a deck and select **Art & setup → Credit the artist → Artist for custom artwork in this deck**. This is a convenient default for the custom images in that deck.

Click an individual card to set **Artist for this custom artwork** for that card/face. A per-card value overrides the deck's custom-art default. Clearing that field returns to inheritance; **Intentionally leave the custom artist blank** is an explicit blank override for custom artwork only.

## Add “Modified by ChatGPT”

Enter `Modified by ChatGPT` in **Modification credit for this deck** to use it across the deck, or enter it in one card's **Modification credit** field to apply it only to that face. The actual printed artist line is:

```
Original Artist · Modified by ChatGPT
```

The separator is a centered dot. The complete line is rendered in the existing artist-credit spot; the proxy footer is unchanged. The text is configurable, for example `Extended by Isaac` or `Restored by ChatGPT`.

Each card's modification field inherits the deck value when blank. Entering a per-card value replaces the inherited suffix. **No modification credit on this face** explicitly suppresses the deck value for that face. The preview updates before saving.

## Upload modified original artwork

After uploading your modified or extended artwork for a card, select **Use the original printing artist for this custom image**, then enter the optional modification text. This retains the selected printing's original illustrator even when the deck's custom-art default is someone else.

For unrelated custom artwork, leave that option off and credit the custom artwork's actual creator instead. The app cannot determine the creator of a local image from its pixels.

## Save, regenerate and reuse

Save the card or deck setup, then generate images. The app stores original artist metadata separately from custom overrides and modification text, so repeated generation never appends the suffix repeatedly.

Artist and modification changes invalidate the affected output hash. Quantity-only and back-only edits do not change the front's rendering inputs. Deck duplication, reusable style defaults and backups retain these settings.

Decks prepared before version 1.1 require generation once to pick up v54 and the corrected credit behavior. Existing PNGs and previously packaged order ZIPs are not deleted or silently rewritten. Build a new order from the regenerated deck to print the updated credits.

The print helper is unchanged from the integrated helper version 1.0.0.
