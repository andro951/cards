"""Validated visual-editor layers compiled to ordinary CardConjurer data."""
from __future__ import annotations
import copy
import math
import re
from .domain import ValidationError

CONDITIONS = {'always', 'legendary', 'nickname', 'pt', 'rulesAndFlavor'}
VARIANTS = set('WUBRGMALCV') | {''.join(sorted(a+b)) for i,a in enumerate('WUBRG') for b in 'WUBRG'[i+1:]}
BINDINGS = {'title', 'subtitle', 'nickname', 'mana', 'type', 'rules', 'flavor', 'pt', 'credit'}


def validate_recipe(recipe, data):
    if not isinstance(recipe, dict) or recipe.get('version') != 1:
        raise ValidationError('Choose a supported visual template recipe.')
    layers = recipe.get('layers')
    sources = recipe.get('sources')
    if not isinstance(sources,dict) or len(sources)>200 or any(not isinstance(src,str) or not re.fullmatch(r'(?:data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=]+|/api/assets/[0-9a-f]{64})',src) for src in sources.values()):
        raise ValidationError('Visual templates need portable image sources.')
    if not isinstance(layers, list) or not layers or len(layers) > 100:
        raise ValidationError('Visual templates need 1–100 frame layers.')
    for layer in layers:
        if not isinstance(layer, dict) or not isinstance(layer.get('when'),str) or layer['when'] not in CONDITIONS or not isinstance(layer.get('mode'),str) or layer['mode'] not in {'source-over', 'destination-out'}:
            raise ValidationError('Invalid visual layer condition or blend.')
        opacity = layer.get('opacity')
        if type(opacity) not in {int, float} or not math.isfinite(opacity) or not 0 <= opacity <= 100:
            raise ValidationError('Visual layer opacity must be 0–100.')
        images = layer.get('images')
        if not isinstance(images, dict) or 'C' not in images or any(key not in VARIANTS for key in images):
            raise ValidationError('Visual layers need a shared image and valid color treatments.')
        for image in images.values():
            if not isinstance(image, dict) or not isinstance(image.get('asset'),str) or image['asset'] not in sources or image.get('mask') is not None and (not isinstance(image['mask'],str) or image['mask'] not in sources):
                raise ValidationError('Visual frame images must be portable PNGs.')
            _rect(image.get('bounds'))
    bindings = recipe.get('bindings')
    if not isinstance(bindings, dict) or not {'title', 'type'} <= set(bindings) or any(slot not in data['text'] or not isinstance(field,str) or field not in BINDINGS for slot,field in bindings.items()):
        raise ValidationError('Visual text bindings are invalid.')
    rules = recipe.get('textRules')
    if not isinstance(rules, dict) or set(rules) != set(bindings):
        raise ValidationError('Visual text appearance rules are missing.')
    for rule in rules.values():
        if not isinstance(rule, dict) or not isinstance(rule.get('when'),str) or rule['when'] not in CONDITIONS or rule.get('flow') not in (None, 'rules') or rule.get('reserveFor') not in (None, 'ManaCost', 'SetSymbol'):
            raise ValidationError('Invalid visual text appearance rule.')
        opacity=rule.get('opacity',1)
        if type(opacity) not in {int,float} or not math.isfinite(opacity) or not 0<=opacity<=1:
            raise ValidationError('Invalid visual text opacity.')
    if type(recipe.get('divider')) is not bool:
        raise ValidationError('Choose whether to use a rules divider.')
    if recipe.get('ptBounds') is not None:
        _rect(recipe['ptBounds'])
    return recipe


def _rect(rect):
    if not isinstance(rect, dict) or any(type(rect.get(key)) not in {int,float} or not math.isfinite(rect[key]) or not -5 <= rect[key] <= 5 for key in ('x','y','width','height')) or rect['width'] <= 0 or rect['height'] <= 0:
        raise ValidationError('Visual bounds must be finite positive regions.')


