"""Shared card-data selectors for imports, artwork matching and saved decks."""
import json,re
from .domain import ValidationError

UUID=re.compile(r'^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$',re.I)

def validate_entries(cards):
    if cards is None:return []
    if not isinstance(cards,list):raise ValidationError('Imported card data cards must be an array.')
    if len(cards)>10000:raise ValidationError('Imported card data may contain at most 10,000 entries.')
    result=[];seen=set()
    for i,item in enumerate(cards,1):
        if not isinstance(item,dict):raise ValidationError(f'data.json card entry {i} must be an object.')
        unknown=set(item)-{'name','oracle_id','scryfall_id','nickname','flavor_text','artist','art'}
        if unknown:raise ValidationError(f'data.json card entry {i} has unsupported field(s): '+', '.join(sorted(unknown))+'.')
        entry={}
        for key,maximum in [('name',300),('oracle_id',36),('scryfall_id',36),('nickname',300),('flavor_text',20000),('artist',300),('art',1000)]:
            value=item.get(key,'')
            if value is None:value=''
            if not isinstance(value,str):raise ValidationError(f'data.json {key} for entry {i} must be text.')
            value=value.strip()
            allowed={'\n','\t'} if key=='flavor_text' else set()
            if len(value)>maximum or any((ord(ch)<32 and ch not in allowed) or ord(ch)==127 for ch in value):
                raise ValidationError(f'data.json {key} for entry {i} is too long or contains unsupported control characters.')
            if value:entry[key]=value
        if not any(entry.get(k) for k in ['name','oracle_id','scryfall_id']):raise ValidationError(f'data.json card entry {i} name or UUID is required.')
        for key in ['oracle_id','scryfall_id']:
            if key in entry:
                if not UUID.fullmatch(entry[key]):raise ValidationError('Invalid '+key+' in data.json.')
                entry[key]=entry[key].lower()
        if 'art' in entry:
            path=entry['art']
            if path.startswith('/') or '\\' in path or ':' in path or any(p in {'','..','.'} for p in path.split('/')):
                raise ValidationError('Artwork filenames must be relative to the selected artwork folder.')
            if not re.search(r'\.(png|jpe?g|webp|gif)$',path,re.I):raise ValidationError('Choose a supported artwork image filename.')
        if not any(k in entry for k in ['nickname','flavor_text','artist','art']):continue
        key=selector_key(entry)
        if key in seen:raise ValidationError('data.json contains more than one nonempty entry for '+str(entry.get('name') or entry.get('oracle_id') or entry.get('scryfall_id'))+'.')
        seen.add(key);result.append(entry)
    return result

def selector_key(entry):
    return (entry.get('oracle_id',''),entry.get('scryfall_id',''),entry.get('name',''))

def identity(card,face):
    sf=card['scryfall'];faces=sf.get('card_faces') or [sf]
    raw=faces[min(face.get('index',0),len(faces)-1)]
    return {'name':str(raw.get('name') or face.get('name') or card['name']),
            'oracle_id':str(raw.get('oracle_id') or sf.get('oracle_id') or '').lower(),
            'scryfall_id':str(sf.get('id') or '').lower()}

def matches(entry,card,face):
    target=identity(card,face)
    return all(target[k]==entry[k] for k in ['oracle_id','scryfall_id','name'] if entry.get(k))

def matching_keys(card,face):
    target=identity(card,face)
    for mask in range(1,8):
        yield tuple(target[k] if mask&(1<<i) else '' for i,k in enumerate(['oracle_id','scryfall_id','name']))

def validate_targets(deck,entries):
    targets={}
    for card in deck.get('cards',[]):
        for face in card.get('faces',[]):
            target=identity(card,face)
            variant=(target['oracle_id'] or target['scryfall_id'] or card['id'],target['name'])
            for key in matching_keys(card,face):targets.setdefault(key,set()).add(variant)
    missing=[e.get('name') or e.get('oracle_id') or e.get('scryfall_id') for e in entries if selector_key(e) not in targets]
    if missing:raise ValidationError('data.json card selector(s) were not found in this deck: '+', '.join(missing[:8])+'. Names must exactly match a card face when supplied.')
    ambiguous=[e.get('name') or e.get('oracle_id') or e.get('scryfall_id') for e in entries if e.get('art') and len(targets[selector_key(e)])>1]
    if ambiguous:raise ValidationError('Artwork selector(s) match multiple card variants or faces: '+', '.join(ambiguous[:8])+'. Use a UUID and face name to identify each artwork mapping.')
    return entries

def merge_entries(original,updates):
    entries={selector_key(e):dict(e) for e in original}
    for entry in updates:entries[selector_key(entry)]={**entries.get(selector_key(entry),{}),**entry}
    return list(entries.values())

def parse_document(raw):
    if not isinstance(raw,(bytes,bytearray)) or len(raw)>2*1024*1024:raise ValidationError('data.json must be a UTF-8 JSON file no larger than 2 MB.')
    try:value=json.loads(bytes(raw).decode('utf-8-sig'))
    except (ValueError,UnicodeError) as exc:raise ValidationError('data.json is not valid UTF-8 JSON.') from exc
    if not isinstance(value,dict):raise ValidationError('data.json must contain a JSON object.')
    if set(value)-{'version','cards'}:raise ValidationError('data.json has unsupported top-level fields.')
    if value.get('version')!=1:raise ValidationError('data.json version must be 1.')
    if not isinstance(value.get('cards'),list):raise ValidationError('data.json cards must be an array.')
    return validate_entries(value['cards'])
