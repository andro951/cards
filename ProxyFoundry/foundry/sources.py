"""Exact-printing Scryfall imports and explicit GitHub art folders."""
from __future__ import annotations
from .timing import timed,timing
import hashlib,json,re
from urllib.parse import quote,urlsplit
from .domain import ValidationError,parse_deck_text,quantity,uid,github_location,slug,type_group,stable_hash
from .legacy import deck_parser,ingest
class Sources:
    def __init__(self,network):self.net=network
    @timed('scryfall.resolve')
    def resolve_card(self,source,refresh=False):
        source=str(source).strip()
        try:parsed=ingest.parse_scryfall_source(source)
        except ingest.DataError as exc:raise ValidationError(str(exc)) from exc
        if parsed:path='/'.join(quote(x,safe='') for x in parsed[1:])
        elif re.fullmatch(r'[0-9a-fA-F-]{36}',source):path=source
        elif re.fullmatch(r'[A-Za-z0-9]+:[A-Za-z0-9★†-]+',source):path='/'.join(quote(x,safe='') for x in source.split(':',1))
        else:path='named?exact='+quote(source)
        d=self.net.json('https://api.scryfall.com/cards/'+path,refresh=refresh)
        if not isinstance(d,dict) or not d.get('name') or not d.get('id'):raise ValidationError('Scryfall did not return a card for '+source)
        # A digital Scryfall printing is still a valid source printing for a proxy.
        # Preserve the exact printing selected by the user instead of substituting
        # a paper version or rejecting the card solely because digital=true.
        canonical='https://api.scryfall.com/cards/'+d['id']
        original='https://api.scryfall.com/cards/'+path
        cached=self.net.store.cache_get(original)
        if cached and canonical!=original:
            asset=self.net.store.asset(cached['asset_id'])
            if asset:self.net.store.cache_put(canonical,asset,cached['fetched'])
        return self._expand_meld(d,refresh)
    def _expand_meld(self,d,refresh=False):
        if d.get('layout')!='meld':return d
        result=next((p for p in d.get('all_parts') or [] if p.get('component')=='meld_result'),None)
        if not result or result.get('id')==d.get('id'):return d
        card=self.resolve_card(result.get('id') or result.get('name',''),refresh)
        images=card.get('image_uris') or {}
        meld_result={k:card.get(k) for k in ('id','name','artist','set','collector_number','rarity') if card.get(k) is not None}
        meld_result['image_uris']={k:images[k] for k in ('png','large','normal','small') if images.get(k)}
        return {**d,'_meld_proxy':True,'_meld_result':meld_result}
    def import_deck(self,source,include_outside=True,refresh=False,progress=lambda *a:None,cancel=lambda:False):
        steps=self.import_deck_steps(source,include_outside,refresh,progress,cancel)
        while True:
            try:next(steps)
            except StopIteration as finished:return finished.value

    def import_deck_steps(self,source,include_outside=True,refresh=False,progress=lambda *a:None,cancel=lambda:False):
        with timing(self.net.store,'deck.import',source=source[:300] if isinstance(source,str) else '[Scryfall export]',refresh=refresh):
            return (yield from self._import_deck_steps(source,include_outside,refresh,progress,cancel))

    @timed('deck.list.fetch')
    def read_deck_manifest(self,source,include_outside=True,refresh=False,cancel=lambda:False,*,include_digests=False):
        if cancel():raise ValidationError('Import cancelled.')
        original=source if isinstance(source,str) else '[Scryfall export]'
        if isinstance(source,str):
            text=source.strip()
            if text.startswith(('{','[')):
                try:source=json.loads(text)
                except ValueError as exc:raise ValidationError('Invalid deck-export JSON.') from exc
            elif re.match(r'^https://(?:www\.)?scryfall\.com/@[^/]+/decks/',text):
                # A public deck export is mutable source data, not card metadata.
                # Always fetch it live so re-importing the same Scryfall URL sees
                # additions/removals immediately instead of the year/week cache.
                source=self.net.json(deck_parser.deck_export_url(deck_parser.extract_deck_uuid(text)),ttl=0)
            elif re.match(r'^https://(?:www\.)?(?:archidekt\.com/decks/\d+|mtggoldfish\.com/deck/\d+)(?:[/?#]|$)',text):
                source=self.net.json(text,ttl=0)
        title='New deck';digests={}
        if isinstance(source,dict) and 'entries' in source:
            try:_,rows=deck_parser.extract_card_sources(source,include_outside_the_game=include_outside)
            except Exception as exc:raise ValidationError(str(exc)) from exc
            title=source.get('name') or source.get('title') or title
            for rows0 in source['entries'].values():
                for row in rows0 if isinstance(rows0,list) else []:
                    if not isinstance(row,dict):continue
                    d=row.get('card_digest') or {};digests[d.get('id')]=d
            manifest=[{'source':r['scryfall_id'],'quantity':quantity(r['count']),'section':r['section']} for r in rows]
        elif isinstance(source,dict) and isinstance(source.get('rows'),list):
            title=source.get('name') or title
            manifest=[]
            for row in source['rows']:
                if not isinstance(row,dict):raise ValidationError('Deck source returned an invalid card row.')
                section=str(row.get('section') or 'mainboard')
                if not include_outside and section not in {'mainboard','commanders'}:continue
                manifest.append({'name':str(row.get('name') or ''), 'source':row.get('source'), 'quantity':quantity(row.get('quantity',1)), 'section':section})
        elif isinstance(source,list):
            manifest=[]
            for r in source:
                if not isinstance(r,dict):raise ValidationError('Card import rows must be objects.')
                manifest.append({'name':str(r.get('name') or ''), 'source':r.get('id') or r.get('source') or r.get('name'),'quantity':quantity(r.get('quantity',1)),'section':r.get('section','mainboard')})
        elif isinstance(source,str):manifest=parse_deck_text(source,include_outside)
        else:raise ValidationError('Upload a Scryfall export, paste a public deck link or card names.')
        if not manifest:raise ValidationError('No cards were supplied.')
        if sum(r['quantity'] for r in manifest)>10000:raise ValidationError('Deck limit is 10,000 physical cards.')
        for row in manifest:
            key=str(row.get('source') or '').strip()
            if not key:raise ValidationError('Every deck row needs a card name or printing identifier.')
            try:ingest.parse_scryfall_source(key)
            except ingest.DataError as exc:raise ValidationError(str(exc)) from exc
            row['source']=key
            row['name']=str(row.get('name') or digests.get(key,{}).get('name') or key)
        listing={'name':str(title),'rows':manifest,'importedSource':original}
        if include_digests:listing['digests']=digests
        return listing

    def _import_deck_steps(self,source,include_outside,refresh,progress,cancel):
        listing=self.read_deck_manifest(source,include_outside,refresh,cancel,include_digests=True)
        title=listing['name'];manifest=listing['rows'];original=listing['importedSource'];digests=listing['digests']
        #No deck is published until all rows are resolved; cached metadata is durable.
        yield
        seen={};cards=[];resolved={}
        for i,row in enumerate(manifest):
            if cancel():raise ValidationError('Import cancelled.')
            progress(i,len(manifest),'Resolving selected printing '+str(row['source']))
            key=str(row['source'])
            sf=resolved.setdefault(key,self.resolve_card(key,refresh)) if key not in resolved else resolved[key]
            identity=(sf['id'],row['section'])
            if identity in seen:seen[identity]['quantity']=quantity(seen[identity]['quantity']+row['quantity'])
            else:
                entry=self.entry(sf,row['quantity'],row['section']);entry['digest']=digests.get(sf['id'],{})
                entry['sourceIsExact']=bool(re.fullmatch(r'[0-9a-fA-F-]{36}',key) or re.fullmatch(r'[A-Za-z0-9]+:[A-Za-z0-9★†-]+',key) or key.startswith('https://'))
                seen[identity]=entry;cards.append(entry)
            progress(i+1,len(manifest),'Resolved selected printing '+sf['name'])
            yield
        if cancel():raise ValidationError('Import cancelled.')
        progress(len(manifest),len(manifest),'Selected printings imported')
        return {'name':str(title),'cards':cards,'importedSource':original}
    def entry(self,sf,count=1,section='mainboard'):
        entry={'id':uid(),'name':sf['name'],'quantity':quantity(count),'section':section,'scryfall':sf,'faces':[]}
        faces=ingest.face_list(sf)
        if sf.get('layout') in {'split','adventure','flip','prepare'}:faces=faces[:1]
        for i,f in enumerate(faces):entry['faces'].append({'id':uid(),'name':f.get('name',sf['name']),'index':i,'artistOverride':None,'artOverride':None,'templateOverride':None})
        return entry
    def art_url(self,sf,face):
        if sf.get('layout')=='art_series' or type_group(face,sf)=='helper':
            # Art Series and helper trackers use the complete printing image,
            # including special tracker layouts and both Day/Night faces.
            return (face.get('image_uris') or {}).get('png') or (sf.get('image_uris') or {}).get('png') or ''
        return ingest.scryfall_art_crop_url(sf,face)
    @staticmethod
    def git_blob_sha(raw):
        return hashlib.sha1(b'blob '+str(len(raw)).encode('ascii')+b'\0'+raw).hexdigest()
    def github_art(self,entry):
        if isinstance(entry,str):
            raw,_,_=self.net.fetch(entry,refresh=True,ttl=0)
            return raw,entry
        if not isinstance(entry,dict) or not isinstance(entry.get('url'),str):
            raise ValidationError('GitHub artwork index entry is invalid.')
        url=entry['url']
        if not re.fullmatch(r'https://raw\.githubusercontent\.com/[^/]+/[^/]+/[0-9a-fA-F]{40}/.+',url):
            raise ValidationError('GitHub artwork must use an exact commit URL.')
        raw,_,_=self.net.fetch(url,immutable=True)
        return raw,url
    @timed('github.index')
    def github_index(self,url,branch=None,refresh=False):
        loc=github_location(url,branch)
        if loc['default_ref']:loc['ref']=self.net.json('https://api.github.com/repos/'+loc['repo'],ttl=0 if refresh else 600).get('default_branch','main')
        requested=str(loc['ref'])
        if re.fullmatch(r'[0-9a-fA-F]{40}',requested):
            commit=requested.lower()
        else:
            resolved=self.net.json('https://api.github.com/repos/'+loc['repo']+'/commits/'+quote(requested,safe=''),ttl=0 if refresh else 600)
            commit=str(resolved.get('sha','')).lower() if isinstance(resolved,dict) else ''
            if not re.fullmatch(r'[0-9a-f]{40}',commit):
                raise ValidationError('GitHub did not return an exact commit for the artwork folder.')
        store=getattr(self.net,'store',None)
        cache_id=stable_hash({'repo':loc['repo'],'folder':loc['folder'],'ref':requested,'version':2})
        previous=store.get('github-art-index',cache_id) if store else None
        if previous and previous.get('commit')==commit:return previous['index']
        unchanged={}
        if previous:
            try:
                comparison=self.net.json('https://api.github.com/repos/'+loc['repo']+'/compare/'+previous['commit']+'...'+commit,immutable=True)
                files=comparison.get('files')
                # GitHub caps comparison files at 300; a capped or diverged
                # comparison cannot prove which of our assets are unchanged.
                if comparison.get('status')=='ahead' and isinstance(files,list) and len(files)<300 and all(isinstance(f,dict) and f.get('filename') and f.get('status') in {'added','modified','removed','renamed','copied','changed','unchanged'} for f in files):
                    changed={path for f in files for path in (f['filename'],f.get('previous_filename')) if path}
                    unchanged={e['path']:e for e in previous['index'].values() if e.get('path') not in changed}
            except (ValidationError,OSError):pass
        api='https://api.github.com/repos/'+loc['repo']+'/contents/'+quote(loc['folder'],safe='/')+'?ref='+commit
        rows=self.net.json(api,immutable=True)
        if not isinstance(rows,list):raise ValidationError('That GitHub link is a file, not an artwork folder.')
        index={}
        for r in rows:
            if r.get('type')=='file' and re.search(r'\.(png|jpe?g|webp|gif)$',r.get('name',''),re.I):
                stem=slug(r['name'].rsplit('.',1)[0]);base=stem;number=1
                while stem in index:
                    number+=1;stem=base+'__'+str(number)
                index[stem]=unchanged.get(r['path']) or {'url':'https://raw.githubusercontent.com/'+loc['repo']+'/'+commit+'/'+quote(r['path'],safe='/'),'path':r['path'],'commit':commit,'filename':r['name']}
        if store:store.put('github-art-index',{'id':cache_id,'commit':commit,'index':index})
        return index
    def printings(self,name,refresh=False,next_page=None):
        url=next_page or 'https://api.scryfall.com/cards/search?unique=prints&order=released&q='+quote('!"'+name.replace('"','')+'" game:paper')
        if not url.startswith('https://api.scryfall.com/cards/search?'):raise ValidationError('Invalid printings page.')
        d=self.net.json(url,refresh=refresh)
        return {'data':d.get('data',[]),'has_more':d.get('has_more',False),'next_page':d.get('next_page')}

    @timed('scryfall.flavor')
    def flavor_source(self,sf,policy='auto',source_exact=True,refresh=False):
        if policy=='resolved' or policy=='auto' and source_exact:return sf
        name=str(sf.get('name','')).replace('\\','\\\\').replace('"','\\"')
        url='https://api.scryfall.com/cards/search?unique=prints&order=released&dir=desc&q='+quote('!"'+name+'" game:paper lang:en')
        try:
            page=self.net.json(url,refresh=refresh)
            rows=page.get('data',[])
            return rows[0] if rows and isinstance(rows[0],dict) else sf
        except ValidationError:
            return sf
