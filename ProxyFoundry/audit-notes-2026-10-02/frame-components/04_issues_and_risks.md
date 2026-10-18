# Risks requiring visual checks
- A recognized mask in a lower layer does not guarantee visibility: Station complete overlay can obscure donor title/type bars.
- Crown compatibility varies; adding standard M15 crowns everywhere can break planeswalker, Saga, flip and rotated Battle layouts.
- _FRAME_BOX_MASKS recognizes Title/Type/Rules/Text/Text (Right), not every nested or alternate upstream name.
- Modal, tall planeswalker, Flip, textless basic and generated Godzilla source families are not all mapped by _frame_effect_source.
- Custom templates and scan/helper designs require explicit exceptions; do not color scans as frames.
