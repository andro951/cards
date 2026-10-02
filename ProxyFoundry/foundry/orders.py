"""Physical-card order snapshots with explicit, stable FRONT/BACK pairs."""
from __future__ import annotations
import json,os,tempfile,time,zipfile
from .domain import ConflictError,ValidationError,uid,stable_hash
class Orders:
    def __init__(self,workspace):self.ws=workspace;self.store=workspace.store
    def plan(self,deck_ids,acknowledge=False):
        if not deck_ids or len(set(deck_ids))!=len(deck_ids):raise ValidationError('Select one or more different decks.')
        physical=[];decks=[];warnings=[];issues=[]
        for ident in deck_ids:
            d=self.ws.deck(ident)
            if d.get('status')=='draft':raise ValidationError(d['name']+': prepare the latest changes before exporting.')
            decks.append({'id':d['id'],'name':d['name'],'revision':d['revision'],
                          'backAsset':d['settings'].get('backAsset')})
            for c in d['cards']:
                faces=c['faces'];front=self._render(faces[0],d['name'])
                if c.get('backOverride'):back=c['backOverride']
                elif c.get('meldBackAsset'):back=c['meldBackAsset']
                elif len(faces)==2:back=self._render(faces[1],d['name'])
                elif len(faces)==1:back=d['settings'].get('backAsset')
                else:raise ValidationError(c['name']+': expected one front or one front/back pair.')
                if not back or not self.store.asset(back):raise ValidationError(d['name']+': choose a back for '+c['name'])
                for f in faces:
                    comp=f.get('compiled') or {}
                    if f.get('acceptedWarningKey')!=comp.get('renderKey'):
                        reasons=[]
                        if (comp.get('crop') or {}).get('warning'):reasons.append('Part of the artwork is outside the frame.')
                        if comp.get('flags'):reasons.append('Card layout needs review.')
                        if reasons:
                            warning=d['name']+' / '+f['name']+': '+' '.join(reasons)
                            warnings.append(warning)
                            issues.append({'deckId':d['id'],'cardId':c['id'],'faceId':f['id'],
                                           'name':f['name'],'deckName':d['name'],'renderKey':comp['renderKey'],
                                           'frontAsset':self._render(f,d['name']),'warning':warning})
                for copy in range(c['quantity']):
                    physical.append({'deckId':d['id'],'deckName':d['name'],'cardId':c['id'],'name':c['name'],
                        'printingId':(c.get('scryfall') or {}).get('id'),'copy':copy+1,'frontAsset':front,'backAsset':back})
        if not physical:raise ValidationError('Selected decks contain no cards.')
        if len(physical)>10000:raise ValidationError('Split orders larger than 10,000 physical cards.')
        return {'cards':physical,'decks':decks,'warnings':list(dict.fromkeys(warnings)),'issues':issues,
                'count':len(physical),'bytes':sum(self.store.asset(c['frontAsset'])['size']+self.store.asset(c['backAsset'])['size'] for c in physical)}
    def _render(self,face,deck_name):
        if face.get('error'):raise ValidationError(deck_name+' / '+face['name']+': '+face['error'])
        r=self.store.render_get((face.get('compiled') or {}).get('renderKey',''))
        if not r:raise ValidationError(deck_name+' / '+face['name']+': render is missing or out of date.')
        return r['asset_id']
    def build(self,deck_ids,acknowledge=False,progress=lambda *a:None,cancel=lambda:False):
        steps=self.build_steps(deck_ids,acknowledge,progress,cancel)
        while True:
            try:next(steps)
            except StopIteration as finished:return finished.value
    def build_steps(self,deck_ids,acknowledge=False,progress=lambda *a:None,cancel=lambda:False):
        if cancel():raise ValidationError('Order packaging cancelled.')
        plan=self.plan(deck_ids)
        if plan['issues']:raise ValidationError('Review each crop/layout warning before packaging this order.')
        ident=uid();dest=self.store.home/'orders'/(ident+'.zip');tmp=dest.with_suffix('.partial')
        published=False
        try:
            with self.store.pin_assets(c[key] for c in plan['cards'] for key in ('frontAsset','backAsset')),zipfile.ZipFile(tmp,'w',zipfile.ZIP_STORED,allowZip64=True) as archive:
                for i,card in enumerate(plan['cards'],1):
                    if cancel():raise ValidationError('Order packaging cancelled.')
                    name=f'{i:06d}.png';card['index']=i;card['frontFile']='FRONT/'+name;card['backFile']='BACK/'+name
                    archive.write(self.store.asset_path(card['frontAsset']),card['frontFile'])
                    archive.write(self.store.asset_path(card['backAsset']),card['backFile'])
                    progress(i,len(plan['cards']),'Packaging '+card['name'])
                    yield
            if cancel():raise ValidationError('Order packaging cancelled.')
            for deck in plan['decks']:
                latest=self.store.get('decks',deck['id'])
                if not latest or latest['revision']!=deck['revision']:
                    raise ConflictError('A selected deck changed while packaging. Review it and create the order again.')
            os.replace(tmp,dest)
            manifest={**plan,'id':ident,'createdAt':time.time(),'pairing':'explicit-filename','snapshotHash':stable_hash(plan)}
            self.store.put('orders',manifest)
            published=True
            return {**manifest,'download':'/api/orders/'+ident+'/download','zipBytes':dest.stat().st_size}
        finally:
            tmp.unlink(missing_ok=True)
            if not published:dest.unlink(missing_ok=True)
