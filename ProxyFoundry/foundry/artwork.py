"""Artwork inventory and exception review without fetching or rendering card art."""
import re
from pathlib import PurePosixPath
from .domain import ValidationError,slug,stable_hash
from .card_data import identity

UUID_IN_NAME=re.compile(r'[0-9a-f]{8}[-_][0-9a-f]{4}[-_][0-9a-f]{4}[-_][0-9a-f]{4}[-_][0-9a-f]{12}',re.I)

class ArtworkIndex(dict):
    def __init__(self,values,names=None):
        super().__init__(values);self.names={};self.by_name={};self.by_uuid={};self.by_file={}
        for key,value in values.items():
            filename=(names or {}).get(key) or (value.get('filename') if isinstance(value,dict) else None) or key+'.png'
            self.names[key]=filename;self.by_file.setdefault(filename,[]).append(key)
            stem=slug(PurePosixPath(filename).stem)
            for name in {stem,re.sub(r'^\d+_','',stem)}:
                self.by_name.setdefault(name.replace('_',''),set()).add(key)
            for uuid in UUID_IN_NAME.findall(filename):
                self.by_uuid.setdefault(uuid.lower().replace('_','-'),set()).add(key)

    def resolve(self,name,oracle_id='',filename='',multiface=False,printing_id=''):
        if filename:
            candidates=self.by_file.get(filename,[])
            # Old workspace imports did not retain extensions. Only use the
            # legacy stem when no original filename was retained for that key.
            if not candidates:
                key=slug(PurePosixPath(filename).stem)
                if key in self and self.names[key]==key+'.png' and filename==key+'.png':candidates=[key]
            if not candidates:raise ValidationError('Mapped artwork is missing: '+filename+'.')
        else:
            candidates=list(self.by_uuid.get(str(oracle_id).lower(),[]) or self.by_uuid.get(str(printing_id).lower(),[]))
            if candidates and multiface:
                face_key=slug(name)
                candidates=[k for k in candidates if re.search(r'(^|_)'+re.escape(face_key)+r'(_|$)',slug(PurePosixPath(self.names[k]).stem))]
            if not candidates:candidates=list(self.by_name.get(slug(name).replace('_',''),[]))
            exact=slug(name)
            if len(candidates)>1 and exact in candidates and self.names[exact]==exact+'.png':candidates=[exact]
            if not candidates:return None
        if len(candidates)!=1:raise ValidationError('Multiple custom artwork files match '+name+': '+', '.join(sorted(self.names[k] for k in candidates))+'. Choose their artwork in the matching helper.')
        return candidates[0]

def face_key(card,face):
    target=identity(card,face)
    return (target['oracle_id'] or target['scryfall_id'] or card['id'])+'/'+target['name']

def build_review(deck,settings,index):
    items={};defaults=set(settings.get('artDefaults') or [])
    for card in deck['cards']:
        raw_faces=card['scryfall'].get('card_faces') or [card['scryfall']]
        for face in card['faces']:
            key=face_key(card,face)
            if key in items:continue
            raw=raw_faces[min(face.get('index',0),len(raw_faces)-1)]
            image=(raw.get('image_uris') or card['scryfall'].get('image_uris') or {})
            selector=identity(card,face)
            selector={k:v for k,v in selector.items() if v and (k!='scryfall_id' or not selector['oracle_id'])}
            item={'id':key,'selector':selector,'name':face['name'],'image':image.get('normal') or image.get('png') or image.get('large') or '',
                  'status':'missing','filename':None,'key':None,'reason':'No matching custom artwork.',
                  'explicit':bool(face.get('artFilename'))}
            if face.get('artOverride') or face.get('selectedArtPrintingId'):
                item.update(status='override',reason='Artwork chosen for this card.')
            elif key in defaults:
                item.update(status='default',reason='Scryfall artwork approved.')
            else:
                try:
                    match=index.resolve(face['name'],identity(card,face)['oracle_id'],face.get('artFilename',''),len(raw_faces)>1,identity(card,face)['scryfall_id'])
                    if match is not None:item.update(status='matched',key=match,filename=index.names[match],reason='')
                except ValidationError as exc:item.update(status='conflict',reason=str(exc))
            items[key]=item
    # Name-only matches must not silently assign one image to distinct token
    # variants. Explicit mappings are allowed to deliberately reuse artwork.
    users={}
    for item in items.values():
        if item['key'] is not None:users.setdefault(item['key'],[]).append(item)
    for rows in users.values():
        if len(rows)>1 and any(not r['explicit'] for r in rows):
            for row in rows:
                if not row['explicit']:row.update(status='conflict',key=None,filename=None,reason='This artwork name matches more than one card variant. Choose the correct artwork.')
    used={i['key'] for i in items.values() if i['key'] is not None}
    inventory=[]
    for key,value in index.items():
        inventory.append({'key':key,'filename':index.names[key],
                          'image':'/api/assets/'+value+'/thumbnail' if isinstance(value,str) else value['url'],
                          'identity':value if isinstance(value,str) else value.get('blobSha',value['url'])})
    signature=stable_hash({'inventory':[(r['key'],r['filename'],r['identity']) for r in inventory],
                           'faces':sorted(items),'source':{k:v for k,v in settings['source'].items() if k not in {'localFiles','localNames'}}})
    unresolved=[r for r in items.values() if r['status'] in {'missing','conflict'}]
    unused=[r for r in inventory if r['key'] not in used]
    return {'items':list(items.values()),'inventory':inventory,'unused':unused,'signature':signature,
            'needsReview':bool(unresolved or unused and settings.get('artReviewSignature')!=signature),
            'missing':len(unresolved),'needed':len(items),'available':len(inventory)}
