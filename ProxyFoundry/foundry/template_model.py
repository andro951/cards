"""Versioned reusable template model for dynamic card layouts."""
from __future__ import annotations

import copy
import math

from .domain import GROUP_LABELS, ValidationError, validate_template
from .template_expressions import parse_formula, evaluate_formula

FORMAT='bulk-proxy-forge-template'
SCHEMA=3
FIELDS={'title','type','mana','rules','flavor','pt','loyalty','defense'}
GEOMETRY={'x','y','width','height','size'}
TRANSPARENT='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYGD4DwABBAEAHnOcQAAAAABJRU5ErkJggg=='


def initial_regions(data):
    return {slot:{'field':slot if slot in FIELDS else 'native:'+slot,'geometry':'native','offset':{}}
            for slot in data.get('text',{})}


def convert_cardconjurer(source, name='Custom template', group='standard'):
    if group not in GROUP_LABELS:raise ValidationError('Choose a supported structural card group.')
    data=validate_template(source)
    data=copy.deepcopy(data)
    for key in ('artSource','setSymbolSource'):
        data.pop(key,None)
    data['watermarkSource']=TRANSPARENT
    data['watermarkOpacity']=0
    for slot in initial_regions(data):
        data['text'][slot]['text']=''
    return {'format':FORMAT,'schemaVersion':SCHEMA,'name':str(name or 'Custom template')[:200],
            'data':data,'groups':[group],'legendary':group in {'legendary','legendary-land'},
            'baseGroup':group,'regions':initial_regions(data)}


def validate_model(value):
    if not isinstance(value,dict) or value.get('format')!=FORMAT or value.get('schemaVersion') not in {2,SCHEMA}:
        raise ValidationError('Choose a version 2 or 3 Bulk Proxy Forge template JSON file.')
    data=validate_template(value.get('data'))
    groups=value.get('groups')
    if not isinstance(groups,list) or not groups or any(group not in GROUP_LABELS for group in groups):
        raise ValidationError('Choose valid structural groups for this template.')
    base=value.get('baseGroup')
    if base not in groups:raise ValidationError('The base group must be one of the supported groups.')
    regions=value.get('regions')
    if not isinstance(regions,dict) or not {'title','type'}<=set(regions):
        raise ValidationError('Map title and type regions before saving.')
    for slot,region in regions.items():
        if slot not in data['text'] or not isinstance(region,dict):raise ValidationError('Region names must match template text boxes.')
        field=region.get('field')
        if not isinstance(field,str) or not (field in FIELDS or field.startswith('native:') and field[7:] in data['text']):
            raise ValidationError('Choose a supported semantic field or native text slot.')
        if region.get('geometry') not in {'native','fixed'}:raise ValidationError('Choose native or fixed geometry.')
        for key in GEOMETRY:
            number=data['text'][slot].get(key)
            if number is not None and (type(number) not in {int,float} or not math.isfinite(number)):
                raise ValidationError('Template region geometry must contain finite numbers.')
        formulas=region.get('formulas') or {}
        if not isinstance(formulas,dict) or any(key not in GEOMETRY for key in formulas):raise ValidationError('Choose supported geometry formula properties.')
        for expression in formulas.values():parse_formula(expression)
        offset=region.get('offset') or {}
        if not isinstance(offset,dict) or any(key not in GEOMETRY or isinstance(number,bool) or
                                             not isinstance(number,(int,float)) or not math.isfinite(number) or abs(number)>.5
                                             for key,number in offset.items()):
            raise ValidationError('Region offsets must be finite values between -0.5 and 0.5.')
    variants=value.get('variants') or []
    if not isinstance(variants,list) or len(variants)>32:raise ValidationError('Use at most 32 template variants.')
    previous_conditions=[]
    for variant in variants:
        if not isinstance(variant,dict):raise ValidationError('Template variants must be objects.')
        when=variant.get('when') or {}
        if not isinstance(when,dict) or set(when)-{'group','legendary','hasPT','colors'}:raise ValidationError('Choose valid variant conditions.')
        if 'group' in when and when['group'] not in groups:raise ValidationError('Variant group must be supported by the template.')
        for key in ('legendary','hasPT'):
            if key in when and type(when[key]) is not bool:raise ValidationError('Variant boolean conditions must be true or false.')
        if 'colors' in when and (not isinstance(when['colors'],list) or len(set(map(str,when['colors'])))!=len(when['colors']) or any(not isinstance(color,str) or len(color)!=1 or color not in 'WUBRG' for color in when['colors'])):raise ValidationError('Variant colors must be W/U/B/R/G.')
        canonical={key:sorted(number) if key=='colors' else number for key,number in when.items()}
        if any(all(canonical.get(key)==number for key,number in previous.items()) for previous in previous_conditions):
            raise ValidationError('A previous variant already covers this condition; reorder or narrow its conditions.')
        previous_conditions.append(canonical)
        patched=copy.deepcopy(data)
        if 'frames' in variant:patched['frames']=variant['frames'];validate_template(patched)
        replacements=variant.get('regions') or {}
        if not isinstance(replacements,dict) or set(replacements)-set(regions):raise ValidationError('Variant regions must already exist.')
        if replacements:
            validate_model({**value,'variants':[], 'regions':{**regions,**replacements}})
    metadata=value.get('layoutMetadata') or {}
    if not isinstance(metadata,dict) or set(metadata)-{'tokenStyle'}:raise ValidationError('Unknown template layout metadata.')
    if metadata.get('tokenStyle') not in {None,'token-classic','token-full-art','token-borderless'}:raise ValidationError('Choose a supported token layout family.')
    return {**value,'layoutMetadata':metadata,'schemaVersion':SCHEMA,'data':data,'groups':groups,'baseGroup':base,
            'regions':copy.deepcopy(regions),'variants':copy.deepcopy(variants)}



