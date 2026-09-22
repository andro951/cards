"""Deck orchestration. Source changes invalidate front renders; backs/quantities do not."""
from __future__ import annotations
import base64,copy,io,json,math,re,time,zipfile
from pathlib import PurePosixPath
from PIL import Image
from .domain import *
from .storage import Store,display_name
from .network import Network
from .images import ingest_image,data_uri,decode_image,rarity_variants
from .sources import Sources
from .compiler import Compiler,BUILTINS,SINGLE_SURFACE
from .legacy import ingest,compiler as native,tokens
from .credits import credit_text,printing_artist
from .backs import Backs

HOSTED_LAND_LIBRARY='https://github.com/andro951/cards/tree/main/ProxyFoundry/full_art_lands'
DEFAULT_SETTINGS={'source':{'mode':'scryfall','githubFolder':'','ref':'','localFiles':{},'fallback':True},'symbols':{},'artist':'','modificationCredit':'','backAsset':None,'templateRules':{},'useLandLibrary':False,'disableAutofit':False,'refreshData':False,'flavorPolicy':'auto','acceptCropWarnings':False,'acceptLayoutWarnings':False}
FRONT_SETTINGS={'source','symbols','artist','modificationCredit','templateRules','useLandLibrary','disableAutofit','flavorPolicy'}
class Workspace:
    def __init__(self,store=None,network=None):
        self.store=store or Store();self.net=network or Network(self.store);self.sources=Sources(self.net);self.compiler=Compiler(self.store);self.backs=Backs(self.store)
    def new_deck(self, name='Untitled deck'):
        return self.store.put('decks', {'name':str(name).strip()[:200] or 'Untitled deck',
            'cards':[], 'settings':self.validate_settings(self.global_settings().get('defaults',{})),
            'status':'draft', 'notes':'', 'importedSource':''})
    def global_settings(self):
        s=self.store.get('settings','global') or {'id':'global','refreshData':False,'deletePermanently':False,'defaults':{}}
        s.setdefault('deletePermanently',False)
        return s
    def set_global_settings(self,values):
        old=self.global_settings();old.pop('landLibrary',None);safe={k:v for k,v in values.items() if k in {'refreshData','deletePermanently','defaults'}}
        if 'deletePermanently' in safe:safe['deletePermanently']=bool(safe['deletePermanently'])
        if 'defaults' in safe and safe['defaults']:
            safe['defaults']=self.validate_settings(safe['defaults'])
        return self.store.put('settings',{**old,**safe},values.get('revision'))
    def validate_settings(self,settings):
        s={**copy.deepcopy(DEFAULT_SETTINGS),**settings,**self.backs.settings(settings)};s['source']={**DEFAULT_SETTINGS['source'],**s.get('source',{})};s.pop('landLibrary',None);s['source'].pop('refreshArt',None)
        if s['source']['mode'] not in {'scryfall','github','local'}:raise ValidationError('Select Scryfall, GitHub folder, or Computer folder.')
        if s['source']['mode']=='github' and s['source'].get('githubFolder'):github_location(s['source']['githubFolder'],s['source'].get('ref') or None)
        for ident in [s.get('backAsset'),*s.get('symbols',{}).values(),*s['source'].get('localFiles',{}).values()]:
            if ident and not self.store.asset(ident):raise ValidationError('A selected uploaded image is missing.')
        if len(s['source'].get('localFiles',{}))>5000:raise ValidationError('Select at most 5,000 local art files.')
        if s.get('flavorPolicy') not in {'auto','resolved','latest'}:raise ValidationError('Choose an automatic, selected-printing or latest-printing flavor policy.')
        s['artist']=credit_text(s.get('artist'))
        s['modificationCredit']=credit_text(s.get('modificationCredit'), 'Modification credit', maximum=160)
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
                f['originalArtist']=printing_artist(sf,sf_face)
                total+=1
                if f.get('error'):errors+=1
                comp=f.get('compiled') or {};r=self.store.render_get(comp.get('renderKey',''))
                if not comp:
                    # A failed preparation is a review/error state, not an
                    # unprepared-change state. Keeping it out of "draft" lets
                    # render planning save every valid face and report the real
                    # preparation error instead of the vague "prepare changes"
                    # message. Truly missing compilation data is still draft.
                    if not f.get('error'):
                        d['status']='draft';d['upgradeRequired']=True
                if comp:
                    comp['render']=r
                    if comp.get('generationVersion')!=PIPELINE_VERSION:
                        d['status']='draft';d['upgradeRequired']=True
                    else:
                        choice=f.get('templateOverride') or d.get('settings',{}).get('templateRules',{}).get(f['group'],'auto')
                        try:template_key,template_version,_=self.compiler.template_identity(f['group'],choice)
                        except ValidationError:
                            d['status']='draft'
                        else:
                            old_key=comp.get('templateKey');old_version=comp.get('templateVersion')
                            # Legacy compiled faces predate template version fields. They are
                            # compatible with built-in v1 and with custom templates whose edits
                            # already use invalidate_template(). Future v2+ bumps become stale.
                            if old_key is None:
                                if template_key.startswith(('auto:','builtin:')) and template_version!=1:d['status']='draft'
                            elif old_key!=template_key or old_version!=template_version:d['status']='draft'
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
            incoming={**d['settings'],**patch['settings']}
            # Old callers sending a complete back by ID remain supported.
            if 'backAsset' in patch['settings'] and 'backDesign' not in patch['settings']:incoming.pop('backDesign',None)
            new=self.validate_settings(incoming)
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
            if 'backDesignOverride' in patch and patch['backDesignOverride'] is not None:
                resolved=self.backs.settings({'backDesign':patch['backDesignOverride'],'backAsset':patch.get('backOverride')})
                c['backOverride']=resolved['backAsset'];c['backDesignOverride']=resolved['backDesign']
            elif 'backOverride' in patch:
                value=patch['backOverride']
                if value and not self.store.asset(value):raise ValidationError('Back image is missing.')
                c['backOverride']=value;c.pop('backDesignOverride',None)
            if patch.get('faceId'):
                f=next((f for f in c['faces'] if f['id']==patch['faceId']),None)
                if not f:raise ValidationError('Card face no longer exists.')
                for k in ('artistOverride','artistCreditMode','modificationCreditOverride','artOverride','templateOverride','fit','semanticOverrides'):
                    if k in patch:
                        if k=='artOverride' and patch[k] and not self.store.asset(patch[k]):raise ValidationError('Artwork image is missing.')
                        if k in {'artistOverride','modificationCreditOverride'} and patch[k] is not None:
                            credit_text(patch[k], 'Modification credit' if k=='modificationCreditOverride' else 'Artist credit', maximum=160 if k=='modificationCreditOverride' else 300)
                        if k=='artistCreditMode' and patch[k] not in {None,'inherit','printing'}:raise ValidationError('Invalid artist credit source.')
                        if f.get(k)!=patch[k]:f[k]=patch[k];d['status']='draft'
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
        new=self.sources.entry(sf,old['quantity'],old['section']);new['id']=old['id'];new['backOverride']=old.get('backOverride');new['backDesignOverride']=old.get('backDesignOverride')
        for i,f in enumerate(new['faces']):
            if i<len(old['faces']):
                for k in ('artistOverride','artistCreditMode','modificationCreditOverride','artOverride','templateOverride'):f[k]=old['faces'][i].get(k)
        d['cards']=[new if c['id']==card_id else c for c in d['cards']];d['status']='draft';d.pop('summary',None)
        return self.store.put('decks',d,revision)
    def _art(self,sf,face,opts,settings,index,land_index):
        if opts.get('artOverride'):return opts['artOverride'],'uploaded override',None
        name=face.get('name',sf['name']);stem=slug(name);url=None;remote_entry=None;origin=''
        local=settings['source'].get('localFiles',{})
        if settings['source']['mode']=='local' and stem in local:return local[stem],'computer folder',None
        if settings['source']['mode']=='github' and stem in index:remote_entry=index[stem];origin='GitHub folder'
        if remote_entry is None and settings.get('useLandLibrary') and 'Land' in str(face.get('type_line') or sf.get('type_line','')).split(' — ')[0] and stem in land_index:remote_entry=land_index[stem];origin='land art library'
        if remote_entry is None:
            if settings['source']['mode']!='scryfall' and not settings['source'].get('fallback',True):raise ValidationError('Missing custom art: '+stem+'.png. Upload it or enable Scryfall fallback.')
            url=self.sources.art_url(sf,face);origin='Scryfall selected printing'
            if not url:raise ValidationError('This selected printing does not provide face artwork. Upload custom art.')
        refresh=bool(settings.get('refreshData') or self.global_settings().get('refreshData'))
        # GitHub indexes resolve the branch to an exact commit and retain the
        # directory listing's blob SHA. The raw URL is therefore immutable and
        # its bytes are verified before normalization. Scryfall keeps its
        # separate year/week cache policy.
        if remote_entry is not None:
            raw,url=self.sources.github_art(remote_entry)
        else:
            raw,_,_=self.net.fetch(url,refresh=refresh,ttl=None)
        asset=ingest_image(self.store,raw)
        if origin=='Scryfall selected printing' and ingest.saga_creature_trailing_rules_text(face.get('type_line',sf.get('type_line','')),face.get('oracle_text',sf.get('oracle_text',''))):
            im=decode_image(self.store.asset_path(asset['id']).read_bytes())
            if im.height<=182:raise ValidationError('Saga-creature artwork is too short for the approved 99/83-pixel crop.')
            im=im.crop((0,99,im.width,im.height-83));out=io.BytesIO();im.save(out,'PNG');asset=ingest_image(self.store,out.getvalue());url=None
        return asset['id'],origin,url
    def _meld_back(self,sf,refresh=False):
        result=sf.get('_meld_result') or {};images=result.get('image_uris') or {}
        url=images.get('png') or images.get('large') or images.get('normal') or images.get('small')
        if not url:raise ValidationError('Scryfall did not provide an image for the meld result.')
        raw,_,_=self.net.fetch(url,refresh=refresh)
        try:
            with Image.open(io.BytesIO(raw)) as source:
                source.load();width,height=source.size
                if width<2 or height<2:raise ValueError('invalid meld result dimensions')
                split=height//2;top=bool(re.search(r'\bmeld them into\b',str(sf.get('oracle_text','')),re.I))
                box=(0,0,width,split) if top else (0,split,width,height)
                half=source.crop(box).transpose(Image.Transpose.ROTATE_90);out=io.BytesIO();half.save(out,'PNG')
        except (OSError,ValueError) as exc:raise ValidationError('Could not decode the Scryfall meld-result image.') from exc
        return ingest_image(self.store,out.getvalue())['id']
    def _prepare_card_faces(self,d,c,s,index,land_index,progress,cancel,done,total):
        if cancel():raise ValidationError('Preparation cancelled.')
        sf=c['scryfall']
        refresh=bool(s.get('refreshData') or self.global_settings().get('refreshData'))
        if sf.get('id'):
            progress(done,total,'Checking cached metadata for '+c['name'])
            sf=self.sources.resolve_card(sf['id'],refresh);c['scryfall']=sf
        if sf.get('_meld_result'):c['meldBackAsset']=self._meld_back(sf,refresh)
        else:c.pop('meldBackAsset',None)
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
                if sf.get('layout') in {'flip','prepare'} and len(sf_faces)==2:
                    nested='flip_face' if sf['layout']=='flip' else 'prepared_spell'
                    secondary_flavor=ingest.select_matching_flavor_face(flavor_sf,sf_faces[1],1)
                    options['nestedFlavorTexts']={nested:str(ingest.face_value(secondary_flavor,flavor_sf,'flavor_text','') or '')}
                comp=self.compiler.compile_face(sf,face,f.get('index',0),options,s,art_id,art_origin=origin)
                if c.get('tokenSpec'):
                    entry=tokens.build_token({'key':comp['name'],'data':comp['data']},c['tokenSpec']);comp['data']=entry['data'];comp['name']=entry['key'];comp['group']='token';comp['recipe']='Card Tools copy token'
                    comp['renderKey']=render_key(comp['data'],art_id,comp.get('templateCacheVersion',1));comp['render']=self.store.render_get(comp['renderKey'])
                content_key=comp['renderKey']
                comp['contentRenderKey']=content_key
                comp['renderKey']=stable_hash({'content':content_key,'deck':d['id'],'face':f['id']})
                comp['render']=self.store.render_get(comp['renderKey'])
                comp['artOrigin']=origin;comp['exportArtUrl']=url;f['compiled']=comp
            except (ValidationError,native.BuildError,ValueError,OSError) as e:
                f['error']=str(e);f.pop('compiled',None)
            done+=1;progress(done,total,'Prepared '+f['name'])
        return done
    def _prepare_sources(self,s,progress):
        index={};land_index={}
        if s['source']['mode']=='github':
            if not s['source'].get('githubFolder'):raise ValidationError('Provide the GitHub art folder.')
            progress(0,1,'Reading GitHub artwork folder');index=self.sources.github_index(s['source']['githubFolder'],s['source'].get('ref') or None,refresh=True)
        if s.get('useLandLibrary'):
            progress(0,1,'Reading hosted full-art land library');land_index=self.sources.github_index(HOSTED_LAND_LIBRARY,refresh=True)
        return index,land_index
    def prepare(self,ident,progress=lambda *a:None,cancel=lambda:False):
        d=self.deck(ident);rev=d['revision'];s=self.validate_settings(d['settings'])
        if any(not s['symbols'].get(r) for r in RARITIES):raise ValidationError('Set up all four rarity symbols before preparing the deck.')
        index,land_index=self._prepare_sources(s,progress)
        total=sum(len(c['faces']) for c in d['cards']);done=0
        for c in d['cards']:
            done=self._prepare_card_faces(d,c,s,index,land_index,progress,cancel,done,total)
        d['settings']=s;d['status']='prepared';d.pop('summary',None);d.pop('upgradeRequired',None)
        self.store.put('decks',d,rev);return self.deck(ident)
    def prepare_card(self,ident,card_id,progress=lambda *a:None,cancel=lambda:False):
        d=self.deck(ident);rev=d['revision'];s=self.validate_settings(d['settings'])
        if any(not s['symbols'].get(r) for r in RARITIES):raise ValidationError('Set up all four rarity symbols before preparing this card.')
        c=next((x for x in d['cards'] if x['id']==card_id),None)
        if not c:raise ValidationError('Card no longer exists.')
        index,land_index=self._prepare_sources(s,progress)
        self._prepare_card_faces(d,c,s,index,land_index,progress,cancel,0,len(c.get('faces',[])))
        # Preparing one card must not imply that unrelated pending deck changes
        # were prepared. Clear derived upgrade metadata so deck() can recompute it,
        # but preserve the deck's draft/prepared state exactly as it was.
        d['settings']=s;d.pop('summary',None);d.pop('upgradeRequired',None)
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
    def render_targets(self,deck_ids,force=False):
        targets={};cached=0;errors=[]
        for ident in deck_ids:
            d=self.deck(ident)
            if d['status']=='draft':raise ValidationError(d['name']+': prepare changes before rendering.')
            for c in d['cards']:
                for f in c['faces']:
                    comp=f.get('compiled')
                    if f.get('error') or not comp:
                        errors.append(d['name']+' / '+f['name']+': '+str(f.get('error') or 'not prepared'));continue
                    if not force and self.store.render_get(comp['renderKey']):cached+=1;continue
                    targets.setdefault(comp['renderKey'],{'key':comp['renderKey'],'name':f['name'],'deckName':d['name'],'deckId':d['id'],'cardName':c['name'],'cardId':c['id'],'faceId':f['id'],'data':comp['data']})
        return {'targets':list(targets.values()),'cached':cached,'errors':errors}
    def render_targets_for_card(self,deck_id,card_id,force=False):
        d=self.deck(deck_id)
        c=next((x for x in d['cards'] if x['id']==card_id),None)
        if not c:raise ValidationError('Card no longer exists.')
        targets={};cached=0;errors=[]
        for f in c.get('faces',[]):
            comp=f.get('compiled')
            if f.get('error') or not comp:
                errors.append(d['name']+' / '+f['name']+': '+str(f.get('error') or 'not prepared'));continue
            if not force and self.store.render_get(comp['renderKey']):cached+=1;continue
            targets.setdefault(comp['renderKey'],{'key':comp['renderKey'],'name':f['name'],'deckName':d['name'],'deckId':d['id'],'cardName':c['name'],'cardId':c['id'],'faceId':f['id'],'data':comp['data']})
        return {'targets':list(targets.values()),'cached':cached,'errors':errors,'deckName':d['name'],'cardName':c['name']}
    def _render_target_from_key(self,key):
        for d in self.store.list('decks'):
            for c in d.get('cards',[]):
                for f in c.get('faces',[]):
                    comp=f.get('compiled') or {}
                    if comp.get('renderKey')==key:
                        return {'key':key,'name':f.get('name') or c.get('name') or 'Card','deckName':d.get('name') or 'Deck','deckId':d.get('id'),'cardName':c.get('name') or 'Card','cardId':c.get('id'),'faceId':f.get('id'),'data':comp.get('data') or {}}
        return {'key':key,'name':'Card','deckName':'Deck','data':{}}

    def save_render(self,target,raw,expected_size):
        if isinstance(target,str):target=self._render_target_from_key(target)
        asset=ingest_image(self.store,raw)
        if [asset['width'],asset['height']]!=list(expected_size):raise ValidationError('Rendered canvas size did not match its template. Nothing was marked ready.')
        return self.store.render_put(target['key'],asset,deck_id=target.get('deckId'),card_id=target.get('cardId'),face_id=target.get('faceId'),deck_name=target.get('deckName') or 'Deck',face_name=target.get('name') or target.get('cardName') or 'Card')
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

    @staticmethod
    def _js_round(value):
        return math.floor(float(value)+0.5)

    def _cropped_art_png(self,face,deck_name):
        if face.get('error'):raise ValidationError(deck_name+' / '+face.get('name','Card')+': '+str(face['error']))
        comp=face.get('compiled') or {}
        data=comp.get('data') or {}
        art_id=comp.get('artId')
        asset=self.store.asset(art_id) if art_id else None
        if not asset:raise ValidationError(deck_name+' / '+face.get('name','Card')+': prepared artwork is missing.')
        try:
            cw=float(data.get('width') or 2010);ch=float(data.get('height') or 2814)
            mx=float(data.get('marginX') or 0);my=float(data.get('marginY') or 0)
            bounds=data.get('artBounds') or {'x':0,'y':0,'width':1,'height':1}
            bx=float(bounds.get('x') or 0);by=float(bounds.get('y') or 0)
            bw=float(bounds.get('width') or 0);bh=float(bounds.get('height') or 0)
            zoom=float(data.get('artZoom') or 0);angle=float(data.get('artRotate') or 0)
            art_x=float(data.get('artX') or 0);art_y=float(data.get('artY') or 0)
        except (TypeError,ValueError) as exc:
            raise ValidationError(deck_name+' / '+face.get('name','Card')+': artwork placement contains an invalid number.') from exc
        if not all(math.isfinite(x) for x in (cw,ch,mx,my,bx,by,bw,bh,zoom,angle,art_x,art_y)) or min(cw,ch,bw,bh,zoom)<=0:
            raise ValidationError(deck_name+' / '+face.get('name','Card')+': artwork placement is invalid.')

        # Mirror CardConjurer's canvas transform exactly: translate to artX/Y,
        # rotate around the art's top-left origin, then scale the source image.
        out_w=max(1,self._js_round(bw*cw));out_h=max(1,self._js_round(bh*ch))
        window_x=self._js_round((bx+mx)*cw);window_y=self._js_round((by+my)*ch)
        placed_x=self._js_round((art_x+mx)*cw);placed_y=self._js_round((art_y+my)*ch)
        radians=math.radians(angle);cos_a=math.cos(radians);sin_a=math.sin(radians);inv=1.0/zoom
        affine=(
            cos_a*inv,
            sin_a*inv,
            (cos_a*(window_x-placed_x)+sin_a*(window_y-placed_y))*inv,
            -sin_a*inv,
            cos_a*inv,
            (-sin_a*(window_x-placed_x)+cos_a*(window_y-placed_y))*inv,
        )
        source=decode_image(self.store.asset_path(art_id).read_bytes()).convert('RGBA')
        cropped=source.transform(
            (out_w,out_h),
            Image.Transform.AFFINE,
            affine,
            resample=Image.Resampling.BICUBIC,
            fillcolor=(0,0,0,0),
        )
        output=io.BytesIO();cropped.save(output,'PNG');return output.getvalue()

    def cropped_art(self,ident,progress=lambda *a:None,cancel=lambda:False):
        d=self.deck(ident)
        if d.get('status')=='draft':raise ValidationError(d['name']+': prepare the latest changes before downloading cropped art.')
        total=sum(len(c.get('faces',[])) for c in d.get('cards',[]))
        if not total:raise ValidationError(d['name']+': this deck has no card artwork to export.')
        stem=slug(d['name'])[:80] or 'deck'
        out=self.store.home/'orders'/('BulkProxyForge_Cropped_Art_'+stem+'_'+uid()[:8]+'.zip')
        used=set();count=0
        def unique_name(value):
            base=display_name(value,'Card');name=base+'.png';number=2
            while name.casefold() in used:
                name=f'{base} ({number}).png';number+=1
            used.add(name.casefold());return name
        try:
            with zipfile.ZipFile(out,'w',zipfile.ZIP_STORED,allowZip64=True) as archive:
                for c in d.get('cards',[]):
                    for f in c.get('faces',[]):
                        if cancel():raise ValidationError('Cropped-art export cancelled.')
                        raw=self._cropped_art_png(f,d['name'])
                        archive.writestr(unique_name(f.get('name') or c.get('name') or 'Card'),raw)
                        count+=1;progress(count,total,'Cropped art for '+str(f.get('name') or c.get('name') or 'Card'))
            return {'filename':out.name,'count':count,'bytes':out.stat().st_size,'download':'/api/files/'+out.name}
        except Exception:
            out.unlink(missing_ok=True);raise

    def _review_render(self,face,deck_name):
        if face.get('error'):raise ValidationError(deck_name+' / '+face['name']+': '+face['error'])
        render=self.store.render_get((face.get('compiled') or {}).get('renderKey',''))
        if not render:raise ValidationError(deck_name+' / '+face['name']+': render is missing or out of date.')
        return render

    def _review_composite(self,reference_url,render,refresh=False):
        raw,_,_=self.net.fetch(reference_url,refresh=refresh)
        reference=decode_image(raw)
        ours=decode_image(self.store.asset_path(render['asset_id']).read_bytes())
        if reference.size!=ours.size:
            reference=reference.resize(ours.size,Image.Resampling.LANCZOS)
        canvas=Image.new('RGBA',(ours.width*2+1,ours.height),(0,0,0,255))
        canvas.paste(reference,(0,0),reference)
        canvas.paste(ours,(ours.width+1,0),ours)
        out=io.BytesIO();canvas.save(out,'PNG');return out.getvalue()

    def review_image(self,deck_id,card_id,face_id=None,progress=lambda *a:None,cancel=lambda:False):
        d=self.deck(deck_id)
        c=next((x for x in d.get('cards',[]) if x['id']==card_id),None)
        if not c:raise ValidationError('Card no longer exists.')
        faces=c.get('faces') or []
        if not faces:raise ValidationError(c['name']+': card has no renderable face.')
        face=next((x for x in faces if x.get('id')==face_id),None) if face_id else faces[0]
        if not face:raise ValidationError('Card face no longer exists.')
        if cancel():raise ValidationError('Review-image export cancelled.')
        sf=c['scryfall'];sf_faces=sf.get('card_faces') or [sf]
        index=min(max(int(face.get('index',0) or 0),0),len(sf_faces)-1)
        source_face=sf if index==0 and (sf.get('image_uris') or {}).get('png') else sf_faces[index]
        reference_url=(source_face.get('image_uris') or {}).get('png')
        if not reference_url:raise ValidationError(face.get('name',c['name'])+': selected printing has no full-card PNG for this face.')
        render=self._review_render(face,d['name'])
        refresh=bool(d.get('settings',{}).get('refreshData',False))
        raw=self._review_composite(reference_url,render,refresh)
        base=slug(face.get('name',c['name'])) or 'card';filename=base+'_review.png'
        out=self.store.home/'orders'/filename
        if out.exists():
            filename=base+'_'+uid()[:8]+'_review.png';out=self.store.home/'orders'/filename
        out.write_bytes(raw);progress(1,1,'Saved review image for '+face.get('name',c['name']))
        return {'filename':filename,'count':1,'bytes':out.stat().st_size,'download':'/api/files/'+filename}

    def review_images(self,ident,progress=lambda *a:None,cancel=lambda:False):
        d=self.deck(ident)
        if d.get('status')=='draft':raise ValidationError(d['name']+': prepare the latest changes before downloading review images.')
        stem=slug(d['name'])[:80] or 'deck'
        out=self.store.home/'orders'/('BulkProxyForge_Review_Images_'+stem+'_'+uid()[:8]+'.zip')
        names=set();count=0;refresh=bool(d.get('settings',{}).get('refreshData',False))
        dfc_layouts={'transform','modal_dfc','double_faced_token','reversible_card'}
        total=sum(1+(1 if c.get('scryfall',{}).get('layout') in dfc_layouts and len(c.get('faces',[]))>=2 else 0) for c in d['cards'])
        def unique_name(face_name,sf,card_id):
            base=slug(face_name) or 'card';name=base+'_review.png'
            if name in names:
                suffix=slug(str(sf.get('set',''))+'_'+str(sf.get('collector_number',''))+'_'+card_id[:8])
                name=base+'_'+suffix+'_review.png'
            names.add(name);return name
        try:
            with zipfile.ZipFile(out,'w',zipfile.ZIP_STORED) as z:
                for c in d['cards']:
                    if cancel():raise ValidationError('Review-image export cancelled.')
                    sf=c['scryfall'];faces=c.get('faces') or []
                    if not faces:raise ValidationError(c['name']+': card has no renderable face.')
                    sf_faces=sf.get('card_faces') or [sf]
                    front_sf=sf if (sf.get('image_uris') or {}).get('png') else sf_faces[0]
                    front_url=(front_sf.get('image_uris') or {}).get('png')
                    if not front_url:raise ValidationError(c['name']+': selected printing has no full-card PNG for the front.')
                    front=faces[0];render=self._review_render(front,d['name'])
                    z.writestr(unique_name(front.get('name',c['name']),sf,c['id']),self._review_composite(front_url,render,refresh));count+=1
                    progress(count,total,'Saved review image for '+front.get('name',c['name']))
                    if sf.get('layout') in dfc_layouts and len(faces)>=2:
                        if len(sf_faces)<2:raise ValidationError(c['name']+': selected printing is missing its reverse face.')
                        back_url=(sf_faces[1].get('image_uris') or {}).get('png')
                        if not back_url:raise ValidationError(c['name']+': selected printing has no full-card PNG for the reverse face.')
                        back=faces[1];render=self._review_render(back,d['name'])
                        z.writestr(unique_name(back.get('name',c['name']+' back'),sf,c['id']),self._review_composite(back_url,render,refresh));count+=1
                        progress(count,total,'Saved review image for '+back.get('name',c['name']))
            return {'filename':out.name,'count':count,'bytes':out.stat().st_size,'download':'/api/files/'+out.name}
        except Exception:out.unlink(missing_ok=True);raise
