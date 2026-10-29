"""On-demand pinned CardConjurer files. Never download or unpack a repository archive."""
from __future__ import annotations
import base64,html,io,json,mimetypes,re,threading,hashlib
from pathlib import Path
from urllib.parse import quote,unquote,urlsplit
from xml.etree import ElementTree
from PIL import Image,ImageDraw,ImageChops,ImageFilter
from .nickname_geometry import TITLE_BAR_HEIGHT,TITLE_JOINED_HEIGHT,TITLE_BAR_VERSION
from .domain import ValidationError,CC_REPO,CC_COMMIT,COMPAT_REPO,COMPAT_COMMIT,STATION_SCRIPT_URL,STATION_SCRIPT_SHA256
from .artifact_frame import ArtifactFrameCache
from . import classic_token_frame
from . import dual_land_rules
from .transform_crown import restore_crown_bevel,BEVEL_VERSION,mirror_header_png,BACK_VERSION
from .werewolf_frame import neutralize_icon_surround,ICON_RING_VERSION
from .dfc_material import color_title_png,VERSION as DFC_MATERIAL_VERSION
from .planeswalker_frame import PREFIX as PW_PREFIX,TALL_VERSION,PINLINE_VERSION,CLASSIC_PINLINE_VERSION,pinline_without_loyalty_png,nickname_pinline_png,extend_rules_png,extend_rules_svg,renderer_script as planeswalker_renderer_script
from .devoid_frame import PREFIX as DEVOID_PREFIX,VERSION as DEVOID_VERSION,transparent_header_png
from .saga_frame import PREFIX as SAGA_PREFIX,VERSION as SAGA_VERSION,transform_back_png
from .pinline_masks import PREFIX as PINLINE_MASK_PREFIX,BUNDLED as PINLINE_OUTLINE_FILES

