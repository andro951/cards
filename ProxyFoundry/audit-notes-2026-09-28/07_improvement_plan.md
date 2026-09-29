# Ordered improvement plan for the next task

1. Freeze representative fixtures: a normal non-land, land, legendary card, native Scryfall token, colorless token, black token, and a deck-wide converted token. Include `data.json` with nickname and flavor. Confirm native frame asset availability and text-outline property names before changing output.
2. Add direct local file and direct GitHub file/link import, both using the current v1 validator and staged `cardData` save contract. Keep one-click root discovery. Cover invalid/duplicate/unknown names.
3. Define explicit template choice behavior for Godzilla land and non-land groups. Decide how existing nickname-only decks migrate so their current automatic appearance is preserved until the user picks a frame. Keep structural groups compatible.
4. Compose Godzilla treatment after either token path, using complete frame pieces. Apply white text with a black outline to type, rules and flavor, and check layering/P/T for each representative color.
5. Build the Art & setup frame picker as a modal with representative card previews. Compile and render one applicable card per choice, show loading/error states, cache previews by compiled identity, and save only the selected rule.
6. Run compiler, browser and native-render tests; inspect sample PNGs at full size. Verify cache invalidation and print-order snapshot behavior. Reconcile the vendor guard discrepancy separately.
