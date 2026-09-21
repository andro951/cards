"""On-demand pinned CardConjurer files. Never download or unpack a repository archive."""
from __future__ import annotations
import base64,html,io,json,mimetypes,re,threading,hashlib
from urllib.parse import quote,unquote,urlsplit
from PIL import Image
from .domain import ValidationError,CC_REPO,CC_COMMIT,COMPAT_REPO,COMPAT_COMMIT,STATION_SCRIPT_URL,STATION_SCRIPT_SHA256

class Runtime:
    SOURCE_FILES=('/creator/index.html','/js/main-1.js','/js/creator-23.js','/js/frames/groupStandard-3.js','/js/frames/packM15Regular-1.js','/css/style-9.css')
    COLORLESS_SAGA_CREATURE_PATH='/img/frames/saga/creature/c.png'
    COLORLESS_SAGA_CREATURE_REPO='joshbirnholz/cardconjurer'
    COLORLESS_SAGA_CREATURE_COMMIT='d3c6706692898d596ec6a5be0be44f63062c9e12'
    def __init__(self,network):self.net=network;self.requested={};self.lock=threading.Lock()
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
        if text.count(loop_anchor)!=1 or text.count(mana_anchor)!=1:
            raise ValidationError('Pinned CardConjurer text renderer changed unexpectedly; inline mana wrapping was not patched.')
        text=text.replace(loop_anchor,loop_replacement).replace(mana_anchor,mana_replacement)
        with self.lock:self.requested[path]={'url':url,'bytes':len(raw),'cache':meta.get('cache',False),'sha256':hashlib.sha256(raw).hexdigest(),'adapter':'inline mana cluster wrapping'}
        return text.encode(),'application/javascript'

    def station_script(self):
        """Use the real native Station module, pinned by content rather than a moving site version.

        The verified module is absent from the older GitHub runtime snapshots.
        Only its UI property assignment is made CSP-safe; drawing/layout stays native.
        """
        raw,mime,meta=self.net.fetch(STATION_SCRIPT_URL,immutable=True)
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
    def fetch(self,path):
        path=self.path(path)
        if path=='/js/creator-23.js':return self.creator_script()
        if path=='/js/frames/versionStation.js':return self.station_script()
        # The hidden native frame picker does not need its thumbnail catalogue.
        if re.search(r'Thumb\.png$',path,re.I):
            b=io.BytesIO();Image.new('RGBA',(1,1),(0,0,0,0)).save(b,'PNG');return b.getvalue(),'image/png'
        url='https://raw.githubusercontent.com/'+CC_REPO+'/'+CC_COMMIT+quote(path,safe='/')
        try:raw,mime,meta=self.net.fetch(url,immutable=True)
        except ValidationError as original:
            if not path.startswith('/img/') or 'HTTP 404' not in str(original):raise
            url='https://raw.githubusercontent.com/'+COMPAT_REPO+'/'+COMPAT_COMMIT+'/public'+quote(path,safe='/')
            try:raw,mime,meta=self.net.fetch(url,immutable=True)
            except ValidationError as compat_error:
                if path!=self.COLORLESS_SAGA_CREATURE_PATH or 'HTTP 404' not in str(compat_error):raise
                # CardConjurer's valid colorless Saga-creature layer is absent from
                # both older pinned snapshots. Fill only this known asset gap from
                # a newer CardConjurer fork pinned to an immutable commit.
                url='https://raw.githubusercontent.com/'+self.COLORLESS_SAGA_CREATURE_REPO+'/'+self.COLORLESS_SAGA_CREATURE_COMMIT+quote(path,safe='/')
                raw,mime,meta=self.net.fetch(url,immutable=True)
        mime={'.js':'application/javascript','.css':'text/css','.svg':'image/svg+xml','.ttf':'font/ttf','.otf':'font/otf','.woff':'font/woff','.woff2':'font/woff2'}.get('.'+path.rsplit('.',1)[-1].lower(),mimetypes.guess_type(path)[0] or mime)
        with self.lock:self.requested[path]={'url':url,'bytes':len(raw),'cache':meta.get('cache',False)}
        return raw,mime
    def prepare(self,progress=lambda *a:None,cancel=lambda:False):
        for i,p in enumerate(self.SOURCE_FILES):
            if cancel():raise ValidationError('Renderer preparation cancelled.')
            progress(i,len(self.SOURCE_FILES),'Loading pinned CardConjurer '+p.rsplit('/',1)[-1]);self.fetch(p)
        progress(len(self.SOURCE_FILES),len(self.SOURCE_FILES),'Native CardConjurer ready to start')
        return {'repository':CC_REPO,'commit':CC_COMMIT,'host':'/runtime/host'}
    def fonts_css(self):
        raw,_=self.fetch('/css/style-9.css');text=raw.decode('utf-8-sig')
        blocks=re.findall(r'@font-face\s*\{[^}]+\}',text,re.S)
        if not blocks:raise ValidationError('Pinned CardConjurer font definitions are missing.')
        out='\n'.join(blocks).replace('../fonts/','/fonts/')
        return out.encode()
    def host(self):
        raw,_=self.fetch('/creator/index.html');creator=raw.decode('utf-8-sig')
        creator=re.sub(r'<script\b[\s\S]*?</script>','',creator,flags=re.I)
        creator=re.sub(r'<link\b[^>]*>','',creator,flags=re.I)
        return ('''<!doctype html><html><head><meta charset="utf-8"><title>Proxy Foundry native CardConjurer renderer</title>
<link rel="stylesheet" href="/runtime/fonts.css"><style>html,body{margin:0;background:#101216;color:#eee} .notification-container{display:none}.native-host{position:absolute;left:-12000px;top:0;width:1600px;opacity:0;pointer-events:none}</style>
<meta name="pf-parent-origin" content="''' + html.escape(getattr(self, 'parent_origin', ''), quote=True) + '''"><script src="/site/runtime-hooks.js"></script></head><body><div class="notification-container"></div><div class="native-host">'''+creator+'''</div><script src="/js/main-1.js"></script><script src="/js/creator-23.js"></script><script src="/site/runtime-bridge.js"></script></body></html>''').encode()
    def diagnostic(self):
        with self.lock:return {'repository':CC_REPO,'commit':CC_COMMIT,'files':dict(self.requested),'count':len(self.requested),'bytes':sum(x['bytes'] for x in self.requested.values())}
