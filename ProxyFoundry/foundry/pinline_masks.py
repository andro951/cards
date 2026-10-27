"""Bundled native outlines restore black edges above two-color gradients."""
PREFIX='/img/frames/proxy-foundry/masks/'
SOURCES={
    'm15-pinline':('/img/frames/m15/regular/m15MaskPinline.png','/img/frames/m15/regular/m15FrameM.png'),
    'm15-super-pinline':('/img/frames/m15/regular/m15MaskPinlineSuper.png','/img/frames/m15/regular/m15FrameM.png'),
    'showcase-pinline':('/img/frames/m15/genericShowcase/m15GenericShowcaseMaskPinline.png','/img/frames/m15/genericShowcase/m15GenericShowcaseFrameM.png'),
    'transform-front-pinline':('/img/frames/m15/transform/regular/maskPinlineFront.png','/img/frames/m15/transform/regular/frontM.png'),
    'transform-back-pinline':('/img/frames/m15/transform/regular/maskPinlineBack.png','/img/frames/m15/transform/regular/backM.png'),
    'transform-new-back-pinline':('/img/frames/m15/transform/regular/new/maskPinlineBack.png','/img/frames/m15/transform/regular/new/backM.png'),
    'battle-pinline':('/img/frames/m15/battle/maskPinline.png','/img/frames/m15/battle/m.png'),
    'flip-pinline':('/img/frames/m15/flip/pinline.svg','/img/frames/m15/flip/m.png'),
    'modal-pinline':('/img/frames/modal/regular/pinline.svg','/img/frames/modal/regular/m.png'),
    'token-pinline':('/img/frames/token/tokenMaskRegularPinline.png','/img/frames/token/regular/tokenFrameMRegular.png'),
    'token-textless-pinline':('/img/frames/token/tokenMaskTextlessPinline.png','/img/frames/token/textless/tokenFrameMTextless.png'),
    'token-classic-pinline':('/img/frames/token/m15/regular/pinline.svg','/img/frames/token/m15/regular/m.png'),
    'token-classic-textless-pinline':('/img/frames/token/m15/textless/pinline.svg','/img/frames/token/m15/textless/m.png'),
    'token-short-pinline':('/img/frames/token/short/m15MaskPinlineSuperShort.png','/img/frames/token/short/tokenFrameMShort.png'),
    'walker-pinline':('/img/frames/planeswalker/regular/planeswalkerMaskPinline.png','/img/frames/planeswalker/regular/planeswalkerFrameM.png'),
    'walker-tall-pinline':('/img/frames/planeswalker/tall/planeswalkerTallMaskPinline.png','/img/frames/planeswalker/tall/planeswalkerTallM.png'),
}
OUTLINES={source:PREFIX+name+'-outline.png' for name,(source,_) in SOURCES.items()}
OUTLINES.update({
    '/img/frames/proxy-foundry/planeswalker/MaskPinlineRegular.png':PREFIX+'walker-pinline-outline.png',
    '/img/frames/proxy-foundry/planeswalker/MaskPinlineClassicTall.png':PREFIX+'walker-tall-pinline-outline.png',
})
BUNDLED={path.rsplit('/',1)[-1] for path in OUTLINES.values()}
