"""Small adapter over Card Tools v48. Automatic mode delegates without changing geometry."""
from __future__ import annotations
import copy,base64,io
from PIL import Image
from .domain import ValidationError,ORDINARY_GROUPS,type_group,is_legendary,crop_metrics,render_key
from .legacy import compiler as native,ingest
from .images import data_uri
BUILTINS=[
 {'id':'auto','name':'Card Tools · automatic','description':'Preserve every approved v48 type-specific recipe.','legendary':True,'groups':'all'},
 {'id':'normal','name':'Classic card','description':'Standard card frame, with a crown on legendary cards.','legendary':True,'groups':'ordinary'},
 {'id':'land','name':'Full-art land','description':'The existing nonlegendary land frame. No compatible crown.','legendary':False,'groups':'ordinary'},
 {'id':'legend-land','name':'Crowned full art','description':'The existing legendary-land frame. Crown removed for nonlegendary cards.','legendary':True,'groups':'ordinary'}]
SINGLE_SURFACE={'adventure','split','flip','room','prepare'}

def semantic(sf,face,index=0):
    get=lambda k,default='':ingest.face_value(face,sf,k,default)
    types=ingest.split_type_line(get('type_line'))
    d={**types,'name':get('name'),'mana_cost':get('mana_cost'),'oracle_text':get('oracle_text'),
       'colors':get('colors',[]),'rarity':sf.get('rarity','common'),'flavor_text':get('flavor_text')}
    for k in ('power','toughness','loyalty','defense'):
        v=get(k,None)
        if v is not None:d[k]=str(v)
    lc=ingest.build_land_colors(types,face,sf,d['oracle_text'])
    if lc:d['land_colors']=lc
    if len(sf.get('card_faces',[]))>1:d.update(parent_name=sf['name'],face_index=index,scryfall_layout=sf.get('layout',''))
    if sf.get('layout')=='prepare':
        faces=sf.get('card_faces',[])
        if len(faces)!=2:raise ValidationError('Prepare cards require the host and prepared spell.')
        d['prepared_spell']=semantic({**sf,'layout':'normal','card_faces':[]},faces[1],0)
        d['scryfall_layout']='prepare'
    return d

def choose_builtin(d,choice):
    group=type_group(d)
    if choice=='auto':return d
    if group not in ORDINARY_GROUPS:raise ValidationError('This structural card needs its automatic recipe or a compatible custom template.')
    if choice=='land' and d.get('legendary'):raise ValidationError('The full-art land frame has no compatible legendary crown. Choose Classic or Crowned full art.')
    d=copy.deepcopy(d)
    if choice=='normal':
        has_pt=bool('Creature' in d['types'] or {'Vehicle','Spacecraft'} & set(d['subtypes']))
        d['layout']=('creature_legendary' if d['legendary'] else 'creature') if has_pt else ('card_legendary' if d['legendary'] else 'card_noncreature')
        if not d.get('colors') and 'Artifact' not in d['types']:d['frame_color']='L'
    elif choice in {'land','legend-land'}:
        d['layout']='land_full_single' if choice=='land' else 'land_full_legendary'
        if 'Land' not in d['types']:d['land_colors']=d.get('colors',[])
    else:raise ValidationError('Unknown built-in template: '+str(choice))
    return d

def custom_data(template,sem,other_faces=None):
    d=copy.deepcopy(template['data']);values={'title':sem['name'],'type':native.get_type_info(sem)['normalized'],
       'mana':sem.get('mana_cost',''),'rules':native.italicize_dash_labels(sem.get('oracle_text',''))+('{flavor}'+sem['flavor_text'] if sem.get('flavor_text') else ''),
       'pt':(str(sem['power'])+'/'+str(sem['toughness'])) if sem.get('power') is not None and sem.get('toughness') is not None else '',
       'loyalty':sem.get('loyalty',''),'defense':sem.get('defense','')}
    mapping=template.get('mapping') or {k:k for k in values}
    for slot,field in mapping.items():
        if slot not in d['text']:continue
        if field in values:d['text'][slot]['text']=values[field]
        elif field.startswith('face2.') and other_faces:
            s=other_faces[0];key=field.split('.',1)[1];d['text'][slot]['text']=str(s.get({'title':'name','mana':'mana_cost','rules':'oracle_text','type':'type_line'}.get(key,key),'') or '')
    if 'pt' in d['text'] and not values['pt']:d['text']['pt']['text']=''
    return d

