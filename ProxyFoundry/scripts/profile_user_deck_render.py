"""Recover the user's Supernatural preparation inputs into an isolated benchmark.

The source workspace is opened read-only. No source images or decks are changed.
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from foundry.server import App
from foundry.storage import Store
from foundry.images import ingest_image
from foundry.domain import slug,type_group
from foundry.legacy import ingest


def recover():
    output=ROOT/'test-results/user-deck-workers';output.mkdir(parents=True,exist_ok=True)
    source=Path('D:/isaac/Documents/BulkProxyForge')
    connection=sqlite3.connect('file:'+(source/'workspace.sqlite3').as_posix()+'?mode=ro',uri=True)
    metadata=[]
    for url,ident in connection.execute('SELECT url,asset_id FROM http_cache WHERE url LIKE ?',('%api.scryfall.com/cards/%',)):
        try:
            item=json.loads((source/'assets'/ident[:2]/ident).read_bytes())
            if item.get('object')=='card':metadata.append(item)
        except (OSError,ValueError):continue
    connection.close()
    data=json.loads((ROOT.parent/'supernatural/data.json').read_text(encoding='utf-8'))
    store=Store(output/'workspace');app=App(store);parents={}
    for row in data['cards']:
        candidates=[card for card in metadata if card.get('oracle_id')==row.get('oracle_id')]
        path=re.search(r'/card/([^/?]+)/([^/?]+)',row.get('scryfall_url',''))
        selected=next((card for card in candidates if path and card.get('set')==path[1] and card.get('collector_number')==path[2]),None)
        if not selected:selected=next((card for card in candidates if card.get('name')==row['name'] or any(face.get('name')==row['name'] for face in card.get('card_faces',[]))),None)
        if not selected:
            if not path:raise ValueError('Missing printing reference: '+row['name'])
            selected=json.loads(app.ws.net.fetch('https://api.scryfall.com/cards/'+path[1]+'/'+path[2])[0])
        parents[selected['id']]=selected
    cards=[app.ws.sources.entry(card,1,'mainboard') for card in parents.values()]
    local={};names={}
    for path in (ROOT.parent/'supernatural/art').glob('*.png'):
        asset=ingest_image(store,path.read_bytes());key=slug(path.stem);local[key]=asset['id'];names[key]=path.name
    symbols={rarity:ingest_image(store,(ROOT.parent/'supernatural/set_symbol'/(rarity+'.png')).read_bytes(),trim_transparent_padding=True)['id'] for rarity in ['common','uncommon','rare','mythic']}
    deck=app.ws.new_deck('Supernatural worker benchmark')
    deck['cards']=cards
    deck['settings'].update(source={'mode':'local','localFiles':local,'localNames':names,'fallback':False},symbols=symbols,artist='ChatGPT',acceptCropWarnings=True,acceptLayoutWarnings=True)
    for card in cards:
        raw_faces=ingest.face_list(card['scryfall'])
        for face in card['faces']:
            group=type_group(raw_faces[face['index']],card['scryfall'],face['index'])
            if group in {'land','legendary-land','basic-land'}:face['templateOverride']='godzilla-land'
            elif group in {'standard','legendary','modal-front','modal-back','transform-front','transform-back'}:face['templateOverride']='godzilla-card'
            elif group=='token':face['templateOverride']='token-full-art'
            if 'Germ' in face['name']:face['artFilename']='105_germ.png'
    app.ws._apply_card_data(deck,data['cards']);store.put('decks',deck,deck['revision'])
    deck=app.ws.prepare(deck['id'],progress=lambda done,total,message:print(done,total,message,flush=True) if done%20==0 else None)
    errors=[(face['name'],face['error']) for card in deck['cards'] for face in card['faces'] if face.get('error')]
    if errors:raise RuntimeError(errors)
    prepared=[{'name':face['name'],'key':face['compiled']['renderKey'],'data':face['compiled']['data']} for card in deck['cards'] for face in card['faces']]
    report={'name':'Supernatural','cards':len(cards),'faces':len(prepared),'source':'Read-only cached Scryfall printings plus the repository supernatural/data.json and numbered artwork. Quantities do not affect unique-face rendering.','deck':deck,'data':prepared}
    (output/'prepared.json').write_text(json.dumps(report),encoding='utf-8')
    app.close();print('Recovered',len(cards),'cards',len(prepared),'faces',flush=True)
    return output


if __name__=='__main__':recover()
