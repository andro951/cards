"""On-demand pinned CardConjurer files. Never download or unpack a repository archive."""
from __future__ import annotations
import base64,html,io,json,mimetypes,re,threading,hashlib
from pathlib import Path
from urllib.parse import quote,unquote,urlsplit
from PIL import Image,ImageDraw,ImageChops,ImageFilter
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
    def fetch(self,path):
        path=self.path(path)
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
        compact=re.fullmatch(r'/img/frames/proxy-foundry/compact-land/(TrueName[WUBRGMAL]|Title[WUBRGMAL]|TitleCut[WUBRGMAL]|CrownOutline)\.png',path)
        if compact:
            raw=(Path(__file__).resolve().parents[1]/'assets/compact-land'/(compact[1]+'.png')).read_bytes()
            with self.lock:self.requested[path]={'bytes':len(raw),'adapter':'Bundled approved compact land header'}
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
            source=f'/img/frames/m15/nickname/m15Nickname{kind.removesuffix("Joined")}{code}.png'
            raw,_=self.fetch(source)
            if kind.endswith('Joined'):
                with self.lock:self.requested[path]={'source':source,'bytes':len(raw),'adapter':'Native joined Godzilla title/crown and real-name strip'}
                return raw,'image/png'
            # Preserve the crown shoulders below the main bar. A rectangular
            # crop cuts through their outer black outline.
            height,original=(.069,.1053) if kind=='Title' else (.1286,.1286)
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
                output=io.BytesIO();image.save(output,'PNG')
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