def apply_regions(data,reference,regions,sem=None):
    sem=sem or {}
    for slot,region in regions.items():
        target=data['text'].get(slot)
        source=reference.get('text',{}).get(region['field'].removeprefix('native:'))
        if not target:continue
        if not source:
            if region['geometry']=='fixed':source=target
            else:continue
        variables={'native.'+key:source.get(key,0) for key in GEOMETRY}
        variables.update({'card.titleLength':len(str(sem.get('name') or '')),
                          'card.rulesLength':len(str(sem.get('oracle_text') or '')),
                          'card.colorCount':len(sem.get('colors') or []),
                          'card.legendary':int(bool(sem.get('legendary'))),
                          'card.hasPT':int(sem.get('power') is not None and sem.get('toughness') is not None)})
        for key in GEOMETRY:
            if key in (region.get('formulas') or {}):target[key]=evaluate_formula(region['formulas'][key],variables)
            elif region['geometry']=='native' and key in source:target[key]=source[key]+(region.get('offset') or {}).get(key,0)
            elif region['geometry']=='fixed' and key in target:target[key]+=(region.get('offset') or {}).get(key,0)
            if key in target and (type(target[key]) not in {int,float} or not math.isfinite(target[key]) or abs(target[key])>2 or key in {'width','height','size'} and target[key]<=0):
                raise ValidationError('Template region '+slot+' has invalid geometry.')
        if region['field'].startswith('native:'):target['text']=str(source.get('text') or '')
    if isinstance(reference.get('setSymbolBounds'),dict):
        data['setSymbolBounds']=copy.deepcopy(reference['setSymbolBounds'])
    return data


def select_variant(model,sem,group):
    result=copy.deepcopy(model)
    actual={'group':group,'legendary':bool(sem.get('legendary')),
            'hasPT':sem.get('power') is not None and sem.get('toughness') is not None,
            'colors':sorted(sem.get('colors') or [])}
    for variant in model.get('variants') or []:
        if all(actual[key]==(sorted(value) if key=='colors' else value) for key,value in (variant.get('when') or {}).items()):
            if 'frames' in variant:result['data']['frames']=copy.deepcopy(variant['frames'])
            result['regions'].update(copy.deepcopy(variant.get('regions') or {}))
            break
    return result
