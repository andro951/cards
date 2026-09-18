"""Exact-printing Scryfall imports and explicit GitHub art folders."""
from __future__ import annotations
import json,re
from urllib.parse import quote,urlsplit
from .domain import ValidationError,parse_deck_text,quantity,uid,github_location,slug
from .legacy import deck_parser,ingest
class Sources:
    def __init__(self,network):self.net=network
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
    def import_deck(self,source,include_outside=False,refresh=False,progress=lambda *a:None,cancel=lambda:False):
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
        elif isinstance(source,list):
            manifest=[]
            for r in source:
                if not isinstance(r,dict):raise ValidationError('Card import rows must be objects.')
                manifest.append({'source':r.get('id') or r.get('source') or r.get('name'),'quantity':quantity(r.get('quantity',1)),'section':r.get('section','mainboard')})
        elif isinstance(source,str):manifest=parse_deck_text(source,include_outside)
        else:raise ValidationError('Upload a Scryfall export, paste a public deck link or card names.')
        if not manifest:raise ValidationError('No cards were supplied.')
        if sum(r['quantity'] for r in manifest)>10000:raise ValidationError('Deck limit is 10,000 physical cards.')
        seen={};cards=[];resolved={}
        for i,row in enumerate(manifest):
            if cancel():raise ValidationError('Import cancelled.')
            progress(i,len(manifest),'Resolving selected printing '+str(row['source']))
            key=str(row['source'])
            sf=resolved.setdefault(key,self.resolve_card(key,refresh)) if key not in resolved else resolved[key]
            identity=(sf['id'],row['section'])
            if identity in seen:seen[identity]['quantity']=quantity(seen[identity]['quantity']+row['quantity']);continue
            entry=self.entry(sf,row['quantity'],row['section']);entry['digest']=digests.get(sf['id'],{})
            entry['sourceIsExact']=bool(re.fullmatch(r'[0-9a-fA-F-]{36}',key) or re.fullmatch(r'[A-Za-z0-9]+:[A-Za-z0-9★†-]+',key) or key.startswith('https://'))
            seen[identity]=entry;cards.append(entry)
        progress(len(manifest),len(manifest),'Selected printings imported')
        return {'name':str(title),'cards':cards,'importedSource':original}
    def entry(self,sf,count=1,section='mainboard'):
        entry={'id':uid(),'name':sf['name'],'quantity':quantity(count),'section':section,'scryfall':sf,'faces':[]}
        faces=ingest.face_list(sf)
        if sf.get('layout') in {'split','adventure','flip','prepare'}:faces=faces[:1]
        for i,f in enumerate(faces):entry['faces'].append({'id':uid(),'name':f.get('name',sf['name']),'index':i,'artistOverride':None,'artOverride':None,'templateOverride':None})
        return entry
    def art_url(self,sf,face):return ingest.scryfall_art_crop_url(sf,face)
    def github_index(self,url,branch=None,refresh=False):
        loc=github_location(url,branch)
        if loc['default_ref']:loc['ref']=self.net.json('https://api.github.com/repos/'+loc['repo'],ttl=0 if refresh else 600).get('default_branch','main')
        api='https://api.github.com/repos/'+loc['repo']+'/contents/'+quote(loc['folder'],safe='/')+'?ref='+quote(loc['ref'],safe='')
        rows=self.net.json(api,ttl=0 if refresh else 600)
        if not isinstance(rows,list):raise ValidationError('That GitHub link is a file, not an artwork folder.')
        index={}
        for r in rows:
            if r.get('type')=='file' and re.search(r'\.(png|jpe?g|webp|gif)$',r.get('name',''),re.I):
                stem=slug(r['name'].rsplit('.',1)[0])
                if stem in index:raise ValidationError('Ambiguous filenames in GitHub folder: '+r['name'])
                index[stem]='https://raw.githubusercontent.com/'+loc['repo']+'/'+quote(loc['ref'],safe='')+'/'+quote(r['path'],safe='/')
        return index
    def printings(self,name,refresh=False,next_page=None):
        url=next_page or 'https://api.scryfall.com/cards/search?unique=prints&order=released&q='+quote('!"'+name.replace('"','')+'" game:paper')
        if not url.startswith('https://api.scryfall.com/cards/search?'):raise ValidationError('Invalid printings page.')
        d=self.net.json(url,refresh=refresh)
        return {'data':d.get('data',[]),'has_more':d.get('has_more',False),'next_page':d.get('next_page')}

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