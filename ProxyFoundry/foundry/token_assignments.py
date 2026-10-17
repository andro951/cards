"""Physical token pairs are print metadata, independent of generated face images."""
import json,re
from .domain import ValidationError,quantity

FIELDS=('name','oracle_id','scryfall_id','copy')

def reference(card):
    sf=card.get('scryfall') or {};raw=(sf.get('card_faces') or [sf])[0]
    result={'name':str(raw.get('name') or card['name'])}
    for field,value in [('oracle_id',raw.get('oracle_id') or sf.get('oracle_id')),('scryfall_id',sf.get('id'))]:
        if value:result[field]=value.lower()
    if card.get('tokenSpec') and card['name']!=sf.get('name',card['name']):result['copy']=card['name']
    return result

def key(ref):
    return json.dumps([ref.get('oracle_id',''),ref.get('scryfall_id',''),ref['name'],ref.get('copy','')],ensure_ascii=False,separators=(',',':'))

def validate_reference(value):
    if not isinstance(value,dict) or set(value)-set(FIELDS) or not isinstance(value.get('name'),str) or not value['name'].strip():
        raise ValidationError('Choose a valid token face.')
    result={}
    for field,text in value.items():
        if not isinstance(text,str) or len(text)>300 or any(ord(c)<32 for c in text):raise ValidationError('Invalid token face reference.')
        if field.endswith('_id') and not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',text):raise ValidationError('Invalid token face UUID.')
        result[field]=text.lower() if field.endswith('_id') else text.strip()
    return result

def validate_spec(value):
    if not isinstance(value,dict) or set(value)-{'nonlegendary','replace_creature_subtypes','power_toughness','frame_color','color_override','token_key_suffix'}:
        raise ValidationError('Invalid token treatment options.')
    result=dict(value)
    if 'nonlegendary' in result and not isinstance(result['nonlegendary'],bool):raise ValidationError('Invalid token legendary option.')
    for field in ('power_toughness','frame_color','token_key_suffix'):
        if field in result and (not isinstance(result[field],str) or len(result[field])>100 or any(ord(c)<32 for c in result[field])):raise ValidationError('Invalid token '+field+'.')
    if result.get('power_toughness') and (result['power_toughness'].count('/')!=1 or any(not part.strip() or len(part)>20 for part in result['power_toughness'].split('/'))):raise ValidationError('Enter token power / toughness, for example 1/1.')
    if result.get('frame_color') not in (None,'','W','U','B','R','G','M','A','L','C'):raise ValidationError('Invalid token frame color.')
    for field in ('replace_creature_subtypes','color_override'):
        if field in result:
            values=result[field]
            if not isinstance(values,(str,list)) or isinstance(values,str) and len(values)>200 or isinstance(values,list) and (len(values)>30 or any(not isinstance(v,str) or len(v)>100 for v in values)):
                raise ValidationError('Invalid token '+field+'.')
    return result

def pair_key(row):
    front=key(row['front']);back=row['back']
    return tuple(sorted((front,key(back)))) if 'kind' not in back else (front,back['kind'])

def validate_assignments(value):
    if not isinstance(value,list) or len(value)>10000:raise ValidationError('Token assignments must be an array of at most 10,000 pairs.')
    result=[];seen=set()
    for row in value:
        if not isinstance(row,dict) or set(row)-{'front','back','quantity'}:raise ValidationError('Invalid token assignment.')
        front=validate_reference(row.get('front'));back=row.get('back')
        if isinstance(back,dict) and isinstance(back.get('kind'),str) and back['kind'] in {'card-back','reverse'} and set(back)=={'kind'}:back=dict(back)
        else:back=validate_reference(back)
        count=row.get('quantity')
        if isinstance(count,bool) or not isinstance(count,int):raise ValidationError('Token quantity must be a whole number from 1 to 9999.')
        safe={'front':front,'back':back,'quantity':quantity(count)};ident=pair_key(safe)
        if 'kind' not in back and key(front)==key(back):raise ValidationError('A token cannot use the same face on both sides.')
        if ident in seen:raise ValidationError('This token combination already exists. Adjust its quantity instead.')
        seen.add(ident);result.append(safe)
    return result

