"""Preserved Card Tools utilities, available without creating a managed deck."""
from __future__ import annotations
import copy,json,os,zipfile
from .domain import ValidationError,uid,validate_template
from .legacy import tokens,image_tools
from .images import decode_image

class CardTools:
    def __init__(self,workspace):self.ws=workspace;self.store=workspace.store
    def copy_tokens(self,payload):
        entries=payload.get('entries');specs=payload.get('specs')
        if not isinstance(entries,list) or not entries or len(entries)>2000:raise ValidationError('Upload a .cardconjurer file containing 1–2,000 faces.')
        if not isinstance(specs,list) or not specs or len(specs)>500:raise ValidationError('Add 1–500 copy-token specifications.')
        by_key={}
        for e in entries:
            if not isinstance(e,dict) or not e.get('key'):raise ValidationError('Invalid CardConjurer entry.')
            validate_template(e)
            if e['key'] in by_key:raise ValidationError('The source save has duplicate card keys: '+e['key'])
            by_key[e['key']]=e
        out=[] if payload.get('tokensOnly') else copy.deepcopy(entries)
        used={e['key'] for e in out}
        allowed={'source_name','nonlegendary','replace_creature_subtypes','power_toughness','frame_color','color_override','token_key_suffix','title_override','output_key'}
        for raw_spec in specs:
            if not isinstance(raw_spec,dict):raise ValidationError('Each token row must be an object.')
            spec={k:v for k,v in raw_spec.items() if k in allowed};key=spec.get('source_name')
            if key not in by_key:raise ValidationError('Source card not found: '+str(key))
            try:e=tokens.build_token(by_key[key],spec)
            except (Exception,SystemExit) as exc:raise ValidationError('Could not create copy token for '+key+': '+str(exc)) from exc
            if e['key'] in used:raise ValidationError('A token key is duplicated. Change the suffix: '+e['key'])
            used.add(e['key']);out.append(e)
        return json.dumps(out,ensure_ascii=False,separators=(',',':')).encode()
    def originals(self,payload,progress=lambda *a:None,cancel=lambda:False):
        source=payload.get('source','');refresh=bool(payload.get('refreshData') or self.ws.global_settings().get('refreshData'))
        if isinstance(source,str):
            text=source.strip()
            if text.startswith('{'):
                try:source=json.loads(text)
                except ValueError as exc:raise ValidationError('Invalid deck export JSON.') from exc
            else:
                try:url=image_tools.deck_export_url(text)
                except ValueError as exc:raise ValidationError(str(exc)) from exc
                # Deck exports are mutable; always fetch the current list.
                progress(0,1,'Fetching one Scryfall deck export');source=self.ws.net.json(url,ttl=0)
        if not isinstance(source,dict):raise ValidationError('Provide a Scryfall deck link or deck JSON export.')
        entries=[];seen=set()
        try:
            for section,row in image_tools.iter_entries(source,None,bool(payload.get('includeOutside'))):
                for name,url,_ in image_tools.choose_digest_png_downloads(row.get('card_digest') or {}):
                    if url not in seen:seen.add(url);entries.append((name,url))
        except (RuntimeError,ValueError) as exc:raise ValidationError(str(exc)) from exc
        if not entries:raise ValidationError('No downloadable printing images in this export.')
        if len(entries)>10000:raise ValidationError('Split exports larger than 10,000 faces.')
        dest=self.store.home/'orders'/('originals-'+uid()+'.zip');tmp=dest.with_suffix('.partial');used=set()
        try:
            with zipfile.ZipFile(tmp,'w',zipfile.ZIP_STORED) as z:
                for i,(name,url) in enumerate(entries):
                    if cancel():raise ValidationError('Original image download cancelled.')
                    progress(i,len(entries),'Downloading '+name)
                    raw,mime,_=self.ws.net.fetch(url,refresh=refresh);decode_image(raw)
                    filename=image_tools.uniquify_filename(image_tools.snake_slug(name),used);z.writestr(filename,raw)
            os.replace(tmp,dest);progress(len(entries),len(entries),'Original printing images saved')
            return {'count':len(entries),'bytes':dest.stat().st_size,'download':'/api/files/'+dest.name,'filename':dest.name}
        except Exception:tmp.unlink(missing_ok=True);dest.unlink(missing_ok=True);raise
