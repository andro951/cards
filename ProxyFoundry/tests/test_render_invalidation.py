"""Edits keep review evidence and do not invalidate unrelated cached faces."""
import copy
import io
import json

from PIL import Image

from foundry.network import Network
from foundry.storage import Store
from foundry.workspace import Workspace


def test_face_edit_retains_previous_render_and_reuses_other_faces(tmp_path):
    store=Store(tmp_path)
    card={'id':'11111111-1111-4111-8111-111111111111','name':'Test Creature',
          'layout':'normal','type_line':'Creature — Wizard','colors':['U'],
          'mana_cost':'{U}','oracle_text':'Flying','rarity':'common',
          'power':'1','toughness':'1','artist':'Test Artist',
          'image_uris':{'art_crop':'https://cards.scryfall.io/test.png'}}
    image=io.BytesIO();Image.new('RGB',(900,650),'blue').save(image,'PNG')
    def transport(url):
        if 'api.scryfall.com' in url:return json.dumps(card).encode(),'application/json',{}
        return image.getvalue(),'image/png',{}
    ws=Workspace(store,Network(store,transport=transport,sleeper=lambda _:None))
    deck=ws.create({'source':card['id']})
    duplicate=copy.deepcopy(deck['cards'][0])
    duplicate['id']='22222222-2222-4222-8222-222222222222'
    duplicate['faces'][0]['id']='33333333-3333-4333-8333-333333333333'
    deck['cards'].append(duplicate)
    store.put('decks',deck,deck['revision'])
    deck=ws.prepare(deck['id'])
    before=deck['cards'][0]['faces'][0]['compiled']
    rendered=io.BytesIO();Image.new('RGB',(before['data']['width'],before['data']['height']),'orange').save(rendered,'PNG')
    other_key=deck['cards'][1]['faces'][0]['compiled']['renderKey']
    for entry in deck['cards']:
        compiled=entry['faces'][0]['compiled']
        ws.save_render(compiled['renderKey'],rendered.getvalue(),(compiled['data']['width'],compiled['data']['height']))
    deck=ws.deck(deck['id'])
    entry=deck['cards'][0]
    changed=ws.mutate_card(deck['id'],entry['id'],{'revision':deck['revision'],
        'faceId':entry['faces'][0]['id'],'semanticOverrides':{'oracle_text':'Flying. Vigilance.'}})
    face=changed['cards'][0]['faces'][0]
    assert 'compiled' not in face
    assert face['lastRender']['render']['url']==store.render_get(before['renderKey'])['url']
    assert not changed.get('upgradeRequired')
    assert changed['cards'][1]['faces'][0]['compiled']['renderKey']==other_key
    ws.prepare(deck['id'])
    plan=ws.render_targets([deck['id']])
    assert len(plan['targets'])==1 and plan['cached']==1
    assert plan['targets'][0]['cardId']==entry['id']


def test_new_deck_is_dirty_without_claiming_pipeline_upgrade(tmp_path):
    ws=Workspace(Store(tmp_path))
    deck=ws.new_deck()
    assert not ws.deck(deck['id']).get('upgradeRequired')
