"""Measure preparation only against live sources in an isolated workspace.

Run with PYTHONPATH set to the application directory. No card images are rendered.
"""
import argparse
import json
import tempfile
import time
from pathlib import Path

import foundry.timing as timings
from foundry.domain import uid
from foundry.network import Network
from foundry.storage import Store
from foundry.workspace import Workspace


class TimingCollector:
    def __init__(self):self.events=[]
    def info(self,format,body):self.events.append(json.loads(body))


def measure(ws,deck_id,label):
    collector=TimingCollector();ws.store.timing_logger=collector
    hits,misses=ws.net.hits,ws.net.misses;progress=[]
    started=time.perf_counter()
    deck=ws.prepare(deck_id,progress=lambda done,total,message:progress.append(message))
    elapsed=time.perf_counter()-started
    errors=[face['error'] for card in deck['cards'] for face in card['faces'] if face.get('error')]
    if errors:raise RuntimeError(errors)
    totals={}
    for event in collector.events:totals[event['stage']]=totals.get(event['stage'],0)+event['seconds']
    return {'label':label,'seconds':elapsed,'networkDownloads':ws.net.misses-misses,
            'networkCacheReads':ws.net.hits-hits,'stages':totals,'events':collector.events,
            'progress':progress,'rendered':deck['summary']['rendered']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='test-results/preparation-timing.json')
    parser.add_argument('--source',choices=['github','scryfall'],default='github')
    args=parser.parse_args();timings.THRESHOLD_SECONDS=0
    # Setup choices and bundled symbols already exist when preparation begins.
    # The selected printing's remaining metadata and artwork are deliberately cold.
    home=Path(tempfile.mkdtemp(prefix='bpf-preparation-benchmark-'))
    store=Store(home);ws=Workspace(store,Network(store));deck=ws.new_deck('Preparation timing: Fighter Class')
    sf={'id':'afr:222','name':'Fighter Class','layout':'normal','type_line':'Enchantment — Class'}
    card={'id':uid(),'name':sf['name'],'quantity':1,'sourceIsExact':True,'scryfall':sf,
          'faces':[{'id':uid(),'name':sf['name'],'index':0}]}
    if args.source=='github':
        deck['settings']['source']={'mode':'github','githubFolder':'https://github.com/andro951/cards/tree/main/supernatural/art','fallback':False}
    store.put('decks',{**deck,'cards':[card]},deck['revision'])
    cold=measure(ws,deck['id'],'new card, cold metadata and artwork')
    warm=measure(ws,deck['id'],'same card, cached preparation')
    store=Store(home);ws=Workspace(store,Network(store))
    restarted=measure(ws,deck['id'],'same card, cached after restart')
    for run in (warm,restarted):
        if 'card.compile' in run['stages'] or 'image.decode' in run['stages']:
            raise RuntimeError('The cached run unexpectedly rebuilt a card: '+run['label'])
    assert all(run['rendered']==0 for run in (cold,warm,restarted))
    report={'source':args.source,'workspace':str(home),'card':'Fighter Class (AFR 222)',
            'scope':'Preparation only; no rendering or output-image generation.',
            'setupExcluded':'Creating the deck and its default back/symbols before the user starts preparation.',
            'runs':[cold,warm,restarted]}
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    for run in report['runs']:
        print(run['label'],round(run['seconds'],4),'seconds;',run['networkDownloads'],'downloads')
        print(json.dumps(run['stages'],indent=2))
    print('Report:',output.resolve())


if __name__=='__main__':main()
