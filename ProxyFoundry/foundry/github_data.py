"""Refresh small GitHub card-data documents before preparation cache decisions."""
import copy
import re
from urllib.parse import quote, urlsplit

from .card_data import parse_document, document_settings, selector_key, matching_keys, identity as face_identity, validate_targets
from .domain import ValidationError, github_location

FIELDS={'nickname','flavor_text','oracle_text','artist','art'}


def selector_order(key):
    return bool(key[0] or key[1]),sum(bool(value) for value in key),bool(key[1])


def face_values(entries,card,face):
    keys=sorted((key for key in matching_keys(card,face) if key in entries),key=selector_order)
    return {field:value for key in keys for field,value in entries[key].items() if field in FIELDS}


def location(settings):
    source=settings.get('dataJsonSource') or {}
    if not source and settings.get('githubSetupFolder'):
        loc=github_location(settings['githubSetupFolder'])
        loc['folder']='/'.join(part for part in (loc['folder'],'data.json') if part)
        return {**loc,'optional':True}
    if source.get('kind')!='github':return None
    value=source.get('value','')
    if value.startswith('https://'):
        loc=github_location(value)
        #Older card saves retained the project folder instead of its data file.
        parts=urlsplit(value).path.strip('/').split('/')
        if len(parts)>=4 and parts[2]=='tree' and loc['folder'].rsplit('/',1)[-1]!='data.json':
            loc['folder']='/'.join(part for part in (loc['folder'],'data.json') if part)
    else:
        root=settings.get('githubSetupFolder')
        if not root:raise ValidationError('Reconnect the GitHub data.json source in Art & Setup.')
        base=github_location(root)
        loc=github_location('https://github.com/'+base['repo']+'/blob/'+quote(base['ref'],safe='')+'/'+quote(value,safe='/'))
    if loc['folder'].rsplit('/',1)[-1]!='data.json':raise ValidationError('Choose a GitHub file named data.json.')
    return loc