class Compiler:
    def __init__(self,store):self.store=store
    def compile_face(self,sf,face,index,options,settings,art_id):
        sem=semantic(sf,face,index)
        for k in ('flavor_text','rarity','oracle_text','mana_cost','power','toughness','loyalty','defense'):
            if k in options.get('semanticOverrides',{}):sem[k]=options['semanticOverrides'][k]
        rarity=sem.get('rarity','common');symbols=settings.get('symbols',{})
        if not all(self.store.asset(symbols.get(r,'')) for r in ('common','uncommon','rare','mythic') if symbols.get(r)) or any(not symbols.get(r) for r in ('common','uncommon','rare','mythic')):
            raise ValidationError('Provide all four rarity symbols, or generate the four treatments from one symbol.')
        symbol_id=symbols.get(rarity)
        if not symbol_id:raise ValidationError('No set symbol for rarity '+str(rarity))
        art=self.store.asset(art_id)
        if not art:raise ValidationError('Artwork is missing.')
        sem['art']=data_uri(self.store,art_id);sem['art_local_path']=str(self.store.asset_path(art_id))
        sem['set_symbol_source']=data_uri(self.store,symbol_id)
        artist=options.get('artistOverride')
        if artist is None:artist=settings.get('artist') or face.get('artist') or sf.get('artist') or ''
        group=type_group(face,sf,index)
        choice=options.get('templateOverride') or settings.get('templateRules',{}).get(group,'auto')
        flags=[]
        if choice in {x['id'] for x in BUILTINS}:
            if group not in ORDINARY_GROUPS and choice!='auto':raise ValidationError('Choose automatic or a custom template for '+group+'.')
            if group in {'transform-front','transform-back','split','adventure','flip','room','meld','art-series','planar','scheme','vanguard','token','emblem'}:
                raise ValidationError('Recognized '+group+' layout needs a compatible custom template; it will not be printed with the wrong frame.')
            d0=choose_builtin(sem,choice)
            try:
                entry=native.build_one(copy.deepcopy(d0),{'artist':artist},True,flagged_sagas=flags)
                data=entry['data']
                if choice=='legend-land' and not sem['legendary']:native.remove_crown(data)
            except native.BuildError as exc:raise ValidationError(str(exc)) from exc
            recipe=native.infer_layout(d0,native.get_type_info(d0))
        else:
            t=self.store.get('templates',choice)
            if not t:raise ValidationError('The selected template was deleted. Choose another template.')
            if group not in t.get('groups',[]):raise ValidationError('The selected template is not approved for '+group+'.')
            if sem['legendary'] and not t.get('legendary',False):raise ValidationError('The selected template does not support legendary cards.')
            if (sem.get('power') is not None) and not ('pt' in t['data']['text'] or 'pt' in (t.get('mapping') or {}).values()):
                raise ValidationError('This creature template needs a power/toughness text slot.')
            data=custom_data(t,sem,sf.get('card_faces',[])[1:]);data.update(artSource=sem['art'],setSymbolSource=sem['set_symbol_source'],infoArtist=str(artist))
            native.auto_fit(data,sem['art_local_path']);recipe='custom:'+choice
        for k in ('artX','artY','artZoom','artRotate'):
            if k in options.get('fit',{}):data[k]=float(options['fit'][k])
        if options.get('rawCard'):
            data=copy.deepcopy(options['rawCard']);data['artSource']=sem['art'];data['setSymbolSource']=sem['set_symbol_source'];data['infoArtist']=str(artist)
        key=render_key(data,art_id)
        warning=crop_metrics(art['width'],art['height'],data)
        return {'name':sem['name'],'data':data,'renderKey':key,'render':self.store.render_get(key),'group':group,'recipe':recipe,'crop':warning,'flags':flags,'artId':art_id,'artist':str(artist)}