class Runtime:
    SOURCE_FILES=('/creator/index.html','/js/main-1.js','/js/creator-23.js','/js/frames/groupStandard-3.js','/js/frames/packM15Regular-1.js','/css/style-9.css')
    COLORLESS_SAGA_CREATURE_PATH='/img/frames/saga/creature/c.png'
    COLORLESS_SAGA_CREATURE_REPO='joshbirnholz/cardconjurer'
    COLORLESS_SAGA_CREATURE_COMMIT='d3c6706692898d596ec6a5be0be44f63062c9e12'
    def __init__(self,network):
        self.net=network;self.requested={};self.lock=threading.Lock()
        self.artifact_frames=None
        self.derived_locks={}
    @staticmethod
    def path(raw):
        p=unquote(str(raw)).split('?',1)[0]
        if not p.startswith(('/js/','/img/','/fonts/','/css/','/creator/')) or any(x in {'.','..'} for x in p.split('/')) or '\\' in p or '\x00' in p:
            raise ValidationError('Invalid CardConjurer dependency path.')
        return p
    @classmethod
    def upstream_alias(cls,url):
        u=urlsplit(str(url))
        if u.scheme not in {'http','https'} or u.username or u.password:return None
        if u.hostname not in {'cardconjurer.app','www.cardconjurer.app','cardconjurer.com','www.cardconjurer.com'}:return None
        return cls.path(u.path)
    def creator_script(self):
        """Patch native inline mana wrapping while preserving the pinned renderer."""
        path='/js/creator-23.js'
        url='https://raw.githubusercontent.com/'+CC_REPO+'/'+CC_COMMIT+quote(path,safe='/')
        raw,mime,meta=self.net.fetch(url,immutable=True)
        text=raw.decode('utf-8').replace('\r\n','\n')
        symbol_anchor="loadManaSymbols(true, ['e', 'a']);"
        symbol_replacement=symbol_anchor+"""
loadManaSymbols(true, ['infinity'], [1.4, 0.65]);
function proxyFoundryInlineSymbols(text) {
    //Braced infinity denotes a mana cost; plain infinity is a rules glyph.
    return text.replace(/\\{\\u221e\\}|\\u221e/g, token => token.length > 1 ? `{inf}` : `{infinity}`);
}"""
        token_anchor="var splitText = rawText.replace(/\\n/g, '{line}')"
        token_replacement="var splitText = proxyFoundryInlineSymbols(rawText).replace(/\\n/g, '{line}')"
        metrics_anchor="\t\t\t\tdrawingText = false;"
        metrics_replacement=metrics_anchor+"\n\t\t\t\ttextObject.proxyFoundryTextFit = {size: startingTextSize, height: currentY};"
        fit_anchor="\touterloop: while (drawingText) {"
        fit_replacement="""\t//Calculated mana wraps belong only to the current font-size attempt.
\tvar proxyFoundrySourceTokens = splitText.slice();
\touterloop: while (drawingText) {
\t\tsplitText = proxyFoundrySourceTokens.slice();"""
        loop_anchor="""		//Begin looping through words/codes
		innerloop: for (word of splitText) {
			var wordToWrite = word;"""
        loop_replacement="""		//Begin looping through words/codes
		function proxyFoundryManaSymbolForToken(token) {
			if (typeof token != 'string' || !token.includes('{') || !token.includes('}')) return null;
			var code = token.toLowerCase().replace('{', '').replace('}', '').replaceAll('/', '');
			if (['bar', 'whitebar', 'planechase'].includes(code)) return null;
			var symbol = null;
			if (textObject.manaPrefix) {
				symbol = getManaSymbol(textObject.manaPrefix + code) || getManaSymbol(textObject.manaPrefix + code.split('').reverse().join(''));
			}
			return symbol || getManaSymbol(code) || getManaSymbol(code.split('').reverse().join('')) || null;
		}
		function proxyFoundryManaClusterWidth(startIndex) {
			var total = 0;
			var index = startIndex;
			var lastBaseWidth = 0;
			var lastSpacing = 0;
			while (index < splitText.length) {
				var symbol = proxyFoundryManaSymbolForToken(splitText[index]);
				if (!symbol) break;
				var spacing = textSize * 0.04 + textManaSpacing;
				var baseWidth = symbol.width * textSize * 0.78;
				total += baseWidth + spacing * 2;
				lastBaseWidth = baseWidth;
				lastSpacing = spacing;
				index ++;
			}
			if (index < splitText.length && typeof splitText[index] == 'string' && /^[,:;.?!]+$/.test(splitText[index])) {
				total += lineContext.measureText(splitText[index]).width;
			}
			if (textObject.manaImageScale > 1 && lastBaseWidth) {
				total += Math.max(0, (textObject.manaImageScale - 1) * lastBaseWidth / 2 - lastSpacing);
			}
			return total;
		}
		innerloop: for (var proxyFoundryWordIndex = 0; proxyFoundryWordIndex < splitText.length; proxyFoundryWordIndex ++) {
			var word = splitText[proxyFoundryWordIndex];
			var wordToWrite = word;"""
        mana_anchor="""					var manaSymbolSpacing = textSize * 0.04 + textManaSpacing;
					var manaSymbolWidth = manaSymbol.width * textSize * 0.78;
					var manaSymbolHeight = manaSymbol.height * textSize * 0.78;
					var manaSymbolX = currentX + canvasMargin + manaSymbolSpacing;"""
        mana_replacement="""					var manaSymbolSpacing = textSize * 0.04 + textManaSpacing;
					var manaSymbolWidth = manaSymbol.width * textSize * 0.78;
					var manaSymbolHeight = manaSymbol.height * textSize * 0.78;
					if (!textObject.manaPlacement && !textObject.manaLayout && !textOneLine && textArcRadius == 0 && currentX > startingCurrentX) {
						var previousManaSymbol = proxyFoundryManaSymbolForToken(splitText[proxyFoundryWordIndex - 1]);
						if (!previousManaSymbol) {
							var manaClusterWidth = proxyFoundryManaClusterWidth(proxyFoundryWordIndex);
							if (manaClusterWidth > 0 && currentX + manaClusterWidth >= textWidth) {
								splitText.splice(proxyFoundryWordIndex, 0, '{lns}');
								proxyFoundryWordIndex --;
								continue innerloop;
							}
						}
					}
					var manaSymbolX = currentX + canvasMargin + manaSymbolSpacing;"""
        if any(text.count(anchor)!=1 for anchor in (symbol_anchor,token_anchor,metrics_anchor,fit_anchor,loop_anchor,mana_anchor)):
            raise ValidationError('Pinned CardConjurer text renderer changed unexpectedly; inline mana wrapping was not patched.')
        text=text.replace(symbol_anchor,symbol_replacement).replace(token_anchor,token_replacement).replace(metrics_anchor,metrics_replacement).replace(fit_anchor,fit_replacement).replace(loop_anchor,loop_replacement).replace(mana_anchor,mana_replacement)
        editor_anchors={
            "var frameToAdd = JSON.parse(JSON.stringify(availableFrames[selectedFrameIndex]));":"var frameToAdd = loadingFrame || JSON.parse(JSON.stringify(availableFrames[selectedFrameIndex]));",
            "\tvar frameElement = document.createElement('div');":"\tif (window.__PF_WORKER_CORE && window.__PF_RUNTIME?.active) return;\n\tvar frameElement = document.createElement('div');",
            "\tdocument.querySelector('#text-options').innerHTML = null;":"\tif (window.__PF_WORKER_CORE && window.__PF_RUNTIME?.active) { selectedTextIndex = 0; var firstText = Object.values(card.text)[0]; document.querySelector('#text-editor').value = firstText.text; document.querySelector('#text-editor-font-size').value = firstText.fontSize || 0; return; }\n\tdocument.querySelector('#text-options').innerHTML = null;"
        }
        for anchor,replacement in editor_anchors.items():
            if text.count(anchor)!=1:raise ValidationError('Pinned CardConjurer loading controls changed unexpectedly.')
            text=text.replace(anchor,replacement)
        with self.lock:self.requested[path]={'url':url,'bytes':len(raw),'cache':meta.get('cache',False),'sha256':hashlib.sha256(raw).hexdigest(),'adapter':'inline mana cluster wrapping'}
        return text.encode(),'application/javascript'

    def station_script(self):
        """Fetch the native Station module from a pinned upstream commit.

        Only its UI property assignment is made CSP-safe; drawing/layout stays native.
        """
        raw,_,meta=self.net.fetch(STATION_SCRIPT_URL,immutable=True)
        if hashlib.sha256(raw).hexdigest()!=STATION_SCRIPT_SHA256:
            raise ValidationError('The native Station script differs from the verified version. No unverified script was executed. Update Proxy Foundry before rendering Stations.')
        text=raw.decode('utf-8')
        original='eval(`${target} = value`);'
        if text.count(original)!=1:
            raise ValidationError('Unexpected native Station property-assignment format.')
        replacement=r"""const parts = target.replace(/\[(\d+)\]/g, '.$1').split('.');
            if (parts.shift() !== 'card' || parts.some(p => !/^[a-zA-Z0-9_]+$/.test(p) || ['__proto__','prototype','constructor'].includes(p))) throw new Error('Invalid Station property');
            const key = parts.pop(); let object = card;
            for (const part of parts) object = object[part];
            object[key] = value;"""
        text=text.replace(original,replacement)
        with self.lock:self.requested['/js/frames/versionStation.js']={'url':STATION_SCRIPT_URL,'bytes':len(raw),'cache':meta.get('cache',False),'sha256':STATION_SCRIPT_SHA256,'adapter':'CSP-safe UI property assignment'}
        return text.encode(),'application/javascript'
    def cached(self,path):
        land_material=dual_land_rules.material(path)
        if land_material:return bool(self.net.store.cache_get(land_material[1]))
        token_material=classic_token_frame.material(path)
        if token_material:return bool(self.net.store.cache_get(token_material[1]))
        if '/proxy-foundry/' not in path:
            for repo,commit,prefix in ((CC_REPO,CC_COMMIT,''),(COMPAT_REPO,COMPAT_COMMIT,'/public')):
                url='https://raw.githubusercontent.com/'+repo+'/'+commit+prefix+quote(path,safe='/')
                if self.net.store.cache_get(url):return True
        return False

    def ensure(self,path):
        """Warm immutable files without reading their already cached bodies back into Python."""
        path=self.path(path)
        if self.cached(path):return
        self.fetch(path)

    def fetch(self,path):
        path=self.path(path)
        short_token=re.fullmatch(r'/img/frames/proxy-foundry/token-short/frame([WUBRGMALC])\.png',path)
        if short_token:
            raw=(Path(__file__).resolve().parents[1]/'assets/token-short'/('frame'+short_token[1]+'.png')).read_bytes()
            with self.lock:self.requested[path]={'bytes':len(raw),'adapter':'Bundled native Short token frame components'}
            return raw,'image/png'
        land_material=dual_land_rules.material(path)
        if land_material:
            source,key,code=land_material
            with self.lock:asset_lock=self.derived_locks.setdefault(key,threading.Lock())
            with asset_lock:
                cached=self.net.store.cache_get(key)
                if cached:raw=self.net.store.asset_path(cached['asset_id']).read_bytes()
                else:
                    raw=dual_land_rules.colored_rules_png(self.fetch(source)[0],code)
                    asset=self.net.store.add_asset(raw,'image/png');self.net.store.cache_put(key,asset,self.net.clock())
            with self.lock:self.requested[path]={'source':source,'bytes':len(raw),'cache':bool(cached),'adapter':'Stronger classic dual-land rules texture; alpha unchanged'}
            return raw,'image/png'
        token_material=classic_token_frame.material(path)
        if token_material:
            source,key=token_material
            with self.lock:asset_lock=self.derived_locks.setdefault(key,threading.Lock())
            with asset_lock:
                cached=self.net.store.cache_get(key)
                if cached:raw=self.net.store.asset_path(cached['asset_id']).read_bytes()
                else:
                    raw=classic_token_frame.desaturate_white_png(self.fetch(source)[0])
                    asset=self.net.store.add_asset(raw,'image/png');self.net.store.cache_put(key,asset,self.net.clock())
            with self.lock:self.requested[path]={'source':source,'bytes':len(raw),'cache':bool(cached),'adapter':'Desaturated native white classic token; alpha unchanged'}
            return raw,'image/png'
        saga_back=re.fullmatch(re.escape(SAGA_PREFIX)+r'back-(left|right)-([WUBRGMAL])\.png',path)
        if saga_back:
            side,code=saga_back.groups()
            source='/img/frames/saga/regular/'+('l.png' if code=='L' else f'sagaFrame{code}.png')
            header=f'/img/frames/m15/transform/regular/{"new/" if side=="right" else ""}back{code}.png'
            key=f'derived:{CC_COMMIT}:saga-back-v{SAGA_VERSION}:{side}:{code}'
            with self.lock:asset_lock=self.derived_locks.setdefault(key,threading.Lock())
            with asset_lock:
                cached=self.net.store.cache_get(key)
                if cached:raw=self.net.store.asset_path(cached['asset_id']).read_bytes()
                else:
                    original,_=self.fetch(source);back,_=self.fetch(header)
                    mask,_=self.fetch('/img/frames/saga/sagaMaskType.png')
                    raw=transform_back_png(original,back,mask)
                    asset=self.net.store.add_asset(raw,'image/png');self.net.store.cache_put(key,asset,self.net.clock())
            with self.lock:self.requested[path]={'source':source,'bytes':len(raw),'cache':bool(cached),'adapter':'Native transform Saga back header and type bar'}
            return raw,'image/png'
        if re.fullmatch(re.escape(DEVOID_PREFIX)+r'm15DevoidFrame[WUBRGMAL]\.png',path):
            source='/img/frames/m15/devoid/'+path.rsplit('/',1)[-1]
            key=f'derived:{CC_COMMIT}:devoid-header-v{DEVOID_VERSION}:{source}'
            with self.lock:asset_lock=self.derived_locks.setdefault(key,threading.Lock())
            with asset_lock:
                cached=self.net.store.cache_get(key)
                if cached:raw=self.net.store.asset_path(cached['asset_id']).read_bytes()
                else:
                    original,_=self.fetch(source)
                    white=original if source.endswith('FrameW.png') else self.fetch('/img/frames/m15/devoid/m15DevoidFrameW.png')[0]
                    mask,_=self.fetch('/img/frames/m15/regular/m15MaskFrame.png')
                    raw=transparent_header_png(original,white,mask)
                    asset=self.net.store.add_asset(raw,'image/png');self.net.store.cache_put(key,asset,self.net.clock())
            with self.lock:self.requested[path]={'source':source,'bytes':len(raw),'cache':bool(cached),'adapter':'Transparent Devoid header gaps'}
            return raw,'image/png'
        if path=='/img/manaSymbols/infinity.svg':
            source='/img/manaSymbols/inf.svg';original,_=self.fetch(source)
            root=ElementTree.fromstring(original)
            circles=root.findall('.//{http://www.w3.org/2000/svg}circle')
            if len(circles)!=1:raise ValidationError('Pinned infinity symbol changed unexpectedly.')
            #Reuse the genuine infinity glyph, without its generic-mana disc.
            for parent in root.iter():
                if circles[0] in list(parent):parent.remove(circles[0])
            root.set('width','520');root.set('height','240');root.set('viewBox','40 180 520 240')
            raw=ElementTree.tostring(root,encoding='utf-8')
            with self.lock:self.requested[path]={'source':source,'bytes':len(raw),'adapter':'Text-colored infinity glyph without a mana disc'}
            return raw,'image/svg+xml'
        if path=='/img/frames/proxy-foundry/emblem/frame-no-symbol.png':
            source='/img/frames/token/regular/frameC.png'
            cache_key=f'derived:{CC_COMMIT}:emblem-no-symbol-v1:{path}'
            with self.lock:asset_lock=self.derived_locks.setdefault(cache_key,threading.Lock())
            with asset_lock:
                cached=self.net.store.cache_get(cache_key)
                if cached:raw=self.net.store.asset_path(cached['asset_id']).read_bytes()
                else:
                    original,_=self.fetch(source)
                    with Image.open(io.BytesIO(original)) as image:
                        image=image.convert('RGBA');width,height=image.size
                        #The plain neutral pack shares the emblem bars. Move its
                        #lower panel down to emblem coordinates, shortening only
                        #the uniform rules-box middle so the bottom stays fixed.
                        top=round(.60*height);middle=round(.80*height);shift=round(.03*height)
                        result=image.copy();result.paste((0,0,0,0),(0,top,width,middle+shift))
                        result.paste(image.crop((0,top,width,middle)),(0,top+shift))
                        output=io.BytesIO();result.save(output,'PNG');raw=output.getvalue()
                    asset=self.net.store.add_asset(raw,'image/png');self.net.store.cache_put(cache_key,asset,self.net.clock())
            with self.lock:self.requested[path]={'source':source,'bytes':len(raw),'cache':bool(cached),'adapter':'Neutral emblem bars and rules panel; no emblem-symbol overlay'}
            return raw,'image/png'
        if path==PW_PREFIX+'MaskPinlineNickname.png':
            cache_key=f'derived:{CC_REPO}:{CC_COMMIT}:{PINLINE_VERSION}:{path}'
            with self.lock:asset_lock=self.derived_locks.setdefault(cache_key,threading.Lock())
            with asset_lock:
                cached=self.net.store.cache_get(cache_key)
                if cached:raw=self.net.store.asset_path(cached['asset_id']).read_bytes()
                else:
                    frame,_=self.fetch('/img/frames/planeswalker/nickname/planeswalkerNicknameFrameM.png')
                    pinline,_=self.fetch('/img/frames/planeswalker/regular/planeswalkerMaskPinline.png')
                    loyalty,_=self.fetch('/img/frames/planeswalker/maskLoyalty.png')
                    raw=nickname_pinline_png(frame,pinline,loyalty)
                    asset=self.net.store.add_asset(raw,'image/png');self.net.store.cache_put(cache_key,asset,self.net.clock())
            with self.lock:self.requested[path]={'bytes':len(raw),'cache':bool(cached),'adapter':'Nickname-frame pinline alpha; art rails and loyalty badge excluded'}
            return raw,'image/png'
        if path in {PW_PREFIX+'MaskPinlineRegular.png',PW_PREFIX+'MaskPinlineClassicTall.png'}:
            source=('/img/frames/planeswalker/regular/planeswalkerMaskPinline.png' if path.endswith('Regular.png')
                    else '/img/frames/planeswalker/tall/planeswalkerTallMaskPinline.png')
            cache_key=f'derived:{CC_COMMIT}:{CLASSIC_PINLINE_VERSION}:{path}'
            with self.lock:asset_lock=self.derived_locks.setdefault(cache_key,threading.Lock())
            with asset_lock:
                cached=self.net.store.cache_get(cache_key)
                if cached:raw=self.net.store.asset_path(cached['asset_id']).read_bytes()
                else:
                    pinline,_=self.fetch(source);badge,_=self.fetch('/img/frames/planeswalker/maskLoyalty.png')
                    type_bar,_=self.fetch(source.replace('MaskPinline.png','MaskType.png'))
                    raw=pinline_without_loyalty_png(pinline,badge,type_bar)
                    asset=self.net.store.add_asset(raw,'image/png');self.net.store.cache_put(cache_key,asset,self.net.clock())
            with self.lock:self.requested[path]={'source':source,'bytes':len(raw),'cache':bool(cached),'adapter':'Native planeswalker pinline excluding the loyalty badge and type-bar rim'}
            return raw,'image/png'
        tall_pw=re.fullmatch(re.escape(PW_PREFIX)+r'(FrameTall([WUBRGMAL])|Mask(Pinline|Type)Tall|textTall)\.(png|svg)',path)
        if tall_pw:
            if tall_pw[2]:source='/img/frames/planeswalker/nickname/planeswalkerNicknameFrame'+tall_pw[2]+'.png'
            elif tall_pw[3]=='Pinline':source=PW_PREFIX+'MaskPinlineNickname.png'
            elif tall_pw[3]:source='/img/frames/planeswalker/regular/planeswalkerMask'+tall_pw[3]+'.png'
            else:source='/img/frames/planeswalker/text.svg'
            cache_key=f'derived:{CC_REPO}:{CC_COMMIT}:{TALL_VERSION}{PINLINE_VERSION if tall_pw[3]=="Pinline" else ""}:{path}'
            with self.lock:asset_lock=self.derived_locks.setdefault(cache_key,threading.Lock())
            with asset_lock:
                cached=self.net.store.cache_get(cache_key)
                if cached:raw=self.net.store.asset_path(cached['asset_id']).read_bytes()
                else:
                    original,_=self.fetch(source)
                    raw=extend_rules_svg(original) if source.endswith('.svg') else extend_rules_png(original)
                    asset=self.net.store.add_asset(raw,'image/svg+xml' if source.endswith('.svg') else 'image/png')
                    self.net.store.cache_put(cache_key,asset,self.net.clock())
            with self.lock:self.requested[path]={'source':source,'bytes':len(raw),'cache':bool(cached),'adapter':'Native planeswalker rules-box middle repeated; borders retain their pixel thickness'}
            return raw,'image/svg+xml' if path.endswith('.svg') else 'image/png'
        colored=re.fullmatch(r'/img/frames/proxy-foundry/transform/(TitleColored|CrownJoinedColored)([WUBRGMAL])\.png',path)
        if colored:
            kind,code=colored.groups();joined=kind=='CrownJoinedColored'
            cache_key=f'derived:{CC_COMMIT}:{DFC_MATERIAL_VERSION}:{path}'
            if not joined:cache_key+=':'+TITLE_BAR_VERSION
            with self.lock:asset_lock=self.derived_locks.setdefault(cache_key,threading.Lock())
            with asset_lock:
                cached=self.net.store.cache_get(cache_key)
                if cached:raw=self.net.store.asset_path(cached['asset_id']).read_bytes()
                else:
                    header,_=self.fetch('/img/frames/proxy-foundry/godzilla/'+('CrownJoined' if joined else 'Title')+code+'.png')
                    back,_=self.fetch('/img/frames/m15/transform/regular/back'+code+'.png')
                    raw=color_title_png(header,back,joined_crown=joined)
                    asset=self.net.store.add_asset(raw,'image/png');self.net.store.cache_put(cache_key,asset,self.net.clock())
            with self.lock:self.requested[path]={'bytes':len(raw),'cache':bool(cached),'adapter':'Native Godzilla title geometry with colored reverse-face material'}
            return raw,'image/png'
        floating=re.fullmatch(r'/img/frames/proxy-foundry/transform/CrownFloatingBack([WUBRGMAL])\.png',path)
        if floating:
            cache_key=f'derived:{CC_COMMIT}:{BACK_VERSION}:{path}'
            with self.lock:asset_lock=self.derived_locks.setdefault(cache_key,threading.Lock())
            with asset_lock:
                cached=self.net.store.cache_get(cache_key)
                if cached:raw=self.net.store.asset_path(cached['asset_id']).read_bytes()
                else:
                    original,_=self.fetch('/img/frames/m15/transform/crowns/floating/'+floating[1].lower()+'.png')
                    raw=mirror_header_png(original);asset=self.net.store.add_asset(raw,'image/png')
                    self.net.store.cache_put(cache_key,asset,self.net.clock())
            with self.lock:self.requested[path]={'bytes':len(raw),'cache':bool(cached),'adapter':'Native floating crown with right-side circular opening'}
            return raw,'image/png'
        right_header=re.fullmatch(r'/img/frames/proxy-foundry/transform/(CrownJoinedBack([WUBRGMAL])|TitlePinlineBack([WUBRGMAL])|TitleOutlineBack)\.png',path)
        if right_header:
            if right_header[2]:source='/img/frames/proxy-foundry/transform/CrownJoined'+right_header[2]+'.png'
            elif right_header[3]:source='/img/frames/proxy-foundry/werewolf/TitlePinline'+right_header[3]+'.png'
            else:source='/img/frames/proxy-foundry/werewolf/TitleOutline.png'
            cache_key=f'derived:{CC_REPO}:{CC_COMMIT}:{BEVEL_VERSION}:{BACK_VERSION}:{path}'
            with self.lock:asset_lock=self.derived_locks.setdefault(cache_key,threading.Lock())
            with asset_lock:
                cached=self.net.store.cache_get(cache_key)
                if cached:raw=self.net.store.asset_path(cached['asset_id']).read_bytes()
                else:
                    original,_=self.fetch(source);raw=mirror_header_png(original)
                    asset=self.net.store.add_asset(raw,'image/png')
                    self.net.store.cache_put(cache_key,asset,self.net.clock())
            with self.lock:self.requested[path]={'source':source,'bytes':len(raw),'cache':bool(cached),'adapter':'Right-side back-face marker opening; native material preserved'}
            return raw,'image/png'
        bevel=re.fullmatch(r'/img/frames/proxy-foundry/transform/CrownJoined([WUBRGMAL])\.png',path)
        if bevel:
            code=bevel[1]
            cache_key=f'derived:{CC_REPO}:{CC_COMMIT}:{BEVEL_VERSION}:{path}'
            with self.lock:asset_lock=self.derived_locks.setdefault(cache_key,threading.Lock())
            with asset_lock:
                cached=self.net.store.cache_get(cache_key)
                if cached:
                    raw=self.net.store.asset_path(cached['asset_id']).read_bytes()
                else:
                    transform,_=self.fetch('/img/frames/m15/transform/crowns/nickname/'+code.lower()+'.png')
                    godzilla,_=self.fetch('/img/frames/m15/nickname/m15NicknameCrown'+code+'.png')
                    raw=restore_crown_bevel(transform,godzilla)
                    asset=self.net.store.add_asset(raw,'image/png')
                    self.net.store.cache_put(cache_key,asset,self.net.clock())
            with self.lock:self.requested[path]={'bytes':len(raw),'cache':bool(cached),'adapter':'Native Godzilla bevel on unchanged transform crown geometry'}
            return raw,'image/png'
        artifact_gray=re.fullmatch(r'/img/frames/proxy-foundry/godzilla/gray-artifact/(Frame|Title|TitleJoined|Crown|CrownJoined|TitleColored|CrownJoinedColored|TransformCrownFloating(?:Back)?|TransformCrownJoined(?:Back)?)\.png',path)
        if artifact_gray:
            with self.lock:
                if self.artifact_frames is None:self.artifact_frames=ArtifactFrameCache(self.net.store)
            kind=artifact_gray[1]
            source=('/img/frames/m15/nickname/m15NicknameFrameA.png' if kind=='Frame'
                    else '/img/frames/proxy-foundry/transform/CrownJoinedA.png' if kind=='TransformCrownJoined'
                    else '/img/frames/proxy-foundry/transform/CrownJoinedBackA.png' if kind=='TransformCrownJoinedBack'
                    else '/img/frames/proxy-foundry/transform/'+kind+'A.png' if kind in {'TitleColored','CrownJoinedColored'}
                    else '/img/frames/m15/transform/crowns/floating/a.png' if kind=='TransformCrownFloating'
                    else '/img/frames/proxy-foundry/transform/CrownFloatingBackA.png' if kind=='TransformCrownFloatingBack'
                    else f'/img/frames/proxy-foundry/godzilla/{kind}A.png')
            raw,cached=self.artifact_frames.fetch(source,self.fetch)
            with self.lock:self.requested[path]={'source':source,'bytes':len(raw),'cache':cached,'adapter':'Procedural neutral artifact gray; alpha unchanged'}
            return raw,'image/png'
        addon=re.fullmatch(r'/img/frames/proxy-foundry/land-addons/(TrueNameNoOuter[WUBRGMAL]|BasicTrueName[WUBRG])\.png',path)
        if addon:
            raw=(Path(__file__).resolve().parents[1]/'assets/land-addons'/(addon[1]+'.png')).read_bytes()
            return raw,'image/png'
        if path=='/img/frames/proxy-foundry/land-addons/original-dual-type.svg':
            import xml.etree.ElementTree as ET
            raw,_=self.fetch('/img/frames/textless/basics/type.svg')
            svg=ET.fromstring(raw)
            shape=next(element for element in svg.iter() if element.tag.endswith('}path'))
            # The native type fill is inset 0.48 SVG units from the pinline.
            # Restore the clipped native edge, with half a rendered pixel of
            # overlap to avoid an antialiasing seam (viewBox width is 180).
            shape.set('stroke','#ffffff');shape.set('stroke-width','1.06')
            shape.set('stroke-linejoin','round')
            return ET.tostring(svg),'image/svg+xml'
        if path=='/img/frames/proxy-foundry/compact-land/lower-pinline.svg':
            import xml.etree.ElementTree as ET
            raw,_=self.fetch('/img/frames/m15/boxTopper/short/pinline.svg')
            svg=ET.fromstring(raw)
            shape=next(element for element in svg.iter() if element.tag.endswith('}path'))
            original=shape.get('d')
            if 'M105.672,232.739' not in original:raise ValidationError('Pinned compact land pinline changed.')
            shape.set('d',original.split('M105.672,232.739')[0])
            return ET.tostring(svg),'image/svg+xml'
        compact=re.fullmatch(r'/img/frames/proxy-foundry/compact-land/(TrueName[WUBRGMAL]|Title[WUBRGMAL]|TitleBlack[WUBRGMAL]?|CrownJoinedBlack[WUBRGMAL]|CrownFloatingOuter[WUBRGMALC]|TitleCut[WUBRGMAL]|CrownOutline|CrownOuterOutline|CrownHeaderOutline|PinlineFade)\.png',path)
        if compact:
            raw=(Path(__file__).resolve().parents[1]/'assets/compact-land'/(compact[1]+'.png')).read_bytes()
            with self.lock:self.requested[path]={'bytes':len(raw),'adapter':'Bundled approved compact land header'}
            return raw,'image/png'
        werewolf=re.fullmatch(r'/img/frames/proxy-foundry/werewolf/(TitlePinline[WUBRGMAL]|TitleOutline|IconRing|LowerMask)\.png',path)
        if werewolf:
            if werewolf[1]=='IconRing':
                cache_key=f'derived:{CC_COMMIT}:{ICON_RING_VERSION}:{path}'
                with self.lock:asset_lock=self.derived_locks.setdefault(cache_key,threading.Lock())
                with asset_lock:
                    cached=self.net.store.cache_get(cache_key)
                    if cached:raw=self.net.store.asset_path(cached['asset_id']).read_bytes()
                    else:
                        original=(Path(__file__).resolve().parents[1]/'assets/werewolf/IconRing.png').read_bytes()
                        raw=neutralize_icon_surround(original)
                        asset=self.net.store.add_asset(raw,'image/png')
                        self.net.store.cache_put(cache_key,asset,self.net.clock())
                with self.lock:self.requested[path]={'bytes':len(raw),'cache':bool(cached),'adapter':'Neutral native icon surround; shading and alpha preserved'}
                return raw,'image/png'
            raw=(Path(__file__).resolve().parents[1]/'assets/werewolf'/(werewolf[1]+'.png')).read_bytes()
            with self.lock:self.requested[path]={'bytes':len(raw),'adapter':'Bundled approved Werewolf header'}
            return raw,'image/png'
        if path.startswith(PINLINE_MASK_PREFIX) and path[len(PINLINE_MASK_PREFIX):] in PINLINE_OUTLINE_FILES:
            raw=(Path(__file__).resolve().parents[1]/'assets/frame-masks'/path[len(PINLINE_MASK_PREFIX):]).read_bytes()
            with self.lock:self.requested[path]={'bytes':len(raw),'adapter':'Bundled native black outlines above the two-color pinline'}
            return raw,'image/png'
        mask=re.fullmatch(r'/img/frames/proxy-foundry/masks/(class|saga|creature-saga)-pinline\.png',path)
        if mask:
            raw=(Path(__file__).resolve().parents[1]/'assets/frame-masks'/(mask[1]+'-pinline.png')).read_bytes()
            with self.lock:self.requested[path]={'bytes':len(raw),'adapter':'Bundled pinline color mask preserving native black outlines'}
            return raw,'image/png'
        if path in {'/img/frames/proxy-foundry/land-name-neutral.png','/img/frames/proxy-foundry/land-name-color-mask.png'}:
            source_path='/img/frames/m15/nickname/addons/m15NicknameTitleW.png'
            raw,_=self.fetch(source_path)
            with Image.open(io.BytesIO(raw)) as source:
                source=source.convert('RGBA')
                alpha=source.getchannel('A')
                image=Image.new('RGBA',source.size,(0,0,0,0))
                if path.endswith('color-mask.png'):
                    # White-strip luminance retains its antialiased/shaded edge;
                    # black outline and translucent black interior are excluded.
                    coverage=source.getchannel('R').point(lambda value:min(255,round(value*255/252)))
                    alpha=ImageChops.multiply(alpha,coverage)
                image.putalpha(alpha)
                output=io.BytesIO();image.save(output,'PNG')
            with self.lock:self.requested[path]={'source':source_path,'bytes':len(output.getvalue()),'adapter':'True-name geometry with independent title rim paint'}
            return output.getvalue(),'image/png'
        if path=='/img/frames/proxy-foundry/land-name-outline-8.png':
            raw,_=self.fetch('/img/frames/m15/nickname/addons/m15NicknameTitleW.png')
            with Image.open(io.BytesIO(raw)) as source:
                # The native strip has a four-pixel black edge at 1352px wide.
                # Match the land SVG's 8/1000 stroke, keeping its translucent fill.
                radius=7
                alpha=source.convert('RGBA').getchannel('A').point(lambda value:255 if value>=250 else 0)
                alpha.paste(0,(0,0,source.width,148))
                mask=Image.new('L',(source.width+2*radius,source.height+2*radius))
                mask.paste(alpha,(radius,radius));mask=mask.filter(ImageFilter.MaxFilter(radius*2+1))
                mask.paste(0,(0,0,mask.width,148+radius))
                image=Image.new('RGBA',mask.size,(4,6,5,0));image.putalpha(mask)
                output=io.BytesIO();image.save(output,'PNG')
            return output.getvalue(),'image/png'
        match=re.fullmatch(r'/img/frames/proxy-foundry/godzilla/(Title|TitleJoined|Crown|CrownJoined)([WUBRGMAL])\.png',path)
        if match:
            kind,code=match.groups()
            version=TITLE_BAR_VERSION if kind=='Title' else 'godzilla-separated-v1'
            cache_key=f'derived:{CC_COMMIT}:{version}:{path}'
            store=getattr(self.net,'store',None)
            cached=store.cache_get(cache_key) if store and not kind.endswith('Joined') else None
            if cached:return self.net.store.asset_path(cached['asset_id']).read_bytes(),'image/png'
            source=f'/img/frames/m15/nickname/m15Nickname{kind.removesuffix("Joined")}{code}.png'
            raw,_=self.fetch(source)
            if kind.endswith('Joined'):
                with self.lock:self.requested[path]={'source':source,'bytes':len(raw),'adapter':'Native joined Godzilla title/crown and real-name strip'}
                return raw,'image/png'
            # Preserve the crown shoulders below the main bar. A rectangular
            # crop cuts through their outer black outline.
            height,original=(TITLE_BAR_HEIGHT,TITLE_JOINED_HEIGHT) if kind=='Title' else (.1286,.1286)
            with Image.open(io.BytesIO(raw)) as image:
                if kind=='Crown':
                    image=image.convert('RGBA')
                    width,total=image.size
                    # Coordinates belong to the pinned 1428 x 270 crown asset.
                    # Remove the attached subtitle inside the two shoulders.
                    mask=Image.new('L',image.size,255)
                    draw=ImageDraw.Draw(mask)
                    points=[(134,194),(1294,194),(1282,226),(1428,226),
                            (1428,270),(0,270),(0,226),(146,226)]
                    draw.polygon([(round(x*width/1428),round(y*total/270)) for x,y in points],fill=0)
                    image.putalpha(ImageChops.multiply(image.getchannel('A'),mask))
                    # Close the newly separated edge, including the inner
                    # shoulder cuts, with the native outline thickness.
                    edge=[(146,224),(134,194),(1294,194),(1282,224)]
                    ImageDraw.Draw(image).line([(round(x*width/1428),round(y*total/270)) for x,y in edge],fill=(0,0,0,255),width=max(1,round(4*width/1428)))
                else:
                    image=image.crop((0,0,image.width,round(image.height*height/original)))
                    # The joined asset leaves gaps where the subtitle attaches.
                    # Mirror its native top stroke to close the detached bottom.
                    stroke=max(1,round(4*image.width/1352))
                    edge=image.crop((0,0,image.width,stroke)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                    image.paste(edge,(0,image.height-stroke))
                output=io.BytesIO();image.save(output,'PNG')
            if store:
                asset=store.add_asset(output.getvalue(),'image/png');store.cache_put(cache_key,asset,self.net.clock())
            with self.lock:self.requested[path]={'source':source,'bytes':len(output.getvalue()),'adapter':'Godzilla main title without real-name strip'}
            return output.getvalue(),'image/png'
        if path=='/js/creator-23.js':return self.creator_script()
        if path=='/js/frames/versionStation.js':return self.station_script()
        # The hidden native frame picker does not need its thumbnail catalogue.
        if re.search(r'Thumb\.png$',path,re.I):
            b=io.BytesIO();Image.new('RGBA',(1,1),(0,0,0,0)).save(b,'PNG');return b.getvalue(),'image/png'
        url='https://raw.githubusercontent.com/'+CC_REPO+'/'+CC_COMMIT+quote(path,safe='/')
        try:raw,mime,meta=self.net.fetch(url,immutable=True)
        except Exception as original:
            # Pyodide's browser transport raises JsException for HTTP failures,
            # while the local transport raises ValidationError. Both can report
            # the same pinned-image 404 that the compatibility snapshot fills.
            if not path.startswith('/img/') or 'HTTP 404' not in str(original):raise
            url='https://raw.githubusercontent.com/'+COMPAT_REPO+'/'+COMPAT_COMMIT+'/public'+quote(path,safe='/')
            try:raw,mime,meta=self.net.fetch(url,immutable=True)
            except Exception as compat_error:
                if path!=self.COLORLESS_SAGA_CREATURE_PATH or 'HTTP 404' not in str(compat_error):raise
                # CardConjurer's valid colorless Saga-creature layer is absent from
                # both older pinned snapshots. Fill only this known asset gap from
                # a newer CardConjurer fork pinned to an immutable commit.
                url='https://raw.githubusercontent.com/'+self.COLORLESS_SAGA_CREATURE_REPO+'/'+self.COLORLESS_SAGA_CREATURE_COMMIT+quote(path,safe='/')
                raw,mime,meta=self.net.fetch(url,immutable=True)
        if path=='/js/frames/versionPlaneswalker.js':raw=planeswalker_renderer_script(raw)
        if path=='/js/frames/versionClass.js':
            text=raw.decode('utf-8')
            anchor="card.text['level' + i + 'c'].height = height || 1;"
            if text.count(anchor)!=1:
                raise ValidationError('Pinned Class renderer changed unexpectedly.')
            # Keep unused levels empty across repeated native input synchronization.
            raw=text.replace(anchor,"card.text['level' + i + 'c'].height = height || 0;").encode()
        mime={'.js':'application/javascript','.css':'text/css','.svg':'image/svg+xml','.ttf':'font/ttf','.otf':'font/otf','.woff':'font/woff','.woff2':'font/woff2'}.get('.'+path.rsplit('.',1)[-1].lower(),mimetypes.guess_type(path)[0] or mime)
        with self.lock:self.requested[path]={'url':url,'bytes':len(raw),'cache':meta.get('cache',False)}
        return raw,mime
    def prepare(self,progress=lambda *a:None,cancel=lambda:False):
        steps=self.prepare_steps(progress,cancel)
        while True:
            try:next(steps)
            except StopIteration as finished:return finished.value

    def prepare_steps(self,progress=lambda *a:None,cancel=lambda:False):
        for i,p in enumerate(self.SOURCE_FILES):
            if cancel():raise ValidationError('Renderer preparation cancelled.')
            progress(i,len(self.SOURCE_FILES),'Loading pinned CardConjurer '+p.rsplit('/',1)[-1]);self.fetch(p)
            progress(i+1,len(self.SOURCE_FILES),'Loaded pinned CardConjurer '+p.rsplit('/',1)[-1])
            yield
        if cancel():raise ValidationError('Renderer preparation cancelled.')
        progress(len(self.SOURCE_FILES),len(self.SOURCE_FILES),'Native CardConjurer ready to start')
        return {'repository':CC_REPO,'commit':CC_COMMIT,'host':'/runtime/host'}
    def fonts_css(self):
        raw,_=self.fetch('/css/style-9.css');text=raw.decode('utf-8-sig')
        blocks=re.findall(r'@font-face\s*\{[^}]+\}',text,re.S)
        if not blocks:raise ValidationError('Pinned CardConjurer font definitions are missing.')
        out='\n'.join(blocks).replace('../fonts/','/fonts/')
        return out.encode()
    def host(self, worker=False):
        raw,_=self.fetch('/creator/index.html');creator=raw.decode('utf-8-sig')
        creator=re.sub(r'<script\b[\s\S]*?</script>','',creator,flags=re.I)
        creator=re.sub(r'<link\b[^>]*>','',creator,flags=re.I)
        page=('''<!doctype html><html><head><meta charset="utf-8"><title>Proxy Foundry native CardConjurer renderer</title>
<link rel="stylesheet" href="/runtime/fonts.css"><style>html,body{margin:0;background:#101216;color:#eee} .notification-container{display:none}.native-host{position:absolute;left:-12000px;top:0;width:1600px;opacity:0;pointer-events:none}</style>
<meta name="pf-parent-origin" content="''' + html.escape(getattr(self, 'parent_origin', ''), quote=True) + '''"><script src="/site/runtime-hooks.js"></script></head><body><div class="notification-container"></div><div class="native-host">'''+creator+'''</div><script src="/js/main-1.js"></script><script src="/js/creator-23.js"></script><script src="/site/runtime-bridge.js"></script></body></html>''')
        if worker:
            page=re.sub(r'<script\b[\s\S]*?</script>','',page,flags=re.I)
            page=page.replace('</body>','<script src="/site/runtime-worker-host.js"></script></body>')
        return page.encode()
    def diagnostic(self):
        with self.lock:return {'repository':CC_REPO,'commit':CC_COMMIT,'files':dict(self.requested),'count':len(self.requested),'bytes':sum(x['bytes'] for x in self.requested.values())}