def refresh(workspace, deck, cancel=lambda:False):
    loc=location(deck['settings'])
    if not loc:return deck
    if cancel():raise ValidationError('Preparation cancelled.')
    net=workspace.net
    if loc['default_ref']:
        loc['ref']=net.json('https://api.github.com/repos/'+loc['repo'],ttl=0).get('default_branch','main')
    identity={k:loc[k] for k in ('repo','ref','folder')}
    prior=deck.get('githubCardDataState') or {}
    same_source=prior.get('source')==identity
    faces={face['id']:face_identity(card,face) for card in deck.get('cards',[]) for face in card.get('faces',[])}
    commit=loc['ref'].lower()
    if not re.fullmatch(r'[0-9a-f]{40}',commit):
        result=net.json('https://api.github.com/repos/'+loc['repo']+'/commits/'+quote(loc['ref'],safe=''),ttl=0)
        commit=str(result.get('sha','')).lower() if isinstance(result,dict) else ''
    if not re.fullmatch(r'[0-9a-f]{40}',commit):raise ValidationError('GitHub did not return an exact commit for data.json.')
    if same_source and prior.get('commit')==commit and prior.get('faces')==faces:return deck
    if loc.get('optional'):
        #A project can acquire its first data.json after the deck was imported.
        #Check the pinned directory so a genuinely absent optional file is not an error.
        folder=loc['folder'].rpartition('/')[0]
        rows=net.json('https://api.github.com/repos/'+loc['repo']+'/contents/'+quote(folder,safe='/')+'?ref='+commit,immutable=True)
        if not isinstance(rows,list):raise ValidationError('GitHub did not return the project folder contents.')
        if not any(row.get('type')=='file' and row.get('name')=='data.json' for row in rows):return deck
    raw,_,_=net.fetch('https://raw.githubusercontent.com/'+loc['repo']+'/'+commit+'/'+quote(loc['folder'],safe='/'),immutable=True)
    entries=parse_document(raw)
    targets={key for card in deck.get('cards',[]) for face in card.get('faces',[]) for key in matching_keys(card,face)}
    # A shared project file can include tokens or cards absent from this deck.
    # Still validate ambiguous artwork mappings for the entries we will apply.
    validate_targets(deck,[entry for entry in entries if selector_key(entry) in targets])
    settings=document_settings(raw)
    if cancel():raise ValidationError('Preparation cancelled.')
    # Validate everything before touching the deck, then save with its revision.
    updated=copy.deepcopy(deck)
    if loc.get('optional'):
        updated['settings']['dataJsonSource']={'kind':'github','value':'https://github.com/'+loc['repo']+'/blob/'+quote(loc['ref'],safe='')+'/'+quote(loc['folder'],safe='/')}
    previous=prior.get('entries',[]) if same_source else deck.get('cardData',[])
    old={selector_key(e):e for e in previous}
    new={selector_key(e):e for e in entries}
    saved={selector_key(e):dict(e) for e in deck.get('cardData',[])}
    dirty=False
    for key in old.keys()|new.keys():
        if key not in targets:
            saved.pop(key,None)
            continue
        before=old.get(key,{})
        after=new.get(key,{})
        selector=after or before
        target=saved.setdefault(key,{k:v for k,v in selector.items() if k not in FIELDS})
        changes={field for field in FIELDS if before.get(field)!=after.get(field)}
        if not same_source:changes|=FIELDS&after.keys()
        for field in changes:
            if field in after:target[field]=after[field]
            elif target.get(field)==before.get(field):target.pop(field,None)
    for card in updated.get('cards',[]):
        for face in card.get('faces',[]):
            before=face_values(old,card,face);after=face_values(new,card,face)
            changes={field for field in FIELDS if before.get(field)!=after.get(field)}
            fresh_face=not same_source or prior.get('faces',{}).get(face['id'])!=faces[face['id']]
            if fresh_face:changes|=FIELDS&after.keys()
            changed=False
            for field in changes:
                box=face.setdefault('semanticOverrides',{}) if field in {'nickname','flavor_text','oracle_text'} else face
                slot={'artist':'artistOverride','art':'artFilename'}.get(field,field)
                if field=='oracle_text' and after.get(field)=='' and field in after:
                    if slot in box:box.pop(slot);changed=True
                elif field in after:
                    if box.get(slot)!=after[field]:box[slot]=after[field];changed=True
                elif box.get(slot)==before.get(field) and slot in box:
                    box.pop(slot);changed=True
                #Keep saved selector aliases consistent with the source update;
                #otherwise a later setup save can replay an older local value.
                for key in matching_keys(card,face):
                    row=saved.get(key)
                    if row is None or field not in row:continue
                    if field in after:row[field]=after[field]
                    elif row[field]==before.get(field):row.pop(field)
                if field=='art' and field in after:
                    from .artwork import face_key
                    defaults=updated['settings'].get('artDefaults',[])
                    updated['settings']['artDefaults']=[value for value in defaults if value!=face_key(card,face)]
            if changed:workspace.invalidate_face(face);dirty=True
    updated['cardData']=list(saved.values())
    from . import token_assignments
    for field in ('tokenAssignments','tokenTreatments','artVariants'):
        if field in settings and (not same_source or settings[field]!=prior.get('settings',{}).get(field)):
            updated['settings'][field]=settings[field]
        elif field=='artVariants' and same_source and field in prior.get('settings',{}) and field not in settings:
            updated['settings'][field]=[]
    old_specs={c['id']:copy.deepcopy(c.get('tokenSpec')) for c in updated['cards']}
    from . import art_variants
    if art_variants.apply(updated,workspace.invalidate_face):dirty=True
    old_specs.update({c['id']:copy.deepcopy(c.get('tokenSpec')) for c in updated['cards'] if c['id'] not in old_specs})
    token_assignments.apply_treatments(updated)
    for card in updated['cards']:
        if old_specs[card['id']]!=card.get('tokenSpec'):
            for face in card['faces']:workspace.invalidate_face(face)
            dirty=True
    old_settings=prior.get('settings',{}) if same_source else {}
    artist=settings.get('artist','')
    artist_changed='artist' in settings and (not same_source or artist!=old_settings.get('artist'))
    artist_removed=same_source and 'artist' in old_settings and 'artist' not in settings and updated['settings'].get('artist')==old_settings['artist']
    if artist_changed or artist_removed:
        if updated['settings'].get('artist')!=artist:
            updated['settings']['artist']=artist;dirty=True
            for card in updated.get('cards',[]):
                for face in card.get('faces',[]):workspace.invalidate_face(face)
    if dirty:
        updated['status']='draft'
        updated['settings']['artReviewSignature']=''
    updated['githubCardDataState']={'source':identity,'commit':commit,'entries':entries,'settings':settings,'faces':faces}
    workspace.store.put('decks',updated,deck['revision'])
    return workspace.deck(deck['id'])
