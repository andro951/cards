"""Reconcile a live deck list without preparing cards or replacing retained faces."""
import copy,re
from .domain import ConflictError,ValidationError,quantity
from .sources import deck_link
from . import art_variants,token_assignments


def local_card(card):
    #Missing legacy metadata is not proof that a card was added locally.
    return bool(card.get('deckLocal') or token_assignments.reference(card).get('copy'))


def retention_quality(card):
    faces=card['faces']
    return (sum(bool((face.get('compiled') or {}).get('render') or (face.get('lastRender') or {}).get('render')) for face in faces),
            sum(bool(face.get('compiled') or face.get('lastRender')) for face in faces))


def refresh_steps(ws,ident,payload,progress,cancel):
    if cancel():raise ValidationError('Deck refresh cancelled.')
    deck=ws.deck(ident);revision=payload.get('revision')
    if revision!=deck['revision']:raise ConflictError('Reload the deck before refreshing its cards.')
    if deck.get('pendingImport'):raise ValidationError('Wait for card details to finish before refreshing the deck.')
    link=deck_link(payload.get('sourceUrl') or deck.get('importedSource'))
    source=payload.get('source',link)
    if 'scryfall.com/' not in link and source==link:
        raise ValidationError('Refresh this deck through the browser helper, or supply its deck export.')
    progress(0,1,'Reading the latest deck list');yield
    listing=ws.sources.read_deck_manifest(source,cancel=cancel,allow_empty=True)
    if cancel():raise ValidationError('Deck refresh cancelled.')
    original=copy.deepcopy(deck['cards']);groups={};known={};local=[]
    for card in deck['cards']:
        if local_card(card):local.append(card);continue
        sf=card.get('scryfall') or {};key=(sf.get('id'),card.get('section','mainboard'))
        if not key[0]:raise ValidationError('Finish reading card details before refreshing this deck.')
        groups.setdefault(key,[]).append(card)
        aliases={sf['id'],sf.get('name'),card.get('metadataSource')}
        if sf.get('set') and sf.get('collector_number'):aliases.add(sf['set']+':'+sf['collector_number'])
        for alias in filter(None,aliases):known.setdefault(alias.casefold(),{})[sf['id']]=sf
    incoming={};resolved={};total=len(listing['rows'])
    for index,row in enumerate(listing['rows']):
        if cancel():raise ValidationError('Deck refresh cancelled.')
        source_key=row['source'];candidates=known.get(source_key.casefold(),{})
        sf=next(iter(candidates.values())) if len(candidates)==1 else resolved.get(source_key)
        if sf is None:sf=ws.sources.resolve_card(source_key);resolved[source_key]=sf
        key=(sf['id'],row['section'])
        if key in incoming:incoming[key]['quantity']=quantity(incoming[key]['quantity']+row['quantity'])
        else:incoming[key]={'sf':sf,'quantity':row['quantity'],'source':source_key}
        progress(index+1,total,'Checked '+sf['name']);yield
    #Prefer exact sections, then reuse a moved card's existing IDs and images.
    used={key for key in incoming if key in groups};matches={key:key for key in used};available={}
    for key in groups:
        if key not in used:available.setdefault(key[0],[]).append(key)
    for key in incoming:
        if key in matches:continue
        candidates=available.get(key[0],[]);moved=candidates.pop() if candidates else None
        if moved is not None:matches[key]=moved;used.add(moved)
    rows=deck['settings'].get('artVariants',[]);variant_updates={};removed_variants=set();cards=[]
    changes={'added':[],'removed':[],'quantityChanged':[],'moved':[],'retained':0,'local':len(local)}
    for key,item in incoming.items():
        if cancel():raise ValidationError('Deck refresh cancelled.')
        previous=groups.get(matches.get(key),[]);count=item['quantity']
        if not previous:
            card=ws.sources.entry(item['sf'],count,key[1]);card['metadataSource']=item['source']
            card['sourceIsExact']=bool(re.fullmatch(r'[0-9a-fA-F-]{36}',item['source']) or ':' in item['source'] or item['source'].startswith('https://'))
            cards.append(card);changes['added'].append({'name':card['name'],'quantity':count});continue
        changes['retained']+=1;old_count=sum(card['quantity'] for card in previous)
        if old_count!=count:changes['quantityChanged'].append({'name':previous[0]['scryfall']['name'],'before':old_count,'after':count})
        if matches[key][1]!=key[1]:changes['moved'].append({'name':previous[0]['scryfall']['name'],'from':matches[key][1],'to':key[1]})
        variants=[card for card in previous if card.get('artVariantId')];remaining=count
        for card in variants:
            allocated=min(card['quantity'],remaining);remaining-=allocated
            if allocated:variant_updates[card['artVariantId']]=allocated
            else:removed_variants.add(card['artVariantId'])
        #A previous refresh may have left an unrendered duplicate before its saved original.
        retained=previous if variants else [max(previous,key=retention_quality)]
        for index,card in enumerate(retained):
            card['quantity']=count if index==0 else 0;card['section']=key[1];cards.append(card)
    for key,previous in groups.items():
        if key not in used:
            changes['removed'].append({'name':previous[0]['scryfall']['name'],'quantity':sum(card['quantity'] for card in previous)})
            removed_variants.update(card['artVariantId'] for card in previous if card.get('artVariantId'))
    deck['cards']=cards
    if sum(card['quantity'] for card in cards+local)>10000:raise ValidationError('Deck limit is 10,000 physical cards, including locally added cards.')
    updated_rows=[];owners={card['artVariantId']:card for card in cards if card.get('artVariantId')}
    for row in rows:
        if row['id'] in removed_variants:continue
        updated=copy.deepcopy(row)
        if row['id'] in variant_updates:
            updated['quantity']=variant_updates[row['id']]
            owner=owners[row['id']]
            if 'section' in updated['card']:updated['card']['section']=owner['section']
        updated_rows.append(updated)
    if 'artVariants' in deck['settings']:deck['settings']['artVariants']=updated_rows
    if art_variants.apply(deck,ws.invalidate_face):deck['status']='draft'
    deck['cards'].extend(local)
    before=token_assignments.CardReferences(original);after=token_assignments.CardReferences(deck['cards'])
    def survives(ref):return before.resolve(ref) is None or after.resolve(ref) is not None
    if 'tokenAssignments' in deck['settings']:
        deck['settings']['tokenAssignments']=[row for row in deck['settings']['tokenAssignments']
            if survives(row['front']) and (row['back'].get('kind') or survives(row['back']))]
    if 'tokenTreatments' in deck['settings']:
        deck['settings']['tokenTreatments']=[row for row in deck['settings']['tokenTreatments'] if survives(row['face'])]
    token_assignments.apply_treatments(deck)
    if changes['added']:deck['status']='draft'
    deck['importedSource']=link;deck.pop('includeOutside',None);deck.pop('summary',None);deck.pop('metadataBaseRevision',None)
    #No partial list is published, and edits/deletion during the fetch cannot be overwritten.
    if cancel():raise ValidationError('Deck refresh cancelled.')
    current=ws.store.get('decks',ident)
    if not current or current['revision']!=revision:raise ConflictError('The deck changed during refresh. Reload it and try again.')
    progress(total,total,'Saving refreshed deck');yield
    if cancel():raise ValidationError('Deck refresh cancelled.')
    saved=ws.store.put('decks',deck,revision)
    return {'deck':ws.deck(saved['id']),'changes':changes}
