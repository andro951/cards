"""Printing-preserving Scryfall imports and explicit GitHub artwork folders."""
from __future__ import annotations
import json,re
from urllib.parse import quote,urlsplit,unquote
from .domain import ValidationError,parse_deck_text,quantity,uid,github_location,slug
from .legacy import deck_parser,ingest,image_tools

class Sources:
    def __init__(self,network):self.net=network
    def resolve_card(self,source,refresh=False):
        source=str(source).strip();parsed=ingest.parse_scryfall_source(source)
        if parsed:
            path='/'.join(quote(x,safe='') for x in parsed[1:])
        elif re.fullmatch(r'[0-9a-fA-F-]{36}',source):path=source
        elif re.fullmatch(r'[A-Za-z0-9]+:[A-Za-z0-9★†-]+',source):path='/'.join(quote(x,safe='') for x in source.split(':',1))
        else:path='named?exact='+quote(source)
        data=self.net.json('https://api.scryfall.com/cards/'+path,refresh=refresh)
        if not isinstance(data,dict) or not data.get('name') or not data.get('id'):raise ValidationError('Scryfall did not return a card for '+source)
        if data.get('digital'):raise ValidationError(data['name']+' is a digital-only card. Choose a paper printing.')
        return data
    def import_deck(self,source,include_outside=False,refresh=False,progress=lambda *a:None):
        if isinstance(source,str):
            text=source.strip()
            if text.startswith(('{','[')):
                try:source=json.loads(text)
                except ValueError as exc:raise ValidationError('Invalid deck-export JSON.') from exc
            elif re.match(r'^https://(?:www\.)?scryfall\.com/@[^/]+/decks/',text):
                source=self.net.json(deck_parser.deck_export_url(deck_parser.extract_deck_uuid(text)),refresh=refresh)
        title='New deck';manifest=[];digests={}
        if isinstance(source,dict) and 'entries' in source:
            try:_,rows=deck_parser.extract_card_sources(source,include_outside_the_game=include_outside)
            except Exception as exc:raise ValidationError(str(exc)) from exc
            title=source.get('name') or source.get('title') or title
            for rows0 in source['entries'].values():
                for row in rows0 if isinstance(rows0,list) else []:
                    d=row.get('card_digest') or {};digests[d.get('id')]=d
            manifest=[{'source':r['scryfall_id'],'quantity':quantity(r['count']),'section':r['section']} for r in rows]
        elif isinstance(source,list):
            for r in source:
                if not isinstance(r,dict):raise ValidationError('Card import rows must be objects.')
                manifest.append({'source':r.get('id') or r.get('source') or r.get('name'),'quantity':quantity(r.get('quantity',1)),'section':r.get('section','mainboard')})
        elif isinstance(source,str):manifest=parse_deck_text(source,include_outside)
        else:raise ValidationError('Upload a Scryfall deck export, paste a public deck link or paste card names.')
        if sum(r['quantity'] for r in manifest)>10000:raise ValidationError('Deck limit is 10,000 physical cards.')
        seen={};cards=[]
        for i,row in enumerate(manifest):
            progress(i,len(manifest),'Resolving selected printing '+str(row['source']))
            sf=self.resolve_card(row['source'],refresh)
            identity=(sf['id'],row['section'])
            if identity in seen:seen[identity]['quantity']=quantity(seen[identity]['quantity']+row['quantity']);continue
            entry={'id':uid(),'name':sf['name'],'quantity':row['quantity'],'section':row['section'],'scryfall':sf,'digest':digests.get(sf['id'],{}),'faces':[]}
            for index,face in enumerate(ingest.face_list(sf)):
                entry['faces'].append({'id':uid(),'name':face.get('name',sf['name']),'index':index,'artistOverride':None,'artOverride':None,'templateOverride':None})
            seen[identity]=entry;cards.append(entry)
        return {'name':str(title),'cards':cards,'importedSource':source if isinstance(source,str) else '[Scryfall export]'}
    def art_url(self,sf,face):return ingest.scryfall_art_crop_url(sf,face)
    def github_index(self,url,branch=None,refresh=False):
        loc=github_location(url,branch)
        if loc['default_ref']:
            meta=self.net.json('https://api.github.com/repos/'+loc['repo'],refresh=refresh)
            loc['ref']=meta.get('default_branch','main')
        api='https://api.github.com/repos/'+loc['repo']+'/contents/'+quote(loc['folder'],safe='/')+'?ref='+quote(loc['ref'],safe='')
        rows=self.net.json(api,refresh=refresh,ttl=0 if refresh else 600)
        if not isinstance(rows,list):raise ValidationError('That GitHub link is a file, not an artwork folder.')
        index={}
        for r in rows:
            if r.get('type')=='file' and re.search(r'\.(png|jpe?g|webp|gif)$',r.get('name',''),re.I):
                stem=slug(r['name'].rsplit('.',1)[0])
                if stem in index:raise ValidationError('Ambiguous filenames in GitHub folder: '+r['name'])
                index[stem]='https://raw.githubusercontent.com/'+loc['repo']+'/'+quote(loc['ref'],safe='')+'/'+quote(r['path'],safe='/')
        return index
    def printings(self,name,refresh=False):
        url='https://api.scryfall.com/cards/search?unique=prints&order=released&q='+quote('!"'+name.replace('"','')+'" game:paper')
        data=self.net.json(url,refresh=refresh)
        return {'data':data.get('data',[]),'has_more':data.get('has_more',False),'next_page':data.get('next_page')}
