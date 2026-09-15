"""Deck orchestration. Source changes invalidate front renders; backs/quantities do not."""
from __future__ import annotations
import base64,copy,io,json,re,time,zipfile
from pathlib import PurePosixPath
from PIL import Image
from .domain import *
from .storage import Store
from .network import Network
from .images import ingest_image,data_uri,decode_image,rarity_variants
from .sources import Sources
from .compiler import Compiler,BUILTINS,SINGLE_SURFACE
from .legacy import ingest,compiler as native,tokens

DEFAULT_SETTINGS={'source':{'mode':'scryfall','githubFolder':'','ref':'','localFiles':{},'fallback':True},'symbols':{},'artist':'','backAsset':None,'templateRules':{},'useLandLibrary':False,'landLibrary':'','disableAutofit':False,'refreshData':False,'flavorPolicy':'auto','acceptCropWarnings':False,'acceptLayoutWarnings':False}
FRONT_SETTINGS={'source','symbols','artist','templateRules','useLandLibrary','landLibrary','disableAutofit','flavorPolicy'}
class Workspace:
    def __init__(self,store=None,network=None):
        self.store=store or Store();self.net=network or Network(self.store);self.sources=Sources(self.net);self.compiler=Compiler(self.store)
    def new_deck(self, name='Untitled deck'):
        return self.store.put('decks', {'name':str(name).strip()[:200] or 'Untitled deck',
            'cards':[], 'settings':self.validate_settings(self.global_settings().get('defaults',{})),
            'status':'draft', 'notes':'', 'importedSource':''})
    def global_settings(self):return self.store.get('settings','global') or {'id':'global','refreshData':False,'landLibrary':'','defaults':{}}
    def set_global_settings(self,values):
        old=self.global_settings();safe={k:v for k,v in values.items() if k in {'refreshData','landLibrary','defaults'}}
        if safe.get('landLibrary'):github_location(safe['landLibrary'])
        if 'defaults' in safe and safe['defaults']:
            safe['defaults']=self.validate_settings(safe['defaults'])
        return self.store.put('settings',{**old,**safe},values.get('revision'))
    def validate_settings(self,settings):
        s={**copy.deepcopy(DEFAULT_SETTINGS),**settings};s['source']={**DEFAULT_SETTINGS['source'],**s.get('source',{})}
        if s['source']['mode'] not in {'scryfall','github','local'}:raise ValidationError('Select Scryfall, GitHub folder, or Computer folder.')
        if s['source']['mode']=='github' and s['source'].get('githubFolder'):github_location(s['source']['githubFolder'],s['source'].get('ref') or None)
        for ident in [s.get('backAsset'),*s.get('symbols',{}).values(),*s['source'].get('localFiles',{}).values()]:
            if ident and not self.store.asset(ident):raise ValidationError('A selected uploaded image is missing.')
        if len(s['source'].get('localFiles',{}))>5000:raise ValidationError('Select at most 5,000 local art files.')
        if s.get('flavorPolicy') not in {'auto','resolved','latest'}:raise ValidationError('Choose an automatic, selected-printing or latest-printing flavor policy.')
        if len(str(s.get('artist','')))>300:raise ValidationError('Artist credit is too long.')
        for group,choice in s.get('templateRules',{}).items():
            if group not in GROUP_LABELS:raise ValidationError('Unknown template group '+str(group))
            if choice not in {t['id'] for t in BUILTINS} and not self.store.get('templates',choice):raise ValidationError('A selected custom template is missing.')
            if choice=='land' and group in {'legendary','legendary-land'}:raise ValidationError('Full-art land has no compatible crown.')
        return s
    def create(self,payload,progress=lambda *a:None,cancel=lambda:False):
        refresh=bool(payload.get('settings',{}).get('refreshData',self.global_settings().get('refreshData',False)))
        result=self.sources.import_deck(payload.get('source',''),payload.get('includeOutside',False),refresh,progress,cancel)
        if cancel():raise ValidationError('Import cancelled.')
        name=str(payload.get('name') or result['name']).strip()[:200] or 'Untitled deck'
        settings=self.validate_settings({**self.global_settings().get('defaults',{}),**payload.get('settings',{})})
        return self.store.put('decks',{**result,'name':name,'settings':settings,'status':'draft','notes':''})
    def deck(self,ident):
        d=self.store.get('decks',ident)
        if not d:raise ValidationError('Deck not found. It may be in Trash.')
        ready=0;errors=0;warns=0;total=0
        for c in d['cards']:
            for f in c['faces']:
                sf=c.get('scryfall',{});sf_faces=ingest.face_list(sf)
                sf_face=sf_faces[min(f.get('index',0),len(sf_faces)-1)] if sf_faces else sf
                f['group']=type_group(sf_face,sf,f.get('index',0))
                total+=1
                if f.get('error'):errors+=1
                comp=f.get('compiled') or {};r=self.store.render_get(comp.get('renderKey',''))
                if comp:comp['render']=r
                if r:ready+=1
                if (comp.get('crop') or {}).get('warning') or comp.get('flags'):warns+=1
        d['summary']={'cards':sum(quantity(c['quantity']) for c in d['cards']),'faces':total,'rendered':ready,'errors':errors,'warnings':warns}
        if d.get('status')!='draft':d['status']='attention' if errors else 'ready' if total and ready==total else 'prepared'
        return d
    def list_decks(self):
        out=[]
        for old in self.store.list('decks'):
            d=self.deck(old['id']);cover=''
            if d['cards']:
                c=d['cards'][0];f=c['faces'][0] if c['faces'] else {};comp=f.get('compiled') or {}
                cover=(('/api/assets/'+comp['artId']) if comp.get('artId') else '') or (c['scryfall'].get('image_uris') or {}).get('art_crop','')
                if not cover and c['scryfall'].get('card_faces'):cover=(c['scryfall']['card_faces'][0].get('image_uris') or {}).get('art_crop','')
            out.append({**{k:v for k,v in d.items() if k!='cards'},'cover':cover})
        return out
    def save(self,ident,patch):
        d=self.deck(ident);expected=patch.get('revision')
        if expected is None:raise ValidationError('A revision is required to save a deck safely.')
        dirty=False
        if 'name' in patch:d['name']=str(patch['name']).strip()[:200] or 'Untitled deck'
        if 'notes' in patch:d['notes']=str(patch['notes'])[:20000]
        if 'settings' in patch:
            new=self.validate_settings({**d['settings'],**patch['settings']})
            dirty=any(new.get(k)!=d['settings'].get(k) for k in FRONT_SETTINGS);d['settings']=new
        if dirty:d['status']='draft'
        d.pop('summary',None);return self.store.put('decks',d,expected)
    def mutate_card(self,deck_id,card_id,patch):
        d=self.deck(deck_id);c=next((c for c in d['cards'] if c['id']==card_id),None)
        if not c:raise ValidationError('Card no longer exists.')
        rev=patch.get('revision')
        if rev is None:raise ValidationError('Reload the deck before saving this card.')
        if patch.get('remove'):
            d['cards']=[x for x in d['cards'] if x['id']!=card_id]
        else:
            if 'quantity' in patch:c['quantity']=quantity(patch['quantity'])
            if 'backOverride' in patch:
                value=patch['backOverride']
                if value and not self.store.asset(value):raise ValidationError('Back image is missing.')
                c['backOverride']=value
            if patch.get('faceId'):
                f=next((f for f in c['faces'] if f['id']==patch['faceId']),None)
                if not f:raise ValidationError('Card face no longer exists.')
                for k in ('artistOverride','artOverride','templateOverride','fit','semanticOverrides'):
                    if k in patch:
                        if k=='artOverride' and patch[k] and not self.store.asset(patch[k]):raise ValidationError('Artwork image is missing.')
                        f[k]=patch[k];d['status']='draft'
        d.pop('summary',None);return self.store.put('decks',d,rev)
    def add_cards(self,ident,payload,progress=lambda *a:None,cancel=lambda:False):
        d=self.deck(ident);rev=payload.get('revision')
        if rev!=d['revision']:raise ConflictError('Reload the deck before adding cards.')
        result=self.sources.import_deck(payload.get('source',''),payload.get('includeOutside',False),d['settings'].get('refreshData',False),progress,cancel)
        if sum(c['quantity'] for c in d['cards']+result['cards'])>10000:raise ValidationError('Deck limit is 10,000 cards.')
        d['cards']+=result['cards'];d['status']='draft';d.pop('summary',None)
        return self.store.put('decks',d,rev)
    def duplicate(self,ident):
        d=self.deck(ident);d['name']=d['name']+' · copy';d.pop('id');d.pop('summary',None)
        for c in d['cards']:
            c['id']=uid()
            for f in c['faces']:f['id']=uid()
        return self.store.put('decks',d)
    def replace_printing(self,deck_id,card_id,source,revision):
        d=self.deck(deck_id);old=next((c for c in d['cards'] if c['id']==card_id),None)
        if not old:raise ValidationError('Card no longer exists.')
        sf=self.sources.resolve_card(source,d['settings'].get('refreshData',False))
        if sf.get('oracle_id') and old['scryfall'].get('oracle_id') and sf['oracle_id']!=old['scryfall']['oracle_id']:raise ValidationError('Select another printing of the same card, or use Add cards.')
        new=self.sources.entry(sf,old['quantity'],old['section']);new['id']=old['id'];new['backOverride']=old.get('backOverride')
        for i,f in enumerate(new['faces']):
            if i<len(old['faces']):
                for k in ('artistOverride','artOverride','templateOverride'):f[k]=old['faces'][i].get(k)
        d['cards']=[new if c['id']==card_id else c for c in d['cards']];d['status']='draft';d.pop('summary',None)
        return self.store.put('decks',d,revision)
    def _art(self,sf,face,opts,settings,index,land_index):
        if opts.get('artOverride'):return opts['artOverride'],'uploaded override',None
        name=face.get('name',sf['name']);stem=slug(name);url=None;origin=''
        local=settings['source'].get('localFiles',{})
        if settings['source']['mode']=='local' and stem in local:return local[stem],'computer folder',None
        if settings['source']['mode']=='github' and stem in index:url=index[stem];origin='GitHub folder'
        if not url and settings.get('useLandLibrary') and 'Land' in str(face.get('type_line') or sf.get('type_line','')).split(' — ')[0] and stem in land_index:url=land_index[stem];origin='land art library'
        if not url:
            if settings['source']['mode']!='scryfall' and not settings['source'].get('fallback',True):raise ValidationError('Missing custom art: '+stem+'.png. Upload it or enable Scryfall fallback.')
            url=self.sources.art_url(sf,face);origin='Scryfall selected printing'
        if not url:raise ValidationError('This selected printing does not provide face artwork. Upload custom art.')
        raw,_,_=self.net.fetch(url,refresh=settings.get('refreshData',False));asset=ingest_image(self.store,raw)
        if origin=='Scryfall selected printing' and ingest.saga_creature_trailing_rules_text(face.get('type_line',sf.get('type_line','')),face.get('oracle_text',sf.get('oracle_text',''))):
            im=decode_image(self.store.asset_path(asset['id']).read_bytes())
            if im.height<=182:raise ValidationError('Saga-creature artwork is too short for the approved 99/83-pixel crop.')
            im=im.crop((0,99,im.width,im.height-83));out=io.BytesIO();im.save(out,'PNG');asset=ingest_image(self.store,out.getvalue());url=None
        return asset['id'],origin,url
    def prepare(self,ident,progress=lambda *a:None,cancel=lambda:False):
        d=self.deck(ident);rev=d['revision'];s=self.validate_settings(d['settings'])
        if any(not s['symbols'].get(r) for r in RARITIES):raise ValidationError('Set up all four rarity symbols before preparing the deck.')
        index={};land_index={}
        if s['source']['mode']=='github':
            if not s['source'].get('githubFolder'):raise ValidationError('Provide the GitHub art folder.')
            progress(0,1,'Reading GitHub artwork folder');index=self.sources.github_index(s['source']['githubFolder'],s['source'].get('ref') or None)
        if s.get('useLandLibrary'):
            url=s.get('landLibrary') or self.global_settings().get('landLibrary')
            if not url:raise ValidationError('Add a land artwork library link in Settings, or turn the option off.')
            progress(0,1,'Reading optional land artwork library');land_index=self.sources.github_index(url)
        total=sum(len(c['faces']) for c in d['cards']);done=0
        for c in d['cards']:
            if cancel():raise ValidationError('Preparation cancelled.')
            sf=c['scryfall']
            refresh=bool(s.get('refreshData') or self.global_settings().get('refreshData'))
            if sf.get('id'):
                progress(done,total,'Checking cached metadata for '+c['name'])
                sf=self.sources.resolve_card(sf['id'],refresh);c['scryfall']=sf
            flavor_sf=self.sources.flavor_source(sf,s.get('flavorPolicy','auto'),c.get('sourceIsExact',True),refresh)
            sf_faces=ingest.face_list(sf)
            for f in c['faces']:
                if cancel():raise ValidationError('Preparation cancelled.')
                progress(done,total,'Preparing '+f['name']);f.pop('error',None)
                try:
                    face=sf_faces[min(f.get('index',0),len(sf_faces)-1)]
                    art_id,origin,url=self._art(sf,face,f,s,index,land_index)
                    options=copy.deepcopy(f)
                    flavor_face=ingest.select_matching_flavor_face(flavor_sf,face,f.get('index',0))
                    options.setdefault('semanticOverrides',{}).setdefault('flavor_text',str(ingest.face_value(flavor_face,flavor_sf,'flavor_text','') or ''))
                    comp=self.compiler.compile_face(sf,face,f.get('index',0),options,s,art_id)
                    if c.get('tokenSpec'):
                        entry=tokens.build_token({'key':comp['name'],'data':comp['data']},c['tokenSpec']);comp['data']=entry['data'];comp['name']=entry['key'];comp['group']='token';comp['recipe']='Card Tools copy token'
                        comp['renderKey']=render_key(comp['data'],art_id);comp['render']=self.store.render_get(comp['renderKey'])
                    comp['artOrigin']=origin;comp['exportArtUrl']=url;f['compiled']=comp
                except (ValidationError,native.BuildError,ValueError,OSError) as e:
                    f['error']=str(e);f.pop('compiled',None)
                done+=1;progress(done,total,'Prepared '+f['name'])
        d['settings']=s;d['status']='prepared';d.pop('summary',None)
        self.store.put('decks',d,rev);return self.deck(ident)
    def copy_token(self,deck_id,card_id,spec,revision):
        d=self.deck(deck_id);c=next((x for x in d['cards'] if x['id']==card_id),None)
        if not c:raise ValidationError('Source card no longer exists.')
        if len(c['faces'])!=1:raise ValidationError('Choose a single-face card for the preserved Copy Token tool.')
        if not (c['faces'][0].get('compiled')):raise ValidationError('Prepare the source card first.')
        allowed={'nonlegendary','replace_creature_subtypes','power_toughness','frame_color','color_override','token_key_suffix'}
        spec={k:v for k,v in spec.items() if k in allowed};spec.setdefault('token_key_suffix',' — Copy Token')
        try:tokens.build_token({'key':c['name'],'data':c['faces'][0]['compiled']['data']},spec)
        except (Exception,SystemExit) as exc:raise ValidationError('Token specification could not be applied: '+str(exc)) from exc
        new=copy.deepcopy(c);new['id']=uid();new['name']=c['name']+spec['token_key_suffix'];new['quantity']=1;new['tokenSpec']=spec
        new['faces'][0].update(id=uid(),name=new['name']);new['faces'][0].pop('compiled',None)
        d['cards'].append(new);d['status']='draft';d.pop('summary',None);return self.store.put('decks',d,revision)
    def templates(self):return BUILTINS+self.store.list('templates')
    def save_template(self,value):
        d=validate_template(value.get('data',{}));groups=value.get('groups',[])
        if not groups or any(g not in GROUP_LABELS for g in groups):raise ValidationError('Choose the structural groups this template supports.')
        mapping=value.get('mapping') or {}
        if not isinstance(mapping,dict) or any(k not in d['text'] or not isinstance(v,str) for k,v in mapping.items()):raise ValidationError('Bind existing text slots to card fields.')
        if value.get('id') and value.get('revision') is None:
            raise ValidationError('Reload the template before saving; its revision is required.')
        result=self.store.put('templates',{'id':value.get('id'),'name':str(value.get('name') or 'Custom template')[:200],'data':d,'groups':groups,'legendary':bool(value.get('legendary')),'mapping':mapping},value.get('revision'))
        self.invalidate_template(result['id'])
        return result
    def invalidate_template(self,ident):
        # Invalidate only decks referencing this template, never saved order snapshots.
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            rows=db.execute("SELECT id,body FROM documents WHERE kind='decks'").fetchall()
            for row in rows:
                d=json.loads(row['body'])
                uses=ident in d.get('settings',{}).get('templateRules',{}).values() or any(f.get('templateOverride')==ident for c in d.get('cards',[]) for f in c.get('faces',[]))
                if uses:
                    d['status']='draft'
                    db.execute("UPDATE documents SET body=?,rev=rev+1,updated=? WHERE kind='decks' AND id=?",(json.dumps(d,ensure_ascii=False),time.time(),row['id']))
    def delete_template(self,ident,revision):
        if revision is None:raise ValidationError('Reload the template before deleting it.')
        result=self.store.trash('templates',ident,revision)
        self.invalidate_template(ident)
        return result
    def template_seed(self,kind='normal'):
        if kind in {'land','legend-land'}:
            sem={'name':'My land template','types':['Land'],'subtypes':[],'legendary':kind=='legend-land','basic':False,'colors':[],'land_colors':['G'],'oracle_text':'{T}: Add {G}.'}
            key='land_full_single' if kind=='land' else 'land_full_legendary'
            return copy.deepcopy(native.recipe_data(key,sem,native.get_type_info(sem))['data'])
        return copy.deepcopy(native.LAYOUTS['creature']['data'])
    def render_targets(self,deck_ids):
        targets={};cached=0;errors=[]
        for ident in deck_ids:
            d=self.deck(ident)
            if d['status']=='draft':raise ValidationError(d['name']+': prepare changes before rendering.')
            for c in d['cards']:
                for f in c['faces']:
                    comp=f.get('compiled')
                    if f.get('error') or not comp:
                        errors.append(d['name']+' / '+f['name']+': '+str(f.get('error') or 'not prepared'));continue
                    if self.store.render_get(comp['renderKey']):cached+=1;continue
                    targets.setdefault(comp['renderKey'],{'key':comp['renderKey'],'name':f['name'],'data':comp['data']})
        return {'targets':list(targets.values()),'cached':cached,'errors':errors}
    def save_render(self,key,raw,expected_size):
        asset=ingest_image(self.store,raw)
        if [asset['width'],asset['height']]!=list(expected_size):raise ValidationError('Rendered canvas size did not match its template. Nothing was marked ready.')
        return self.store.render_put(key,asset)
    def export_cc(self,deck_ids):
        entries=[];used_keys=set()
        for ident in deck_ids:
            d=self.deck(ident)
            if d['status']=='draft':raise ValidationError('Prepare '+d['name']+' before exporting CardConjurer data.')
            for c in d['cards']:
                for f in c['faces']:
                    comp=f.get('compiled')
                    if not comp or f.get('error'):raise ValidationError(f['name']+': fix preparation errors before exporting.')
                    data=copy.deepcopy(comp['data'])
                    data['artSource']=comp.get('exportArtUrl') or data_uri(self.store,comp['artId']);data['setSymbolSource']=data_uri(self.store,comp['symbolId'])
                    key=f['name']
                    if key in used_keys:key=key+' ['+d['name']+' / '+str(len(entries)+1)+']'
                    used_keys.add(key);entries.append({'key':key,'data':data})
        return json.dumps(entries,ensure_ascii=False,separators=(',',':')).encode()
    def original_images(self,ident,progress=lambda *a:None,cancel=lambda:False):
        d=self.deck(ident);out=self.store.home/'orders'/('originals-'+uid()+'.zip');names=set();count=0
        try:
            with zipfile.ZipFile(out,'w',zipfile.ZIP_STORED) as z:
                for c in d['cards']:
                    sf=c['scryfall'];faces=sf.get('card_faces') or [sf]
                    if sf.get('image_uris',{}).get('png'):faces=[sf]
                    for f in faces:
                        if cancel():raise ValidationError('Image export cancelled.')
                        url=(f.get('image_uris') or {}).get('png')
                        if not url:raise ValidationError(c['name']+': selected printing has no full-card PNG.')
                        raw,_,_=self.net.fetch(url,refresh=d['settings'].get('refreshData',False));decode_image(raw)
                        name=slug(f.get('name',c['name']))+'.png'
                        if name in names:name=slug(f.get('name',c['name']))+'_'+slug(sf.get('set','')+'_'+sf.get('collector_number','')+'_'+c['id'][:8])+'.png'
                        names.add(name);z.writestr(name,raw);count+=1
                    progress(count,0,'Saved '+c['name'])
            return {'filename':out.name,'count':count,'bytes':out.stat().st_size,'download':'/api/files/'+out.name}
        except Exception:out.unlink(missing_ok=True);raise
