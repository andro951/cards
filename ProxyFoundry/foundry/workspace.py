"""Deck orchestration. Source changes invalidate front renders; backs/quantities do not."""
from __future__ import annotations
from .timing import timed,timing
import base64,copy,hashlib,io,json,math,re,time,zipfile
from pathlib import Path,PurePosixPath
from PIL import Image
from .domain import *
from .storage import Store,display_name
from .network import Network
from .images import ingest_image,ingest_render_png,data_uri,decode_image,rarity_variants
from .sources import Sources
from .artwork import ArtworkIndex,build_review,face_key
from .card_data import validate_entries,validate_targets,matches,merge_entries,identity,matching_keys,selector_key
from .compiler import Compiler,BUILTINS,SINGLE_SURFACE,fit_token_art,semantic,apply_nickname_treatment,apply_full_art_text,apply_modern_token_text,frame_treatment_code,full_art_nonland_placement,fit_set_symbol_to_bounds,build_token_data,configure_token_style,token_has_short_text
from .legacy import ingest,compiler as native,tokens
from .credits import credit_text,printing_artist
from .backs import Backs
from .template_model import convert_cardconjurer, validate_model

BUNDLED_SYMBOL_ROOT=Path(__file__).resolve().parents[1]/'assets'/'symbols'
DEFAULT_SETTINGS={'source':{'mode':'scryfall','githubFolder':'','ref':'','localFiles':{},'fallback':False},'symbols':{},'artist':'','backAsset':None,'templateRules':{},'disableAutofit':False,'refreshData':False,'flavorPolicy':'auto','showFlavorText':True,'dataJsonSource':None,'symbolsSource':None,'allCardsTokens':False,'tokenOptions':{'power':'','toughness':'','subtypes':'','nonlegendary':False},'acceptCropWarnings':False,'acceptLayoutWarnings':False}
FRONT_SETTINGS={'artDefaults','source','symbols','artist','templateRules','disableAutofit','flavorPolicy','showFlavorText','allCardsTokens','tokenOptions'}
class Workspace:
    def __init__(self,store=None,network=None):
        self.store=store or Store();self.net=network or Network(self.store);self.sources=Sources(self.net);self.compiler=Compiler(self.store);self.backs=Backs(self.store);self._default_symbols=None
    def default_symbols(self):
        """Import the four bundled rarity symbols into this workspace once."""
        if self._default_symbols is None:
            symbols={}
            for rarity in RARITIES:
                path=BUNDLED_SYMBOL_ROOT/(rarity+'.png')
                if not path.is_file():
                    raise ValidationError('The bundled default set symbols are missing. Extract the complete application ZIP, including assets/symbols.')
                symbols[rarity]=ingest_image(
                    self.store,path.read_bytes(),trim_transparent_padding=True
                )['id']
            self._default_symbols=symbols
        return dict(self._default_symbols)
    def _with_default_symbols(self,settings):
        """Fill missing rarity slots from the bundled defaults; explicit uploads win."""
        values=copy.deepcopy(settings or {})
        explicit=values.get('symbols') or {}
        if not isinstance(explicit,dict):
            raise ValidationError('Invalid set-symbol selection.')
        symbols=self.default_symbols()
        for rarity in RARITIES:
            if explicit.get(rarity):
                symbols[rarity]=explicit[rarity]
        values['symbols']=symbols
        return values
    def new_deck(self, name='Untitled deck'):
        return self.store.put('decks', {'name':str(name).strip()[:200] or 'Untitled deck',
            'cards':[], 'settings':self.validate_settings(self.import_defaults()),
            'status':'draft', 'notes':'', 'importedSource':''})
    def global_settings(self):
        s=self.store.get('settings','global') or {'id':'global','refreshData':False,'deletePermanently':False,'defaults':{},'defaultStylePresetId':None}
        s.setdefault('deletePermanently',False)
        s.setdefault('defaultStylePresetId',None)
        return s
    def set_global_settings(self,values):
        old=self.global_settings();old.pop('landLibrary',None);safe={k:v for k,v in values.items() if k in {'refreshData','deletePermanently','defaults','defaultStylePresetId'}}
        if 'defaultStylePresetId' in safe and safe['defaultStylePresetId'] and not self.store.get('style-presets',safe['defaultStylePresetId']):
            raise ValidationError('That saved style no longer exists.')
        if 'deletePermanently' in safe:safe['deletePermanently']=bool(safe['deletePermanently'])
        if 'defaults' in safe and safe['defaults']:
            safe['defaults']=self.validate_settings(safe['defaults'])
        return self.store.put('settings',{**old,**safe},values.get('revision'))
    def style_presets(self):
        return self.store.list('style-presets')
    def save_style_preset(self,deck_id,name):
        deck=self.deck(deck_id)
        title=str(name or '').strip()[:200]
        if not title:raise ValidationError('Name this saved style.')
        settings=copy.deepcopy(deck['settings'])
        settings['dataJsonSource']=None
        return self.store.put('style-presets',{'name':title,'schema':1,'settings':settings})
    def import_style_preset(self,data):
        if not isinstance(data,dict) or data.get('format')!='bulk-proxy-forge-style' or data.get('schema')!=1:
            raise ValidationError('Choose a Bulk Proxy Forge style JSON file.')
        title=str(data.get('name') or '').strip()[:200]
        if not title:raise ValidationError('The style needs a name.')
        assets=data.get('assets') or {}
        if not isinstance(assets,dict) or len(assets)>5000:raise ValidationError('Invalid style assets.')
        for ident,entry in assets.items():
            if not re.fullmatch(r'[0-9a-f]{64}',str(ident)) or not isinstance(entry,dict):raise ValidationError('Invalid style asset.')
            raw=base64.b64decode(entry.get('base64',''),validate=True)
            if len(raw)>64*1024**2 or hashlib.sha256(raw).hexdigest()!=ident:raise ValidationError('Style image failed its integrity check.')
            image=decode_image(raw)
            self.store.add_asset(raw,str(entry.get('mime') or 'image/png'),image.width,image.height)
        settings=self.validate_settings(data.get('settings') or {})
        settings['dataJsonSource']=None
        return self.store.put('style-presets',{'name':title,'schema':1,'settings':settings})
    def delete_style_preset(self,ident,revision=None):
        if self.global_settings().get('defaultStylePresetId')==ident:
            self.set_global_settings({'defaultStylePresetId':None})
        return self.store.purge('style-presets',ident,revision)
    def import_defaults(self):
        global_settings=self.global_settings()
        preset=self.store.get('style-presets',global_settings.get('defaultStylePresetId')) if global_settings.get('defaultStylePresetId') else None
        return copy.deepcopy(preset['settings'] if preset else global_settings.get('defaults',{}))
    def validate_settings(self,settings):
        settings=self._with_default_symbols(settings)
        settings.pop('modificationCredit',None);settings.pop('useLandLibrary',None);settings.pop('landLibrary',None)
        s={**copy.deepcopy(DEFAULT_SETTINGS),**settings,**self.backs.settings(settings)};s['source']={**DEFAULT_SETTINGS['source'],**s.get('source',{})};s.pop('landLibrary',None);s['source'].pop('refreshArt',None)
        if s['source']['mode'] not in {'scryfall','github','local'}:raise ValidationError('Select Scryfall, GitHub folder, or Computer folder.')
        if s['source']['mode']=='github' and s['source'].get('githubFolder'):github_location(s['source']['githubFolder'],s['source'].get('ref') or None)
        for ident in [s.get('backAsset'),*s.get('symbols',{}).values(),*s['source'].get('localFiles',{}).values()]:
            if ident and not self.store.asset(ident):raise ValidationError('A selected uploaded image is missing.')
        if len(s['source'].get('localFiles',{}))>5000:raise ValidationError('Select at most 5,000 local art files.')
        if s.get('flavorPolicy') not in {'auto','resolved','latest'}:raise ValidationError('Choose an automatic, selected-printing or latest-printing flavor policy.')
        s['showFlavorText']=bool(s.get('showFlavorText',True))
        for field,label in [('dataJsonSource','data.json'),('symbolsSource','set symbols')]:
            raw_data_source=s.get(field)
            if raw_data_source in (None,''):
                s[field]=None
            elif isinstance(raw_data_source,dict):
                kind=raw_data_source.get('kind');value=raw_data_source.get('value')
                if kind not in {'local','github'} or not isinstance(value,str):raise ValidationError('Invalid '+label+' source reference.')
                value=value.strip()
                if not value or len(value)>1000 or any(ord(ch)<32 or ord(ch)==127 for ch in value):raise ValidationError('Invalid '+label+' source reference.')
                s[field]={'kind':kind,'value':value}
            else:
                raise ValidationError('Invalid '+label+' source reference.')
        defaults=s.get('artDefaults',[])
        if not isinstance(defaults,list) or len(defaults)>10000 or any(not isinstance(k,str) or len(k)>500 for k in defaults):raise ValidationError('Invalid default artwork choices.')
        if not isinstance(s.get('artReviewSignature',''),str) or len(s.get('artReviewSignature',''))>64:raise ValidationError('Invalid artwork review reference.')
        names=s['source'].get('localNames',{})
        if not isinstance(names,dict) or any(not isinstance(k,str) or not isinstance(v,str) or len(v)>1000 for k,v in names.items()):raise ValidationError('Invalid artwork filenames.')
        s['allCardsTokens']=bool(s.get('allCardsTokens',False))
        raw_token_options=s.get('tokenOptions') or {}
        if not isinstance(raw_token_options,dict):raise ValidationError('Token options must be an object.')
        def token_text(key,label,maximum):
            value=raw_token_options.get(key,'')
            if value is None:value=''
            if not isinstance(value,str):raise ValidationError(label+' must be text.')
            value=value.strip()
            if len(value)>maximum or any(ord(ch)<32 or ord(ch)==127 for ch in value):
                raise ValidationError(label+' is invalid.')
            return value
        token_power=token_text('power','Token power override',20)
        token_toughness=token_text('toughness','Token toughness override',20)
        legendary_mode=raw_token_options.get('legendaryMode','nonlegendary' if raw_token_options.get('nonlegendary') else 'original')
        if legendary_mode not in {'nonlegendary','original','legendary'}:
            raise ValidationError('Choose a valid token legendary mode.')
        if '/' in token_power or '/' in token_toughness:
            raise ValidationError('Use the separate Power and Toughness boxes; do not include a slash.')
        s['tokenOptions']={
            'power':token_power,
            'toughness':token_toughness,
            'subtypes':token_text('subtypes','Token subtype override',200),
            'nonlegendary':bool(raw_token_options.get('nonlegendary',False)),
            'legendaryMode':legendary_mode,
        }
        s['artist']=credit_text(s.get('artist'))
        for group,choice in s.get('templateRules',{}).items():
            if group not in GROUP_LABELS:raise ValidationError('Unknown template group '+str(group))
            if choice not in {t['id'] for t in BUILTINS} and not self.store.get('templates',choice):raise ValidationError('A selected custom template is missing.')
            builtin=next((t for t in BUILTINS if t['id']==choice),None)
            if builtin and builtin['groups']!='all' and builtin['groups']!='ordinary' and group not in builtin['groups']:
                raise ValidationError('The selected template does not support '+group+'.')
            if choice=='land' and group in {'legendary','legendary-land'}:raise ValidationError('Full-art land has no compatible crown.')
        return s
    def create(self,payload,progress=lambda *a:None,cancel=lambda:False):
        steps=self.create_steps(payload,progress,cancel)
        while True:
            try:next(steps)
            except StopIteration as finished:return finished.value

    def create_steps(self,payload,progress=lambda *a:None,cancel=lambda:False):
        refresh=bool(payload.get('settings',{}).get('refreshData',self.global_settings().get('refreshData',False)))
        result=yield from self.sources.import_deck_steps(payload.get('source',''),payload.get('includeOutside',True),refresh,progress,cancel)
        if cancel():raise ValidationError('Import cancelled.')
        name=str(payload.get('name') or result['name']).strip()[:200] or 'Untitled deck'
        settings=self.validate_settings({**self.import_defaults(),**payload.get('settings',{})})
        return self.store.put('decks',{**result,'name':name,'settings':settings,'status':'draft','notes':''})
    def create_staged(self,payload):
        supplied=payload.get('manifest')
        if not isinstance(supplied,dict):raise ValidationError('Read a deck list before choosing its look.')
        listing=self.sources.read_deck_manifest(supplied,payload.get('includeOutside',True))
        cards=[]
        for row in listing['rows']:
            sf={'name':row['name'],'layout':'normal','type_line':''}
            if re.fullmatch(r'[0-9a-fA-F-]{36}',row['source']):sf['id']=row['source']
            card=self.sources.entry(sf,row['quantity'],row['section']);card['metadataSource']=row['source'];cards.append(card)
        settings=self.validate_settings({**self.import_defaults(),**payload.get('settings',{})})
        return self.store.put('decks',{'name':listing['name'],'cards':cards,'settings':settings,'status':'draft','notes':'',
            'importedSource':supplied.get('importedSource',''),'pendingImport':True,'stagedImport':True})

    @timed('deck.metadata')
    def resolve_metadata(self,ident,progress=lambda *a:None,cancel=lambda:False):
        steps=self.resolve_metadata_steps(ident,progress,cancel)
        while True:
            try:next(steps)
            except StopIteration as finished:return finished.value

    def resolve_metadata_steps(self,ident,progress=lambda *a:None,cancel=lambda:False):
        d=self.deck(ident)
        if not d.get('pendingImport'):return d
        resolved={};entries={};total=len(d['cards'])
        with timing(self.store,'deck.metadata',deckId=ident,cards=total):
            for index,card in enumerate(d['cards']):
                if cancel():raise ValidationError('Card details cancelled. Your setup is saved; retry to continue.')
                key=card['metadataSource'];progress(index,total,'Reading card details '+card['name'])
                if key not in resolved:resolved[key]=self.sources.resolve_card(key,d['settings'].get('refreshData',False))
                entry=self.sources.entry(resolved[key],card['quantity'],card.get('section','mainboard'))
                entry['id']=card['id']
                for number,face in enumerate(entry['faces']):
                    if number<len(card['faces']):face['id']=card['faces'][number]['id']
                entry['metadataSource']=key;entry['sourceIsExact']=bool(re.fullmatch(r'[0-9a-fA-F-]{36}',key) or ':' in key or key.startswith('https://'));entries[card['id']]=entry
                progress(index+1,total,'Read card details '+entry['name']);yield
            #Metadata is merged into the current deck, never the setup snapshot
            #taken before network calls. A deleted deck cannot be republished.
            for attempt in range(5):
                if cancel():raise ValidationError('Card details cancelled. Your setup is saved; retry to continue.')
                current=self.deck(ident)
                if not current.get('pendingImport'):return current
                cards=[];seen={}
                for card in current['cards']:
                    entry=entries.get(card['id'])
                    if not entry:raise ValidationError('The deck list changed while card details loaded. Retry preparation.')
                    fresh=copy.deepcopy(entry)
                    fresh['quantity']=card['quantity']
                    #Keep user overrides applied while metadata was being read.
                    for number,face in enumerate(fresh['faces']):
                        if number<len(card['faces']):
                            overrides={k:v for k,v in card['faces'][number].items() if k not in {'name','index','group','originalArtist'}}
                            face.update(overrides)
                    identity=(fresh['scryfall']['id'],fresh.get('section','mainboard'))
                    if identity in seen:seen[identity]['quantity']=quantity(seen[identity]['quantity']+fresh['quantity'])
                    else:seen[identity]=fresh;cards.append(fresh)
                current['cards']=cards;current.pop('pendingImport',None)
                current['metadataBaseRevision']=current['revision'];current.pop('summary',None)
                try:return self.store.put('decks',current,current['revision'])
                except ConflictError:
                    if attempt==4:raise
                yield

    def invalidate_face(self,face):
        previous=face.get('compiled') or {}
        if previous.get('renderKey') and self.store.render_get(previous['renderKey']):
            face['lastRender']={key:copy.deepcopy(previous[key]) for key in ('renderKey','crop','flags') if key in previous}
            face['lastRender']['render']=self.store.render_get(previous['renderKey'])
        face.pop('compiled',None);face.pop('error',None)

    def deck(self,ident):
        d=self.store.get('decks',ident)
        if d:d.pop('upgradeRequired',None)
        if not d:raise ValidationError('Deck not found. It may be in Trash.')
        # Legacy decks created before bundled defaults existed gain them on read;
        # uploaded/custom rarity IDs continue to override the matching defaults.
        d['settings']=self._with_default_symbols(d.get('settings',{}))
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
                        d['status']='draft'
                if f.get('lastRender'):
                    f['lastRender']['render']=self.store.render_get(f['lastRender']['renderKey'])
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
                if ((comp.get('crop') or {}).get('warning') or comp.get('flags')) and f.get('acceptedWarningKey')!=comp.get('renderKey'):warns+=1
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
    @staticmethod
    def _validated_card_data(value):
        return validate_entries(value)

    def _apply_card_data(self,d,value):
        entries=validate_entries(value)
        if d.get('pendingImport'):
            d['cardData']=merge_entries(d.get('cardData',[]),entries);return False
        entries=validate_targets(d,entries)
        if not entries:return False
        merged=merge_entries(d.get('cardData',[]),entries)
        selectors={selector_key(entry):entry for entry in merged}
        dirty=False
        for card in d.get('cards',[]):
            for face in card.get('faces',[]):
                updates=[selectors[key] for key in set(matching_keys(card,face)) if key in selectors]
                updates.sort(key=lambda e:(bool(e.get('oracle_id') or e.get('scryfall_id')),sum(bool(e.get(k)) for k in ['oracle_id','scryfall_id','name']),bool(e.get('scryfall_id'))))
                values={k:v for entry in updates for k,v in entry.items() if k in {'nickname','flavor_text','artist','art'}}
                current=face.get('semanticOverrides') or {};changed=False
                for key in ['nickname','flavor_text']:
                    if key in values and current.get(key)!=values[key]:current={**current,key:values[key]};changed=True
                if 'artist' in values and face.get('artistOverride')!=values['artist']:face['artistOverride']=values['artist'];changed=True
                if 'art' in values and face.get('artFilename')!=values['art']:
                    face['artFilename']=values['art'];changed=True
                    defaults=d['settings'].get('artDefaults',[])
                    d['settings']['artDefaults']=[key for key in defaults if key!=face_key(card,face)]
                if changed:
                    face['semanticOverrides']=current;self.invalidate_face(face);dirty=True
        d['cardData']=merged
        if dirty:d['status']='draft'
        return dirty

    @timed('artwork.review')
    def artwork_review(self,payload,progress=lambda *a:None,cancel=lambda:False):
        steps=self.artwork_review_steps(payload,progress,cancel)
        while True:
            try:next(steps)
            except StopIteration as finished:return finished.value

    def artwork_review_steps(self,payload,progress=lambda *a:None,cancel=lambda:False):
        d=copy.deepcopy(self.deck(payload['deckId']))
        s=self.validate_settings(payload.get('settings') or d['settings']);d['settings']=s
        self._apply_card_data(d,payload.get('cardData',[]))
        progress(0,1,'Checking artwork filenames…');yield
        if cancel():raise ValidationError('Artwork check cancelled.')
        index=self._prepare_sources(s,progress)
        yield
        if cancel():raise ValidationError('Artwork check cancelled.')
        result=build_review(d,s,index);progress(1,1,'Artwork filenames checked')
        return result


    def save(self,ident,patch):
        d=self.deck(ident);expected=patch.get('revision')
        if expected is None:raise ValidationError('A revision is required to save a deck safely.')
        if expected==d.get('metadataBaseRevision') and d['revision']==expected+1:expected=d['revision']
        d.pop('metadataBaseRevision',None)
        dirty=False;front_settings_dirty=False
        if 'name' in patch:d['name']=str(patch['name']).strip()[:200] or 'Untitled deck'
        if 'notes' in patch:d['notes']=str(patch['notes'])[:20000]
        if 'cardData' in patch:dirty=self._apply_card_data(d,patch.get('cardData')) or dirty
        if 'settings' in patch:
            incoming={**d['settings'],**patch['settings']}
            # Old callers sending a complete back by ID remain supported.
            if 'backAsset' in patch['settings'] and 'backDesign' not in patch['settings']:incoming.pop('backDesign',None)
            new=self.validate_settings(incoming)
            front_settings_dirty=any(new.get(k)!=d['settings'].get(k) for k in FRONT_SETTINGS)
            dirty=front_settings_dirty or dirty;d['settings']=new
        if dirty:
            d['status']='draft'
            if front_settings_dirty:
                for card in d.get('cards',[]):
                    for face in card.get('faces',[]):
                        self.invalidate_face(face)
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
                if 'acceptWarning' in patch:
                    comp=f.get('compiled') or {}
                    if not comp.get('renderKey') or not self.store.render_get(comp['renderKey']):
                        raise ValidationError('Render this face before accepting its warning.')
                    if not ((comp.get('crop') or {}).get('warning') or comp.get('flags')):
                        raise ValidationError('This face has no current crop or layout warning.')
                    if patch['acceptWarning'] is not True or patch.get('renderKey')!=comp['renderKey']:
                        raise ValidationError('The card render changed. Review its current image again.')
                    f['acceptedWarningKey']=comp['renderKey']
                face_dirty=False
                if 'selectedArtPrintingId' in patch:
                    selected=patch['selectedArtPrintingId']
                    if selected:
                        printing,art_face=self._matching_printing_face(c,f,selected)
                        art_url=self.sources.art_url(printing,art_face)
                        if not art_url:
                            raise ValidationError('That printing has no artwork for this face.')
                        artist=str(art_face.get('artist') or printing.get('artist') or '').strip()
                    else:artist='';art_url=None
                    if f.get('selectedArtPrintingId')!=selected:
                        f['selectedArtPrintingId']=selected or None
                        f['selectedArtArtist']=artist or None
                        f['selectedArtUrl']=art_url
                        face_dirty=True
                for kind,field_name,allowed in (
                    ('officialRulesSelection','officialRulesText',{'oracle_text','printed_text'}),
                    ('officialFlavorSelection','officialFlavorText',{'flavor_text'}),
                ):
                    if kind not in patch:continue
                    selected=patch[kind]
                    if selected is None:text=None;source=None
                    else:
                        if not isinstance(selected,dict) or selected.get('field') not in allowed:
                            raise ValidationError('Choose an official text option.')
                        printing,text_face=self._matching_printing_face(c,f,selected.get('printingId'))
                        text=str(text_face.get(selected['field']) or printing.get(selected['field']) or '').strip()
                        if not text or len(text)>20000:raise ValidationError('That printing has no usable official text.')
                        source={'printingId':printing['id'],'field':selected['field']}
                    if f.get(field_name)!=text or f.get(kind)!=source:
                        f[field_name]=text;f[kind]=source;face_dirty=True
                for k in ('artistOverride','artistCreditMode','artOverride','artFilename','templateOverride','fit','semanticOverrides'):
                    if k in patch:
                        if k=='artOverride' and patch[k] and not self.store.asset(patch[k]):raise ValidationError('Artwork image is missing.')
                        if k=='artistOverride' and patch[k] is not None:
                            credit_text(patch[k], 'Artist credit', maximum=300)
                        if k=='artistCreditMode' and patch[k] not in {None,'inherit','printing'}:raise ValidationError('Invalid artist credit source.')
                        if f.get(k)!=patch[k]:f[k]=patch[k];face_dirty=True
                if face_dirty:
                    self.invalidate_face(f);d['status']='draft'
        d.pop('summary',None);return self.store.put('decks',d,rev)
    def _matching_printing_face(self,card,face,ident):
        if not isinstance(ident,str) or not re.fullmatch(r'[0-9a-f-]{36}',ident):
            raise ValidationError('Choose a Scryfall printing of this card.')
        printing=self.sources.resolve_card(ident,False)
        original=card['scryfall']
        if original.get('oracle_id') and printing.get('oracle_id') and original['oracle_id']!=printing['oracle_id']:
            raise ValidationError('Choose a printing of the same card.')
        if not (original.get('oracle_id') and printing.get('oracle_id')) and slug(printing.get('name',''))!=slug(original.get('name','')):
            raise ValidationError('Choose a printing of the same card.')
        faces=ingest.face_list(printing)
        index=int(face.get('index',0))
        if index>=len(faces):raise ValidationError('That printing has no matching card face.')
        selected=faces[index]
        if len(faces)>1 and slug(selected.get('name',''))!=slug(face.get('name','')):
            raise ValidationError('That printing has no matching card face.')
        return printing,selected
    def add_cards(self,ident,payload,progress=lambda *a:None,cancel=lambda:False):
        steps=self.add_cards_steps(ident,payload,progress,cancel)
        while True:
            try:next(steps)
            except StopIteration as finished:return finished.value

    def add_cards_steps(self,ident,payload,progress=lambda *a:None,cancel=lambda:False):
        d=self.deck(ident);rev=payload.get('revision')
        if rev!=d['revision']:raise ConflictError('Reload the deck before adding cards.')
        result=yield from self.sources.import_deck_steps(payload.get('source',''),payload.get('includeOutside',False),d['settings'].get('refreshData',False),progress,cancel)
        if cancel():raise ValidationError('Import cancelled.')
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
                for k in ('artistOverride','artistCreditMode','artOverride','templateOverride'):f[k]=old['faces'][i].get(k)
        d['cards']=[new if c['id']==card_id else c for c in d['cards']];d['status']='draft';d.pop('summary',None)
        return self.store.put('decks',d,revision)
    def custom_art_previews(self,deck_id,settings):
        deck=self.deck(deck_id)
        selected=self.validate_settings(settings)
        index=self._prepare_sources(selected,lambda *args:None)
        out=[]
        for card in deck['cards']:
            faces=ingest.face_list(card['scryfall'])
            for face in card['faces']:
                sf_face=faces[min(face.get('index',0),len(faces)-1)]
                name=sf_face.get('name',card['name'])
                local=selected['source'].get('localFiles',{})
                if (face.get('selectedArtPrintingId') or face_key(card,face) in selected.get('artDefaults',[])) and not face.get('artOverride'):continue
                if not (face.get('artOverride') or selected['source']['mode']=='local' and index.resolve(name,identity(card,face)['oracle_id'],face.get('artFilename',''),len(faces)>1) is not None
                        or selected['source']['mode']=='github' and index.resolve(name,identity(card,face)['oracle_id'],face.get('artFilename',''),len(faces)>1) is not None):continue
                art_id,_,_=self._art(card['scryfall'],sf_face,face,selected,index)
                out.append({'cardId':card['id'],'faceId':face['id'],'name':face['name'],
                            'artist':face.get('artistOverride') or selected.get('artist') or '',
                            'assetId':art_id,**identity(card,face)})
        return out

    @timed('art.resolve')
    def _art(self,sf,face,opts,settings,index):
        if opts.get('artOverride'):return opts['artOverride'],'uploaded override',None
        name=face.get('name',sf['name']);stem=slug(name);url=None;remote_entry=None;origin=''
        if not isinstance(index,ArtworkIndex):index=ArtworkIndex(settings['source'].get('localFiles',{}) if settings['source']['mode']=='local' else index,settings['source'].get('localNames'))
        oracle=str(face.get('oracle_id') or sf.get('oracle_id') or '').lower()
        default_key=(oracle or sf.get('id') or '')+'/'+name
        if default_key in settings.get('artDefaults',[]):
            url=self.sources.art_url(sf,face);origin='Scryfall selected printing'
        local=settings['source'].get('localFiles',{})
        if url is not None:pass
        elif opts.get('selectedArtPrintingId'):
            alternate,alternate_face=self._matching_printing_face({'scryfall':sf},opts,opts['selectedArtPrintingId'])
            url=self.sources.art_url(alternate,alternate_face)
            if not url:raise ValidationError('That printing has no artwork for this face.')
            opts['selectedArtArtist']=str(alternate_face.get('artist') or alternate.get('artist') or '').strip() or None
            origin='Scryfall selected printing'
        elif settings['source']['mode']=='local':
            key=index.resolve(name,oracle,opts.get('artFilename',''),len(sf.get('card_faces') or [])>1,sf.get('id',''))
            if key is not None:return local[key],'computer folder',None
        elif settings['source']['mode']=='github':
            key=index.resolve(name,oracle,opts.get('artFilename',''),len(sf.get('card_faces') or [])>1,sf.get('id',''))
            if key is not None:remote_entry=index[key];origin='GitHub folder'
        if remote_entry is None and url is None:
            if settings['source']['mode']!='scryfall' and not settings['source'].get('fallback',False):raise ValidationError('Missing custom art: '+stem+'.png. Upload it or enable Scryfall fallback.')
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
        if (
            origin=='Scryfall selected printing'
            and ingest.saga_creature_trailing_rules_text(
                face.get('type_line',sf.get('type_line','')),
                face.get('oracle_text',sf.get('oracle_text','')),
            )
        ):
            im=decode_image(self.store.asset_path(asset['id']).read_bytes())
            if im.height<=(
                ingest.SAGA_CREATURE_RULES_ART_TRIM_TOP
                + ingest.SAGA_CREATURE_RULES_ART_TRIM_BOTTOM
            ):
                raise ValidationError('Saga-creature artwork is too short for the approved Scryfall trim.')
            im=im.crop((
                0,
                ingest.SAGA_CREATURE_RULES_ART_TRIM_TOP,
                im.width,
                im.height-ingest.SAGA_CREATURE_RULES_ART_TRIM_BOTTOM,
            ))
            out=io.BytesIO();im.save(out,'PNG')
            asset=ingest_image(self.store,out.getvalue())
            # The prepared pixels are now the authoritative art source for this
            # face; do not export/reload the untrimmed Scryfall URL.
            url=None
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
    @staticmethod
    def _deck_token_spec(settings,comp):
        """Translate deck-wide token options to the preserved Card Tools token spec."""
        if not settings.get('allCardsTokens'):return None
        options=settings.get('tokenOptions') or {}
        spec={'output_key':str(comp.get('name') or ''),'token_key_suffix':''}
        style=settings.get('templateRules',{}).get('token')
        if style in {'token-classic','token-full-art','token-borderless'}:spec['token_frame_style']=style
        if settings.get('templateRules',{}).get('token')=='godzilla-card':spec['force_nickname_frame']=True
        if options.get('legendaryMode','nonlegendary' if options.get('nonlegendary') else 'original')=='nonlegendary':spec['nonlegendary']=True
        if options.get('legendaryMode')=='legendary':spec['force_legendary']=True
        if options.get('subtypes'):spec['replace_creature_subtypes']=options['subtypes']
        power=str(options.get('power') or '')
        toughness=str(options.get('toughness') or '')
        if power or toughness:
            current=str((((comp.get('data') or {}).get('text') or {}).get('pt') or {}).get('text') or '')
            if '/' in current:
                current_power,current_toughness=current.split('/',1)
            else:
                current_power,current_toughness=current,''
            spec['power_toughness']=(power or current_power)+'/'+(toughness or current_toughness)
        return spec

    def _apply_token_spec(self,comp,spec,art_id,recipe_label,autofit=True,sem=None):
        spec=dict(spec)
        style=spec.pop('token_frame_style',None)
        if sem:
            sem=dict(sem)
            if spec.get('nonlegendary'):sem['legendary']=False
            if spec.get('force_legendary'):sem['legendary']=True
        if sem and not spec.get('frame_color'):
            code=frame_treatment_code(sem)
            spec['frame_color']=code if isinstance(code,str) and code in 'WUBRGMAL' else 'A'
        if spec.pop('force_legendary',False):
            type_text=comp['data'].setdefault('text',{}).setdefault('type',{})
            current=str(type_text.get('text') or '')
            if not current.startswith('Legendary '):type_text['text']='Legendary '+current
        try:entry=tokens.build_token({'key':comp['name'],'data':comp['data']},spec)
        except (Exception,SystemExit) as exc:raise ValidationError('Token conversion could not be applied: '+str(exc)) from exc
        comp['data']=entry['data'];comp['name']=entry['key'];comp['group']='token';comp['recipe']=recipe_label
        if style:
            short=token_has_short_text({'oracle_text':comp['data']['text']['rules']['text']})
            configure_token_style(comp['data'],spec.get('frame_color','A'),style,short)
            if comp.get('symbolId'):fit_set_symbol_to_bounds(comp['data'],self.store.asset(comp['symbolId']),recipe_label)
        fit_token_art(comp['data'],str(self.store.asset_path(art_id)),autofit)
        if sem and (sem.get('nickname') or spec.get('force_nickname_frame') or str(comp.get('templateKey') or '').startswith('builtin:godzilla-')):
            apply_nickname_treatment(comp['data'],sem,'token',
                                     force=bool(spec.get('force_nickname_frame')) or str(comp.get('templateKey') or '').startswith('builtin:godzilla-'),
                                     full_frame=bool(spec.get('force_nickname_frame')) or str(comp.get('templateKey') or '').startswith('builtin:godzilla-'))
            if comp['data'].get('version')=='m15Nickname':comp['data'].update(full_art_nonland_placement(self.store.asset(art_id)))
            if comp.get('symbolId') and comp['data'].get('version')=='m15Nickname':
                fit_set_symbol_to_bounds(comp['data'],self.store.asset(comp['symbolId']),'m15_nickname')
        if style=='token-full-art' and comp['data'].get('version')!='m15Nickname':apply_modern_token_text(comp['data'])
        elif comp['data'].get('version') not in {'tokenRegularM15','tokenTextlessM15'} or not style:apply_full_art_text(comp['data'])
        art=self.store.asset(art_id)
        if art:comp['crop']=crop_metrics(art['width'],art['height'],comp['data'])
        comp['renderKey']=render_key(comp['data'],art_id,comp.get('templateCacheVersion',1));comp['render']=None
        return comp

    @timed('card.prepare')
    def _prepare_card_faces(self,d,c,s,index,progress,cancel,done,total):
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
                art_id,origin,url=self._art(sf,face,f,s,index)
                options=copy.deepcopy(f)
                flavor_face=ingest.select_matching_flavor_face(flavor_sf,face,f.get('index',0))
                overrides=options.setdefault('semanticOverrides',{})
                if f.get('officialRulesText') is not None:
                    overrides.setdefault('oracle_text',f['officialRulesText'])
                official_flavor=f.get('officialFlavorText')
                flavor=str(ingest.face_value(flavor_face,flavor_sf,'flavor_text','') or '') if official_flavor is None else official_flavor
                overrides.setdefault('flavor_text',flavor)
                if not s.get('showFlavorText',True):overrides['flavor_text']=''
                if sf.get('layout') in {'flip','prepare'} and len(sf_faces)==2:
                    nested='flip_face' if sf['layout']=='flip' else 'prepared_spell'
                    secondary_flavor=ingest.select_matching_flavor_face(flavor_sf,sf_faces[1],1)
                    options['nestedFlavorTexts']={nested:str(ingest.face_value(secondary_flavor,flavor_sf,'flavor_text','') or '') if s.get('showFlavorText',True) else ''}
                comp=self.compiler.compile_face(sf,face,f.get('index',0),options,s,art_id,art_origin=origin)
                if c.get('tokenSpec'):
                    token_sem=semantic(sf,face,f.get('index',0))
                    token_sem.update({k:v for k,v in options.get('semanticOverrides',{}).items() if k in {'nickname','flavor_text'}})
                    comp=self._apply_token_spec(comp,c['tokenSpec'],art_id,'Card Tools copy token',not s.get('disableAutofit',False),token_sem)
                deck_token_spec=self._deck_token_spec(s,comp)
                if deck_token_spec:
                    token_sem=semantic(sf,face,f.get('index',0))
                    token_sem.update({k:v for k,v in options.get('semanticOverrides',{}).items() if k in {'nickname','flavor_text'}})
                    comp=self._apply_token_spec(comp,deck_token_spec,art_id,'Deck-wide token',not s.get('disableAutofit',False),token_sem)
                content_key=comp['renderKey']
                comp['contentRenderKey']=content_key
                comp['renderKey']=stable_hash({'content':content_key,'deck':d['id'],'face':f['id']})
                comp['render']=self.store.render_get(comp['renderKey'])
                comp['artOrigin']=origin;comp['exportArtUrl']=url;f['compiled']=comp
            except (ValidationError,native.BuildError,ValueError,OSError) as e:
                self.invalidate_face(f);f['error']=str(e)
            done+=1;progress(done,total,'Prepared '+f['name'])
        return done
    def _prepare_sources(self,s,progress):
        index={}
        if s['source']['mode']=='github':
            if not s['source'].get('githubFolder'):raise ValidationError('Provide the GitHub art folder.')
            progress(0,1,'Reading GitHub artwork folder');index=self.sources.github_index(s['source']['githubFolder'],s['source'].get('ref') or None,refresh=True)
        if s['source']['mode']=='local':index=s['source'].get('localFiles',{})
        return ArtworkIndex(index,s['source'].get('localNames'))
    @timed('deck.prepare')
    def prepare(self,ident,progress=lambda *a:None,cancel=lambda:False):
        steps=self.prepare_steps(ident,progress,cancel)
        while True:
            try:next(steps)
            except StopIteration as finished:return finished.value

    def prepare_steps(self,ident,progress=lambda *a:None,cancel=lambda:False):
        if self.deck(ident).get('pendingImport'):yield from self.resolve_metadata_steps(ident,progress,cancel)
        d=self.deck(ident);rev=d['revision'];s=self.validate_settings(d['settings'])
        if any(not s['symbols'].get(r) for r in RARITIES):raise ValidationError('Set up all four rarity symbols before preparing the deck.')
        self._apply_card_data(d,d.get('cardData',[]))
        index=self._prepare_sources(s,progress)
        yield
        total=sum(len(c['faces']) for c in d['cards']);done=0
        for c in d['cards']:
            done=self._prepare_card_faces(d,c,s,index,progress,cancel,done,total)
            # Checkpoint preparation so cancellation/reload preserves finished faces.
            d.pop('summary',None);saved=self.store.put('decks',d,rev);rev=saved['revision']
            yield
        if cancel():raise ValidationError('Preparation cancelled.')
        d['settings']=s;d['status']='prepared';d.pop('summary',None);d.pop('upgradeRequired',None)
        self.store.put('decks',d,rev);return self.deck(ident)
    @timed('card.prepare-single')
    def prepare_card(self,ident,card_id,progress=lambda *a:None,cancel=lambda:False):
        d=self.deck(ident);rev=d['revision'];s=self.validate_settings(d['settings'])
        if any(not s['symbols'].get(r) for r in RARITIES):raise ValidationError('Set up all four rarity symbols before preparing this card.')
        c=next((x for x in d['cards'] if x['id']==card_id),None)
        if not c:raise ValidationError('Card no longer exists.')
        index=self._prepare_sources(s,progress)
        self._prepare_card_faces(d,c,s,index,progress,cancel,0,len(c.get('faces',[])))
        # Recompute draft state from actual face data after this card is prepared.
        # Front-affecting edits clear their face's compiled data, so unrelated
        # pending cards remain draft while a fully prepared deck can leave draft.
        d['settings']=s;d['status']='prepared';d.pop('summary',None);d.pop('upgradeRequired',None)
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
    def template_preview_targets(self,deck_id,group,settings,card_data=None,choices=None):
        if group not in GROUP_LABELS:raise ValidationError('Unknown template group.')
        d=self.deck(deck_id)
        staged={entry['name']:entry for entry in self._validated_card_data(card_data)}
        candidates=[]
        for card in d.get('cards',[]):
            faces=ingest.face_list(card['scryfall'])
            for face_options in card.get('faces',[]):
                number=min(face_options.get('index',0),len(faces)-1)
                if type_group(faces[number],card['scryfall'],number)==group:
                    candidates.append((card,face_options,faces[number]))
        if not candidates:raise ValidationError('Add a card in this layout before previewing its frames.')
        sample=next((item for item in candidates if
                     (staged.get(item[2].get('name','')) or {}).get('nickname')
                     or (item[1].get('semanticOverrides') or {}).get('nickname')
                     or item[2].get('flavor_name')),candidates[0])
        s=self.validate_settings(settings)
        index=self._prepare_sources(s,lambda *args:None)
        card,face_options,_=sample
        sf=card['scryfall']
        faces=ingest.face_list(sf)
        face=faces[min(face_options.get('index',0),len(faces)-1)]
        art_id,origin,_=self._art(sf,face,face_options,s,index)
        options=copy.deepcopy(face_options)
        options['semanticOverrides']=dict(options.get('semanticOverrides') or {})
        if face_options.get('officialRulesText') is not None:
            options['semanticOverrides'].setdefault('oracle_text',face_options['officialRulesText'])
        options['semanticOverrides'].setdefault('flavor_text',str(ingest.face_value(face,sf,'flavor_text','') or ''))
        if not s.get('showFlavorText',True):options['semanticOverrides']['flavor_text']=''
        for key in ('nickname','flavor_text'):
            if key in staged.get(face.get('name',''),{}):
                options['semanticOverrides'][key]=staged[face['name']][key]
        targets=[];errors={};seen_previews={}
        legendary=is_legendary(face)
        for template in self.templates():
            if choices is not None and template['id'] not in choices:continue
            supported=template.get('groups')
            if template['id']!='auto' and not (supported=='ordinary' and group in ORDINARY_GROUPS or isinstance(supported,list) and group in supported):
                continue
            if legendary and not template.get('legendary',False):continue
            choice=template['id']
            try:
                compiled=self.compiler.compile_face(sf,face,face_options.get('index',0),
                    {**options,'templateOverride':choice},s,art_id,art_origin=origin)
                visual_key=stable_hash(compiled['data'])
                if visual_key in seen_previews:
                    seen_previews[visual_key]['choices'].append(choice)
                    continue
                target={'key':stable_hash({'preview':choice,'compiled':compiled['renderKey']}),
                        'name':template['name'],'choice':choice,'choices':[choice],
                        'data':compiled['data'],'preview':True}
                seen_previews[visual_key]=target
                targets.append(target)
            except (ValidationError,native.BuildError,ValueError,OSError) as exc:
                errors[choice]=str(exc)
        return {'targets':targets,'errors':errors,'sample':face.get('name',card['name'])}
    def save_template(self,value):
        if value.get('schemaVersion') in {2,3}:
            model=validate_model(value)
            if value.get('id') and value.get('revision') is None:
                raise ValidationError('Reload the template before saving; its revision is required.')
            saved={key:model[key] for key in ('format','schemaVersion','name','data','groups','legendary','baseGroup','regions','variants','layoutMetadata')}
            result=self.store.put('templates',{'id':value.get('id'),**saved},value.get('revision'))
            self.invalidate_template(result['id'])
            return result
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
        users=[]
        for deck in self.store.list('decks'):
            if ident in deck.get('settings',{}).get('templateRules',{}).values() or any(
                face.get('templateOverride')==ident for card in deck.get('cards',[]) for face in card.get('faces',[])):
                users.append(deck['name'])
        if users:raise ValidationError('This template is used by: '+', '.join(users[:20])+'. Change those decks before deleting it.')
        return self.store.purge('templates',ident,revision)
    def convert_template_source(self,value):
        return convert_cardconjurer(value.get('source'),value.get('name'),value.get('group','standard'))
    def export_template_file(self,ident):
        template=self.store.get('templates',ident)
        if template and template.get('schemaVersion') in {2,3}:template=validate_model(template)
        if not template:raise ValidationError('Template not found.')
        if template.get('schemaVersion') not in {2,3}:raise ValidationError('Convert this legacy template before exporting it.')
        from .backup import referenced_assets
        model={key:template[key] for key in ('format','schemaVersion','name','data','groups','legendary','baseGroup','regions','variants','layoutMetadata')}
        assets={}
        for asset_id in referenced_assets(model):
            image=self.store.asset(asset_id)
            if not image:raise ValidationError('Template frame image is missing: '+asset_id)
            assets[asset_id]={'mime':image['mime'],'base64':base64.b64encode(self.store.asset_path(asset_id).read_bytes()).decode('ascii')}
        model['assets']=assets
        return model
    def import_template_file(self,value):
        model=validate_model(value)
        from .backup import referenced_assets
        assets=model.pop('assets',{})
        if not isinstance(assets,dict) or len(assets)>200:raise ValidationError('Template assets are invalid.')
        for asset_id in referenced_assets(model):
            if self.store.asset(asset_id):continue
            image=assets.get(asset_id)
            if not isinstance(image,dict):raise ValidationError('Template frame image is missing: '+asset_id)
            raw=base64.b64decode(image.get('base64',''),validate=True)
            if len(raw)>64*1024**2 or hashlib.sha256(raw).hexdigest()!=asset_id:
                raise ValidationError('Template frame image failed its integrity check.')
            decoded=decode_image(raw)
            self.store.add_asset(raw,str(image.get('mime') or 'image/png'),decoded.width,decoded.height)
        model.pop('id',None);model.pop('revision',None)
        return self.save_template(model)
    def preview_template_model(self,value):
        model=validate_model(value)
        sample_names={'standard':'Seasoned Pyromancer','legendary':'Alesha, Who Smiles at Death',
                      'land':'Field of the Dead','legendary-land':'Boseiju, Who Endures','basic-land':'Forest'}
        sample_names.update({'station':'Seriema','prepare':'Harmonized Trio','planeswalker':'Jace, the Mind Sculptor','saga':'The Eldest Reborn','saga-creature':'The Kami War','token':'tmh2:16'})
        name=str(value.get('previewSource') or sample_names.get(model['baseGroup']) or '').strip()
        if not name:raise ValidationError('Enter a sample card for this structural layout before generating template previews.')
        sf=self.sources.resolve_card(name)
        faces=ingest.face_list(sf);index=next((i for i,face in enumerate(faces) if type_group(face,sf,i)==model['baseGroup']),None)
        if index is None:raise ValidationError('The sample card does not use the selected base layout.')
        face=faces[index]
        original_sf=copy.deepcopy(sf)
        sf=copy.deepcopy(sf);face=(sf.get('card_faces') or [sf])[index]
        requested=value.get('previewCondition') or {}
        if 'colors' in requested:face['colors']=requested['colors'];sf['colors']=requested['colors']
        if 'legendary' in requested:
            face['type_line']=face['type_line'].removeprefix('Legendary ')
            if requested['legendary']:face['type_line']='Legendary '+face['type_line']
        if 'hasPT' in requested:
            if requested['hasPT']:face['power']=face.get('power') or '3';face['toughness']=face.get('toughness') or '3'
            else:
                face.pop('power',None);face.pop('toughness',None)
                if model['baseGroup'] in ORDINARY_GROUPS:face['type_line']=face['type_line'].replace('Creature','Artifact')
        url=self.sources.art_url(original_sf,ingest.face_list(original_sf)[index])
        raw,_,_=self.net.fetch(url)
        art=ingest_image(self.store,raw)['id']
        temp=uid()
        self.store.put('templates',{'id':temp,**{key:model[key] for key in
            ('format','schemaVersion','name','data','groups','legendary','baseGroup','regions','variants','layoutMetadata')}})
        try:
            overrides={'oracle_text':'Whenever this creature attacks, draw a card, then discard a card.\n'
                         'When you discard a nonland card this way, create two 1/1 colorless artifact creature tokens.\n'
                         'At the beginning of your end step, if you control seven or more permanents, gain 3 life.'}
            if model['baseGroup'] not in ORDINARY_GROUPS:overrides={}
            compiled=self.compiler.compile_face(sf,face,index,{'templateOverride':temp,'semanticOverrides':overrides},
                                               self.validate_settings({}),art,art_origin='Scryfall selected printing')
            return {'data':compiled['data'],'sample':name}
        finally:
            self.store.purge('templates',temp)
    def preview_template_models(self,value,progress=lambda *a:None,cancel=lambda:False):
        model=validate_model(value);sources=value.get('previewSources') or {}
        if not isinstance(sources,dict) or any(group not in model['groups'] or not isinstance(source,str) for group,source in sources.items()):
            raise ValidationError('Preview sources must map supported groups to card names or printing IDs.')
        cases=[(group,{},group) for group in model['groups']]
        for index,variant in enumerate(model.get('variants') or []):
            when=variant.get('when') or {};group=when.get('group',model['baseGroup'])
            if when.get('legendary') is True and group in {'standard','land'}:
                candidate='legendary' if group=='standard' else 'legendary-land'
                if candidate not in model['groups']:raise ValidationError('Legendary variants need a supported legendary group.')
                group=candidate
            cases.append((group,when,'Variant '+str(index+1)+' / '+group))
        previews=[]
        for index,(group,condition,label) in enumerate(cases):
            if cancel():raise ValidationError('Template preview cancelled.')
            progress(index,len(cases),'Checking '+label)
            options={**value,'baseGroup':group,'previewCondition':condition,
                     'previewSource':sources.get(group) or (value.get('previewSource') if group==model['baseGroup'] else '')}
            preview=self.preview_template_model(options);preview['sample']=label+' / '+preview['sample'];previews.append(preview)
        progress(len(cases),len(cases),'Template layouts checked')
        return previews

    def template_seed(self,kind='normal'):
        if kind in {'token-classic','token-full-art','token-borderless'}:
            sem={'name':'My token template','types':['Creature'],'subtypes':['Beast'],'legendary':False,
                 'colors':['G'],'layout':'creature','oracle_text':'Flying','flavor_text':'','mana_cost':'','rarity':'common',
                 'set_symbol_source':'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYGD4DwABBAEAHnOcQAAAAABJRU5ErkJggg==',
                 'power':'3','toughness':'3','art':'/img/black.png','art_local_path':'','printed_type_line':'Token Creature — Beast'}
            return build_token_data(sem,'',False,[],kind)[1]
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

    @timed('render.persist')
    def save_render(self,target,raw,expected_size):
        if isinstance(target,str):target=self._render_target_from_key(target)
        if target.get('deckId') and not self.store.get('decks',target['deckId']):
            raise ValidationError('This deck was deleted. Its images cannot be saved.')
        with self.store.render_save():
            asset=ingest_render_png(self.store,raw,expected_size)
            result=self.store.render_put(target['key'],asset,deck_id=target.get('deckId'),card_id=target.get('cardId'),face_id=target.get('faceId'),deck_name=target.get('deckName') or 'Deck',face_name=target.get('name') or target.get('cardName') or 'Card')
        return result
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
        steps=self.original_images_steps(ident,progress,cancel)
        while True:
            try:next(steps)
            except StopIteration as finished:return finished.value
    def original_images_steps(self,ident,progress=lambda *a:None,cancel=lambda:False):
        d=self.deck(ident);out=self.store.home/'orders'/('originals-'+uid()+'.zip');names=set();count=0
        complete=False
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
                        yield
            if cancel():raise ValidationError('Image export cancelled.')
            complete=True
            return {'filename':out.name,'count':count,'bytes':out.stat().st_size,'download':'/api/files/'+out.name}
        finally:
            if not complete:out.unlink(missing_ok=True)

    def cropped_art(self,ident,progress=lambda *a:None,cancel=lambda:False):
        steps=self.cropped_art_steps(ident,progress,cancel)
        while True:
            try:next(steps)
            except StopIteration as finished:return finished.value
    def cropped_art_steps(self,ident,progress=lambda *a:None,cancel=lambda:False):
        """Download Scryfall art_crop files for the deck without modifying bytes."""
        d=self.deck(ident)
        entries=[]
        for c in d.get('cards',[]):
            sf=c.get('scryfall') or {}
            faces=sf.get('card_faces') or [sf]
            # Single-image layouts (ordinary, split, adventure, etc.) expose the
            # selected printing's art crop at the card level. True DFCs expose
            # one art_crop per face instead.
            if (sf.get('image_uris') or {}).get('art_crop'):
                faces=[sf]
            for face in faces:
                url=(face.get('image_uris') or {}).get('art_crop')
                if not url:
                    raise ValidationError(
                        str(c.get('name') or face.get('name') or 'Card')
                        +': selected Scryfall printing has no cropped artwork.'
                    )
                entries.append((c,sf,face,url))
        if not entries:
            raise ValidationError(d['name']+': this deck has no Scryfall cropped artwork to export.')

        stem=slug(d['name'])[:80] or 'deck'
        out=self.store.home/'orders'/('BulkProxyForge_Cropped_Art_'+stem+'_'+uid()[:8]+'.zip')
        used=set();count=0

        def extension(url,mime):
            suffix=PurePosixPath(str(url).split('?',1)[0]).suffix.lower()
            if suffix in {'.jpg','.jpeg','.png','.webp','.gif'}:
                return suffix
            kind=str(mime or '').split(';',1)[0].strip().lower()
            return {
                'image/jpeg':'.jpg',
                'image/png':'.png',
                'image/webp':'.webp',
                'image/gif':'.gif',
            }.get(kind,'.img')

        def unique_name(value,ext,sf,card_id):
            base=display_name(value,'Card')
            name=base+ext
            if name.casefold() not in used:
                used.add(name.casefold());return name
            extra=display_name(
                str(sf.get('set',''))+' '+str(sf.get('collector_number',''))+' '+str(card_id or '')[:8],
                'copy'
            )
            number=2
            candidate=base+' '+extra+ext
            while candidate.casefold() in used:
                candidate=f'{base} {extra} ({number}){ext}';number+=1
            used.add(candidate.casefold());return candidate

        complete=False
        try:
            with zipfile.ZipFile(out,'w',zipfile.ZIP_STORED,allowZip64=True) as archive:
                total=len(entries)
                for c,sf,face,url in entries:
                    if cancel():raise ValidationError('Cropped-art export cancelled.')
                    raw,mime,_=self.net.fetch_transient(url)
                    if not str(mime or '').lower().startswith('image/'):
                        raise ValidationError(
                            str(face.get('name') or c.get('name') or 'Card')
                            +': Scryfall cropped-art URL did not return an image.'
                        )
                    ext=extension(url,mime)
                    name=unique_name(
                        face.get('name') or c.get('name') or 'Card',
                        ext,sf,c.get('id')
                    )
                    # Write the response body exactly as received from Scryfall:
                    # no decode, crop, resize, rotation, or re-encoding.
                    archive.writestr(name,raw)
                    count+=1
                    progress(count,total,'Downloaded cropped art for '+str(face.get('name') or c.get('name') or 'Card'))
                    yield
            if cancel():raise ValidationError('Image export cancelled.')
            complete=True
            return {'filename':out.name,'count':count,'bytes':out.stat().st_size,'download':'/api/files/'+out.name}
        finally:
            if not complete:out.unlink(missing_ok=True)

    def _review_render(self,face,deck_name):
        if face.get('error'):raise ValidationError(deck_name+' / '+face['name']+': '+face['error'])
        render=self.store.render_get((face.get('compiled') or {}).get('renderKey',''))
        if not render:raise ValidationError(deck_name+' / '+face['name']+': render is missing or out of date.')
        return render

    def _review_composite(self,reference_url,render,refresh=False):
        # Review references are temporary export inputs. Do not retain hundreds
        # of full-resolution Scryfall card PNGs in the workspace cache.
        raw,_,_=self.net.fetch_transient(reference_url)
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
        steps=self.review_images_steps(ident,progress,cancel)
        while True:
            try:next(steps)
            except StopIteration as finished:return finished.value
    def review_images_steps(self,ident,progress=lambda *a:None,cancel=lambda:False):
        d=self.deck(ident)
        if d.get('status')=='draft':raise ValidationError(d['name']+': prepare the latest changes before downloading review images.')
        stem=slug(d['name'])[:80] or 'deck'
        out=self.store.home/'orders'/('BulkProxyForge_Review_Images_'+stem+'_'+uid()[:8]+'.zip')
        names=set();refresh=bool(d.get('settings',{}).get('refreshData',False))
        dfc_layouts={'transform','modal_dfc','double_faced_token','reversible_card'}

        def unique_name(face_name,sf,card_id):
            base=slug(face_name) or 'card';name=base+'_review.png'
            if name in names:
                suffix=slug(str(sf.get('set',''))+'_'+str(sf.get('collector_number',''))+'_'+card_id[:8])
                name=base+'_'+suffix+'_review.png'
            names.add(name);return name

        items=[]
        for c in d['cards']:
            sf=c['scryfall'];faces=c.get('faces') or []
            if not faces:raise ValidationError(c['name']+': card has no renderable face.')
            sf_faces=sf.get('card_faces') or [sf]
            front_sf=sf if (sf.get('image_uris') or {}).get('png') else sf_faces[0]
            front_url=(front_sf.get('image_uris') or {}).get('png')
            if not front_url:raise ValidationError(c['name']+': selected printing has no full-card PNG for the front.')
            front=faces[0]
            items.append((unique_name(front.get('name',c['name']),sf,c['id']),front.get('name',c['name']),front_url,self._review_render(front,d['name'])))
            if sf.get('layout') in dfc_layouts and len(faces)>=2:
                if len(sf_faces)<2:raise ValidationError(c['name']+': selected printing is missing its reverse face.')
                back_url=(sf_faces[1].get('image_uris') or {}).get('png')
                if not back_url:raise ValidationError(c['name']+': selected printing has no full-card PNG for the reverse face.')
                back=faces[1]
                items.append((unique_name(back.get('name',c['name']+' back'),sf,c['id']),back.get('name',c['name']),back_url,self._review_render(back,d['name'])))

        total=len(items)
        if not total:raise ValidationError(d['name']+': deck has no review images to export.')
        progress(0,total,'Preparing '+str(total)+' review images…')
        count=0
        complete=False
        try:
            #Keep downloads serial; yield between saved images so browser API
            #requests can run without bursting Scryfall's image CDN.
            with self.store.pin_assets(item[3]['asset_id'] for item in items),zipfile.ZipFile(out,'w',zipfile.ZIP_STORED,allowZip64=True) as z:
                for filename,label,url,render in items:
                    if cancel():raise ValidationError('Review-image export cancelled.')
                    progress(count,total,'Downloading review image for '+label)
                    z.writestr(filename,self._review_composite(url,render,refresh))
                    count+=1;progress(count,total,'Saved review image for '+label)
                    yield
            if cancel():raise ValidationError('Image export cancelled.')
            complete=True
            return {'filename':out.name,'count':count,'bytes':out.stat().st_size,'download':'/api/files/'+out.name}
        finally:
            if not complete:out.unlink(missing_ok=True)

