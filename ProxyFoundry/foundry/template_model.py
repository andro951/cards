"""Versioned reusable template model for dynamic ordinary-card layouts."""
from __future__ import annotations

import copy
import math

from .domain import ORDINARY_GROUPS, ValidationError, validate_template

FORMAT='bulk-proxy-forge-template'
SCHEMA=2
FIELDS={'title','type','mana','rules','flavor','pt','loyalty','defense'}
GEOMETRY={'x','y','width','height','size'}
TRANSPARENT='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYGD4DwABBAEAHnOcQAAAAABJRU5ErkJggg=='


def initial_regions(data):
    return {slot:{'field':slot,'geometry':'native','offset':{}}
            for slot in FIELDS if slot in data.get('text',{})}


def convert_cardconjurer(source, name='Custom template', group='standard'):
    if group not in ORDINARY_GROUPS:
        raise ValidationError('Card Conjurer conversion currently supports ordinary cards and lands. Use a hand-authored structural template for this layout.')
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
    if not isinstance(value,dict) or value.get('format')!=FORMAT or value.get('schemaVersion')!=SCHEMA:
        raise ValidationError('Choose a version 2 Bulk Proxy Forge template JSON file.')
    data=validate_template(value.get('data'))
    groups=value.get('groups')
    if not isinstance(groups,list) or not groups or any(group not in ORDINARY_GROUPS for group in groups):
        raise ValidationError('Version 2 templates support ordinary card and land groups.')
    base=value.get('baseGroup')
    if base not in groups:raise ValidationError('The base group must be one of the supported groups.')
    regions=value.get('regions')
    if not isinstance(regions,dict) or not {'title','type'}<=set(regions):
        raise ValidationError('Map title and type regions before saving.')
    for slot,region in regions.items():
        if slot not in data['text'] or not isinstance(region,dict):raise ValidationError('Region names must match template text boxes.')
        if region.get('field') not in FIELDS or region.get('geometry')!='native':
            raise ValidationError('Choose a supported semantic field and native geometry.')
        offset=region.get('offset') or {}
        if not isinstance(offset,dict) or any(key not in GEOMETRY or isinstance(number,bool) or
                                             not isinstance(number,(int,float)) or not math.isfinite(number) or abs(number)>.5
                                             for key,number in offset.items()):
            raise ValidationError('Region offsets must be finite values between -0.5 and 0.5.')
    return {**value,'data':data,'groups':groups,'baseGroup':base,'regions':copy.deepcopy(regions)}


def apply_regions(data,reference,regions):
    for slot,region in regions.items():
        target=data['text'].get(slot)
        source=reference.get('text',{}).get(region['field'])
        if not target or not source:continue
        for key in GEOMETRY:
            if key in source:
                target[key]=source[key]+(region.get('offset') or {}).get(key,0)
    if isinstance(reference.get('setSymbolBounds'),dict):
        data['setSymbolBounds']=copy.deepcopy(reference['setSymbolBounds'])
    return data