def compile_visual(template, sem):
    data = copy.deepcopy(template['data'])
    recipe = template['visualRecipe']
    types = sem.get('types') or []
    colors = sorted(sem.get('land_colors',[]) if 'Land' in types else sem.get('colors') or [])
    treatment = colors[0] if len(colors)==1 else 'M' if len(colors)>1 else None
    base = 'L' if 'Land' in types else 'V' if 'Vehicle' in (sem.get('subtypes') or []) else 'A' if 'Artifact' in types else treatment or 'C'
    pair = ''.join(colors) if len(colors) == 2 else ''
    pt = f"{sem['power']}/{sem['toughness']}" if sem.get('power') is not None and sem.get('toughness') is not None else ''
    nickname = str(sem.get('nickname') or '').strip()
    flavor = str(sem.get('flavor_text') or '')
    conditions = {'always': True, 'legendary': bool(sem.get('legendary')), 'nickname': bool(nickname), 'pt': bool(pt), 'rulesAndFlavor': bool(sem.get('oracle_text') and flavor)}
    data['frames'] = []
    for layer in recipe['layers']:
        if conditions[layer['when']]:
            code=base if layer.get('role') in {'Frame','Border'} else treatment or base
            image = layer['images'].get(pair) or layer['images'].get(code) or layer['images']['C']
            data['frames'].insert(0, {'name': layer.get('name','Custom part'), 'src':recipe['sources'][image['asset']], 'bounds':copy.deepcopy(image['bounds']), 'masks': [{'name':'Custom mask','src':recipe['sources'][image['mask']]}] if image.get('mask') else [], 'mode': layer['mode'], 'opacity': layer['opacity']})
    from .legacy import compiler as native
    try:
        type_line = native.get_type_info(sem)['normalized']
    except native.BuildError:
        type_line = sem.get('printed_type_line') or ' '.join(types)
    values = {'title': nickname or sem['name'], 'subtitle': sem['name'] if nickname else '', 'nickname': nickname,
              'mana': sem.get('mana_cost',''), 'type': type_line, 'rules': native.italicize_dash_labels(sem.get('oracle_text','')),
              'flavor': flavor, 'pt': pt, 'credit': (str(sem['artist'])+' · ' if sem.get('artist') else '')+'BulkProxyForge · Unofficial Proxy'}
    for slot,field in recipe['bindings'].items():
        box = data['text'][slot]
        rule = recipe['textRules'][slot]
        box['text'] = str(values[field]) if conditions[rule['when']] else ''
        if rule.get('opacity',1)<1:
            for key in ('color','outlineColor'):
                color=box.get(key,'#000000')
                if re.fullmatch(r'#[0-9a-fA-F]{6}',color):
                    box[key]='rgba('+','.join(str(int(color[i:i+2],16)) for i in (1,3,5))+','+str(rule['opacity'])+')'
        if rule['reserveFor'] == 'ManaCost':
            mana = next((data['text'][key] for key,binding in recipe['bindings'].items() if binding == 'mana'), None)
            if mana and values['mana']:
                count = len(re.findall(r'\{[^}]+\}', values['mana']))
                size = mana['size'] * data['height'] / data['width']
                right = mana['x'] + mana['width'] - count * size
                box['width'] = max(.01, min(box['width'], right - box['x'] - .008))
        elif rule['reserveFor'] == 'SetSymbol':
            box['width'] = max(.01, min(box['width'], data['setSymbolBounds']['x'] - box['x'] - .008))
    #Let the native renderer flow rules/flavor together, including its divider.
    rules_slot = next((slot for slot,field in recipe['bindings'].items() if field == 'rules' and recipe['textRules'][slot]['flow'] == 'rules'), None)
    flavor_slot = next((slot for slot,field in recipe['bindings'].items() if field == 'flavor' and recipe['textRules'][slot]['flow'] == 'rules'), None)
    if rules_slot and flavor_slot:
        rules_box = data['text'][rules_slot]
        rules_box['size']=min(rules_box['size'],data['text'][flavor_slot]['size'])
        flowing_flavor=data['text'][flavor_slot]['text']
        if flowing_flavor:
            rules_box['text'] += ('{flavor}' if recipe['divider'] else '\n{fontmplantini}') + flowing_flavor
        data['text'][flavor_slot]['text'] = ''
        if pt and recipe.get('ptBounds'):
            rules_box['height'] = max(.01, min(rules_box['height'], recipe['ptBounds']['y'] - rules_box['y'] - .008))
    return data