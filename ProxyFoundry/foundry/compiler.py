"""Adapter over unchanged v54 templates. Overrides are opt-in, never automatic guesses."""
from __future__ import annotations
import copy,math
from .domain import ValidationError,ORDINARY_GROUPS,type_group,crop_metrics,render_key,RARITIES,GENERATION_VERSION
from .legacy import compiler as native,ingest
from .images import data_uri
from .credits import resolve_credit
BUILTINS=[
 {'id':'auto','name':'Card Tools · automatic','description':'Preserves every approved v54 type-specific recipe.','legendary':True,'groups':'all'},
 {'id':'normal','name':'Classic card','description':'Standard card frame, with a crown for legendary cards.','legendary':True,'groups':'ordinary'},
 {'id':'land','name':'Full-art land','description':'Existing nonlegendary land frame. No compatible crown.','legendary':False,'groups':'ordinary'},
 {'id':'legend-land','name':'Crowned full art','description':'Existing legendary-land frame; crown removed for nonlegendary cards.','legendary':True,'groups':'ordinary'}]
SINGLE_SURFACE={'adventure','split','flip','room','prepare'}
NEEDS_CUSTOM={'transform-front','transform-back','split','adventure','room','meld','art-series','planar','scheme','vanguard','token','emblem','battle','class','case','special-land','dungeon','conspiracy'}

def semantic(sf,face,index=0):
    get=lambda k,default='':ingest.face_value(face,sf,k,default)
    types=ingest.split_type_line(get('type_line'))
    d={**types,'name':get('name'),'mana_cost':get('mana_cost'),'oracle_text':get('oracle_text'),'colors':get('colors',[]),'rarity':sf.get('rarity','common'),'flavor_text':get('flavor_text')}
    for k in ('power','toughness','loyalty','defense'):
        v=get(k,None)
        if v is not None:d[k]=str(v)
    lc=ingest.build_land_colors(types,face,sf,d['oracle_text'])
    if lc:d['land_colors']=lc
    if len(sf.get('card_faces',[]))>1:d.update(parent_name=sf['name'],face_index=index,scryfall_layout=sf.get('layout',''))
    if sf.get('layout')=='prepare':
        faces=sf.get('card_faces',[])
        if len(faces)!=2:raise ValidationError('Prepare cards need the host and prepared spell.')
        d['prepared_spell']=semantic({**sf,'layout':'normal','card_faces':[]},faces[1]);d['scryfall_layout']='prepare'
    if sf.get('layout')=='flip':
        faces=sf.get('card_faces',[])
        if len(faces)!=2:raise ValidationError('Flip cards need the upright and rotated lower face.')
        d['flip_face']=ingest.build_nested_face_semantic(sf,faces[1],faces[1],{})
        d['scryfall_layout']='flip'
    return d

def choose_builtin(d,choice):
    if choice=='auto':return d
    if type_group(d) not in ORDINARY_GROUPS:raise ValidationError('Use the automatic recipe or a compatible structural template.')
    if choice=='land' and d.get('legendary'):raise ValidationError('Full-art land has no compatible legendary crown. Choose Classic or Crowned full art.')
    d=copy.deepcopy(d)
    if choice=='normal':
        pt='Creature' in d['types'] or bool({'Vehicle','Spacecraft'} & set(d['subtypes']))
        d['layout']=('creature_legendary' if d['legendary'] else 'creature') if pt else ('card_legendary' if d['legendary'] else 'card_noncreature')
        if 'Land' not in d['types']:
            d['layout']=native.infer_layout(d if 'layout' not in d else {k:v for k,v in d.items() if k!='layout'},native.get_type_info(d))
        if not d.get('colors') and 'Artifact' not in d['types']:
            d['frame_color']='M';d['_neutral_classic']=True
    elif choice in {'land','legend-land'}:
        d['layout']='land_full_single' if choice=='land' else 'land_full_legendary'
        if 'Land' not in d['types']:d['land_colors']=d.get('colors',[])
    else:raise ValidationError('Unknown built-in template.')
    return d

def custom_data(template,sem,other_faces=None):
    d=copy.deepcopy(template['data'])
    values={'title':sem['name'],'type':native.get_type_info(sem)['normalized'],'mana':sem.get('mana_cost',''),
      'rules':native.italicize_dash_labels(sem.get('oracle_text',''))+('{flavor}'+sem['flavor_text'] if sem.get('flavor_text') else ''),
      'flavor':sem.get('flavor_text',''),'pt':str(sem['power'])+'/'+str(sem['toughness']) if sem.get('power') is not None and sem.get('toughness') is not None else '',
      'loyalty':sem.get('loyalty',''),'defense':sem.get('defense','')}
    for i,line in enumerate(sem.get('oracle_text','').splitlines(),1):values['line'+str(i)]=line
    for slot,field in (template.get('mapping') or {k:k for k in values}).items():
        if slot not in d['text']:continue
        if field in values:d['text'][slot]['text']=str(values[field])
        elif field.startswith('face2.') and other_faces:
            key=field.split('.',1)[1];d['text'][slot]['text']=str(other_faces[0].get({'title':'name','mana':'mana_cost','rules':'oracle_text','type':'type_line'}.get(key,key),'') or '')
    if 'pt' in d['text'] and not values['pt']:d['text']['pt']['text']=''
    return d

