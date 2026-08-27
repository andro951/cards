# Derevi proxy sync status

- Card Conjurer entries audited against current Scryfall data: **26**
- Scryfall card pages individually fetched successfully: **26/26**
- Cards with current Oracle/mana/type/P-T differences applied: **5**
- Enchantments using M15 Nyx frames: **2**
- Visible text fields with non-ASCII characters remaining: **0**
- Custom art references: **complete**

See `SCRYFALL_RULES_AUDIT.md` for the per-card Scryfall page audit.

## Legendary crown audit
- Legendary cards: **12**; all have exactly one matching crown.
- Nonlegendary cards: **14**; all have no crown.
- Crown mismatches remaining: **0**.

## Exact art-fit audit
- Cards recalculated from actual PNG dimensions: **26**.
- Official Auto Fit reference cards reproduced exactly: **3/3**.
- Art-fit mismatches remaining: **0**.
- Stored numeric placement is used; no card requires the on-load auto-fit script.
- See `ART_FIT_AUDIT.md` for every image dimension and calculated value.