def validate_treatments(value):
    if not isinstance(value,list) or len(value)>10000:raise ValidationError('Token treatments must be an array.')
    result=[];seen=set()
    for row in value:
        if not isinstance(row,dict) or set(row)!={'face','options'}:raise ValidationError('Invalid saved token treatment.')
        ref=validate_reference(row['face']);ident=key(ref)
        if ident in seen:raise ValidationError('Duplicate token treatment.')
        seen.add(ident);result.append({'face':ref,'options':validate_spec(row['options'])})
    return result

def resolve(cards,ref):
    candidates=[c for c in cards if reference(c)['name']==ref['name'] and reference(c).get('copy','')==ref.get('copy','')]
    for field in ('scryfall_id','oracle_id'):
        if ref.get(field):
            exact=[c for c in candidates if reference(c).get(field)==ref[field]]
            if exact:return exact[0] if len({key(reference(c)) for c in exact})==1 else None
    return candidates[0] if len(candidates)==1 and not (ref.get('scryfall_id') or ref.get('oracle_id')) else None

def is_token(card,settings):
    sf=card.get('scryfall') or {}
    return bool(card.get('tokenSpec') is not None or settings.get('allCardsTokens') or sf.get('layout') in {'token','double_faced_token'} or re.search(r'\bToken\b',str(sf.get('type_line') or ''),re.I) or any(f.get('group')=='token' or (f.get('compiled') or {}).get('recipe') in {'Deck-wide token','Card Tools copy token'} for f in card.get('faces',[])) or len(card.get('faces',[]))==2 and sf.get('layout')=='reversible_card')

def apply_treatments(deck):
    for row in deck.get('settings',{}).get('tokenTreatments',[]):
        card=resolve(deck['cards'],row['face'])
        if card is not None:
            ident=key(reference(card))
            for other in deck['cards']:
                if key(reference(other))==ident:other['tokenSpec']=dict(row['options'])

def overview(deck):
    settings=deck.get('settings',{});all_tokens=[c for c in deck['cards'] if is_token(c,settings)]
    unique={};suggested={}
    for card in all_tokens:
        ident=key(reference(card));unique.setdefault(ident,card);suggested[ident]=suggested.get(ident,0)+card['quantity']
    cards=list(unique.values())
    singles=[c for c in cards if len(c.get('faces',[]))==1];natural=[c for c in cards if len(c.get('faces',[]))==2]
    usage={c['id']:0 for c in singles};assigned=[];invalid=[];natural_used=set();resolved_pairs=set()
    for index,row in enumerate(settings.get('tokenAssignments',[])):
        front=resolve(cards,row['front']);back=row['back'];kind=back.get('kind');other=resolve(singles,back) if not kind else None
        problem=not front or kind=='reverse' and front not in natural or kind!='reverse' and front not in singles or not kind and (not other or other is front)
        identity=tuple(sorted((front['id'],other['id']))) if front and other else (front['id'] if front else '',kind)
        if identity in resolved_pairs:problem=True
        if problem:
            invalid.append({'index':index,'name':row['front']['name'],'reason':'A face is missing, no longer a single-sided token, or duplicates another pair.'});continue
        resolved_pairs.add(identity)
        assigned.append({'index':index,'frontCardId':front['id'],'backCardId':other['id'] if other else None,'backKind':kind or 'token','quantity':row['quantity'],'assignment':row})
        if kind=='reverse':natural_used.add(front['id'])
        else:
            usage[front['id']]+=row['quantity']
            if other:usage[other['id']]+=row['quantity']
    for card in natural:
        if card['id'] not in natural_used:
            row={'front':reference(card),'back':{'kind':'reverse'},'quantity':suggested[key(reference(card))]}
            assigned.append({'index':None,'frontCardId':card['id'],'backCardId':None,'backKind':'reverse','quantity':row['quantity'],'assignment':row})
    unused=[{'cardId':c['id'],'name':c['name']} for c in singles if not usage[c['id']]]
    return {'cardIds':[c['id'] for c in all_tokens],'faces':[{'cardId':c['id'],'reference':reference(c),'used':usage[c['id']],'suggestedQuantity':suggested[key(reference(c))]} for c in singles],
            'assigned':assigned,'unused':unused,'invalid':invalid,'ready':not unused and not invalid,'physicalCount':sum(r['quantity'] for r in assigned)}