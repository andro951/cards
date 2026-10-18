"""Alternate artwork splits quantities without changing the selected printing."""
import copy,re
from .domain import ValidationError,uid


def validate(rows):
    if not isinstance(rows,list) or len(rows)>10000:raise ValidationError('Artwork variants must be an array of at most 10,000 entries.')
    result=[];seen=set()
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'id','card','quantity','faces'}:raise ValidationError('Invalid alternate-art entry.')
        ident=row['id'];source=row['card'];count=row['quantity']
        if not isinstance(ident,str) or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',ident,re.I) or ident.lower() in seen:raise ValidationError('Alternate artwork needs a unique variant ID.')
        seen.add(ident.lower())
        if not isinstance(source,dict) or set(source)-{'name','oracle_id','scryfall_id','section'} or not source.get('name'):raise ValidationError('Choose an existing card for alternate artwork.')
        for key,value in source.items():
            if not isinstance(value,str) or not value.strip() or len(value)>300 or any(ord(ch)<32 for ch in value):raise ValidationError('Invalid alternate-art card reference.')
            if key.endswith('_id') and not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',value,re.I):raise ValidationError('Invalid alternate-art card UUID.')
        if isinstance(count,bool) or not isinstance(count,int) or not 1<=count<=9999:raise ValidationError('Choose 1–9,999 copies for alternate artwork.')
        faces=row['faces']
        if not isinstance(faces,list) or not 1<=len(faces)<=2:raise ValidationError('Choose artwork for a card face.')
        names=set()
        for face in faces:
            if not isinstance(face,dict) or set(face)!={'name','art'}:raise ValidationError('Invalid alternate-art face.')
            name=face['name'];art=face['art']
            if not isinstance(name,str) or not name.strip() or len(name)>300 or name in names:raise ValidationError('Invalid alternate-art face name.')
            names.add(name)
            if not isinstance(art,str) or len(art)>1000 or any(ord(ch)<32 for ch in art) or art.startswith('/') or '\\' in art or ':' in art or any(p in {'','..','.'} for p in art.split('/')) or not re.search(r'\.(png|jpe?g|webp|gif)$',art,re.I):raise ValidationError('Choose an artwork image relative to the project art folder.')
        result.append({'id':ident.lower(),'card':{k:v.lower() if k.endswith('_id') else v for k,v in source.items()},'quantity':count,'faces':copy.deepcopy(faces)})
    return result


def reference(card):
    sf=card['scryfall']
    return {
        'name':card['name'],'section':card.get('section','mainboard'),
        **({'oracle_id':sf['oracle_id'].lower()} if sf.get('oracle_id') else {}),
        **({'scryfall_id':sf['id'].lower()} if sf.get('id') else {})}


def matches(ref,card):
    target=reference(card)
    return all(target.get(key)==value for key,value in ref.items())


def selected_face(face):
    if not face.get('variantArtFilename'):return face
    return {**face,'artFilename':face['variantArtFilename'],'artOverride':None,'selectedArtPrintingId':None}


def apply(deck,invalidate):
    if deck.get('pendingImport'):return False
    rows=validate(deck['settings'].get('artVariants',[]));groups={};assignments={}
    for card in deck['cards']:
        ref=reference(card);key=(ref.get('scryfall_id') or ref.get('oracle_id') or ref['name'],ref['name'],ref['section'])
        groups.setdefault(key,[]).append(card)
    for row in rows:
        candidates=[key for key,cards in groups.items() if matches(row['card'],cards[0])]
        if len(candidates)>1:raise ValidationError('Alternate artwork matches multiple printings. Include its Scryfall ID.')
        if candidates:assignments.setdefault(candidates[0],[]).append(row)
    output=[];changed=False
    for key,cards in groups.items():
        desired=assignments.get(key,[])
        if not desired and not any(c.get('artVariantId') for c in cards):output.extend(cards);continue
        total=sum(c['quantity'] for c in cards);allocated=sum(row['quantity'] for row in desired)
        if allocated>total:raise ValidationError(f'Alternate artwork for {cards[0]["name"]} needs {allocated} copies, but the deck contains {total}.')
        base=next((c for c in cards if not c.get('artVariantId')),None)
        donor=base or cards[0];root=donor.get('artVariantRoot',donor['id']);root_faces=donor.get('artVariantRootFaces',[f['id'] for f in donor['faces']])
        old={c.get('artVariantId'):c for c in cards};entries=[]
        if total>allocated:entries.append((None,total-allocated,{}))
        for row in desired:
            names={f['name'] for f in donor['faces']}
            if any(f['name'] not in names for f in row['faces']):raise ValidationError('Alternate artwork names a face that is not on '+donor['name']+'.')
            entries.append((row['id'],row['quantity'],{f['name']:f['art'] for f in row['faces']}))
        for ident,count,art in entries:
            existing=old.get(ident);card=existing or copy.deepcopy(donor)
            if existing is None:
                card['id']=uid() if ident else root
                for index,face in enumerate(card['faces']):face['id']=uid() if ident else root_faces[index]
                changed=True
            card['quantity']=count;card['artVariantRoot']=root;card['artVariantRootFaces']=root_faces
            if ident:card['artVariantId']=ident
            else:card.pop('artVariantId',None)
            for face in card['faces']:
                filename=art.get(face['name'])
                if face.get('variantArtFilename')!=filename or existing is None:
                    if filename:
                        face['variantArtFilename']=filename
                        face.pop('fit',None)
                    else:face.pop('variantArtFilename',None)
                    invalidate(face);changed=True
            output.append(card)
        if len(entries)!=len(cards):changed=True
    deck['cards']=output
    return changed