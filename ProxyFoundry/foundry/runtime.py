"""On-demand pinned CardConjurer files. Never download or unpack a repository archive."""
from __future__ import annotations
import base64,html,io,json,mimetypes,re,threading
from urllib.parse import quote,unquote
from PIL import Image
from .domain import ValidationError,CC_REPO,CC_COMMIT,COMPAT_REPO,COMPAT_COMMIT

class Runtime:
    SOURCE_FILES=('/creator/index.html','/js/main-1.js','/js/creator-23.js','/js/frames/groupStandard-3.js','/js/frames/packM15Regular-1.js','/css/style-9.css')
    def __init__(self,network):self.net=network;self.requested={};self.lock=threading.Lock()
    @staticmethod
    def path(raw):
        p=unquote(str(raw)).split('?',1)[0]
        if not p.startswith(('/js/','/img/','/fonts/','/css/','/creator/')) or any(x in {'.','..'} for x in p.split('/')) or '\\' in p or '\x00' in p:
            raise ValidationError('Invalid CardConjurer dependency path.')
        return p
    def fetch(self,path):
        path=self.path(path)
        # The hidden native frame picker does not need its thumbnail catalogue.
        if re.search(r'Thumb\.png$',path,re.I):
            b=io.BytesIO();Image.new('RGBA',(1,1),(0,0,0,0)).save(b,'PNG');return b.getvalue(),'image/png'
        url='https://raw.githubusercontent.com/'+CC_REPO+'/'+CC_COMMIT+quote(path,safe='/')
        try:raw,mime,meta=self.net.fetch(url,immutable=True)
        except ValidationError as original:
            if not path.startswith('/img/') or 'HTTP 404' not in str(original):raise
            url='https://raw.githubusercontent.com/'+COMPAT_REPO+'/'+COMPAT_COMMIT+'/public'+quote(path,safe='/')
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