class Compiler:
    def __init__(self,store):self.store=store
    def compile_face(self,sf,face,index,options,settings,art_id,*,art_origin='custom artwork'):
        sem=semantic(sf,face,index)
        for k in ('flavor_text','rarity','oracle_text','mana_cost','power','toughness','loyalty','defense'):
            if k in options.get('semanticOverrides',{}):sem[k]=options['semanticOverrides'][k]
        for nested in ('flip_face','prepared_spell'):
            if nested in sem and nested in options.get('nestedFlavorTexts',{}):
                sem[nested]['flavor_text']=options['nestedFlavorTexts'][nested]
        symbols=settings.get('symbols',{})
        if any(not symbols.get(r) or not self.store.asset(symbols[r]) for r in RARITIES):raise ValidationError('Provide four rarity symbols, or generate four treatments from one symbol.')
        symbol_id=symbols.get(sem.get('rarity','common'))
        if not symbol_id:raise ValidationError('Unsupported rarity. Set a common/uncommon/rare/mythic override.')
        art=self.store.asset(art_id)
        if not art:raise ValidationError('Artwork is missing.')
        sem['art']=data_uri(self.store,art_id);sem['art_local_path']=str(self.store.asset_path(art_id));sem['set_symbol_source']=data_uri(self.store,symbol_id)
        credit=resolve_credit(sf,face,options,settings,art_origin)
        artist=credit['display']
        sem['artist']=artist
        group=type_group(face,sf,index);choice=options.get('templateOverride') or settings.get('templateRules',{}).get(group,'auto');flags=[]
        if choice in {x['id'] for x in BUILTINS}:
            if group not in ORDINARY_GROUPS and choice!='auto':raise ValidationError('Choose automatic or a custom template for '+group+'.')
            if group in NEEDS_CUSTOM:raise ValidationError('Recognized '+group+' needs a compatible custom template; no incorrect frame will be substituted.')
            if group in {'modal-front','modal-back'}:
                pair=[x.get('name') for x in sf.get('card_faces',[])]
                if pair!=['Esika, God of the Tree','The Prismatic Bridge']:
                    raise ValidationError('This modal DFC needs a compatible custom template. The approved built-in pair is Esika / The Prismatic Bridge; its colors and reminder strip must not be reused for another card.')
            d0=choose_builtin(sem,choice)
            try:
                data=native.build_one(copy.deepcopy(d0),{'artist':artist},not settings.get('disableAutofit',False),flagged_sagas=flags)['data']
                if choice=='legend-land' and not sem['legendary']:native.remove_crown(data)
                if d0.get('_neutral_classic'):native.recolor_m15(data,'L')
            except native.BuildError as e:raise ValidationError(str(e)) from e
            recipe=native.infer_layout(d0,native.get_type_info(d0))
        else:
            t=self.store.get('templates',choice)
            if not t:raise ValidationError('The selected template was deleted.')
            if group not in t.get('groups',[]):raise ValidationError('The template is not approved for '+group+'.')
            if sem['legendary'] and not t.get('legendary',False):raise ValidationError('This template does not support legendary cards.')
            if sem.get('power') is not None and not ('pt' in t['data']['text'] or 'pt' in (t.get('mapping') or {}).values()):raise ValidationError('A creature template needs a P/T text slot.')
            data=custom_data(t,sem,sf.get('card_faces',[])[1:]);data.update(artSource=sem['art'],setSymbolSource=sem['set_symbol_source'],infoArtist=str(artist))
            if not settings.get('disableAutofit',False):native.auto_fit(data,sem['art_local_path'])
            recipe='custom:'+choice
        for k in ('artX','artY','artZoom','artRotate'):
            if k in options.get('fit',{}):
                v=float(options['fit'][k])
                if not math.isfinite(v) or (k=='artZoom' and v<=0):raise ValidationError('Invalid artwork placement.')
                data[k]=v
        if options.get('rawCard'):
            data=copy.deepcopy(options['rawCard']);data['artSource']=sem['art'];data['setSymbolSource']=sem['set_symbol_source'];data['infoArtist']=str(artist)
        data['artSource']='/api/assets/'+art_id;data['setSymbolSource']='/api/assets/'+symbol_id
        key=render_key(data,art_id);warning=crop_metrics(art['width'],art['height'],data)
        return {'name':sem['name'],'data':data,'renderKey':key,'render':self.store.render_get(key),'group':group,'recipe':recipe,'crop':warning,'flags':flags,'artId':art_id,'symbolId':symbol_id,'artist':str(artist),'credit':credit,'generationVersion':GENERATION_VERSION}
