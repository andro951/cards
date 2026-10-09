"""Recover browser-native PNG writes before publishing grouped SQLite metadata."""
import json,re,time
from .domain import ValidationError,uid


def allow_shared_render_files(db):
    #Same columns and schema version; only relax the legacy duplicate-file constraint.
    schema=db.execute("SELECT sql FROM sqlite_master WHERE name='renders'").fetchone()[0]
    if not re.search(r'file_path\s+TEXT\s+NOT\s+NULL\s+UNIQUE',schema,re.I):return
    db.execute('BEGIN IMMEDIATE')
    db.execute('CREATE TABLE renders_shared (render_key TEXT PRIMARY KEY,asset_id TEXT NOT NULL,width INTEGER NOT NULL,height INTEGER NOT NULL,created REAL NOT NULL,deck_id TEXT,card_id TEXT,face_id TEXT UNIQUE,file_path TEXT NOT NULL)')
    db.execute('INSERT INTO renders_shared SELECT * FROM renders')
    db.execute('DROP TABLE renders')
    db.execute('ALTER TABLE renders_shared RENAME TO renders')
    db.execute('CREATE INDEX renders_deck_idx ON renders(deck_id)')


def commit_render_saves(app,strict=False):
    store=app.store;folder=store.home/'tmp'/'render-pending'
    if not folder.is_dir():return {'registered':0}
    receipts=[];decks={};registered=0;obsolete=[];errors=[]
    for path in sorted(folder.glob('*.json')):
        try:
            if path.stat().st_size>4096:raise ValidationError('Oversized render receipt.')
            row=json.loads(path.read_text())
            if not isinstance(row,dict):raise ValidationError('Invalid render receipt.')
            if not all(re.fullmatch('[0-9a-f]{64}',str(row.get(k,''))) for k in ('key','hash')):
                raise ValidationError('Invalid render receipt identifier.')
            deck_id=row.get('deckId')
            if not isinstance(deck_id,str):raise ValidationError('Missing render deck.')
            if deck_id not in decks:decks[deck_id]=store.get('decks',deck_id)
            deck=decks[deck_id]
            face=next((f for c in (deck or {}).get('cards',[]) if c.get('id')==row.get('cardId') for f in c.get('faces',[]) if f.get('id')==row.get('faceId')),None)
            comp=(face or {}).get('compiled') or {}
            if comp.get('renderKey')!=row['key']:
                obsolete.append(path);errors.append('A rendered card changed or was deleted. Generate its image again.');continue
            data=comp.get('data') or {}
            expected=[round(data['width']*(1+2*data.get('marginX',0))),round(data['height']*(1+2*data.get('marginY',0)))]
            if [row.get('width'),row.get('height')]!=expected:raise ValidationError('Wrong render receipt dimensions.')
            asset=store.asset_path(row['hash'])
            size=asset.stat().st_size
            if size!=row.get('bytes') or not 33<=size<=64*1024*1024:raise ValidationError('Incomplete rendered PNG.')
            with asset.open('rb') as image:header=image.read(24)
            if header[:8]!=b'\x89PNG\r\n\x1a\n' or [int.from_bytes(header[16:20],'big'),int.from_bytes(header[20:24],'big')]!=expected:
                raise ValidationError('Invalid rendered PNG header.')
            receipts.append((path,row))
        except (ValueError,TypeError,KeyError,ValidationError,FileNotFoundError) as error:
            #Keep damaged receipts for diagnostics; a broken image never becomes a cache hit.
            app.log.warning('RENDER_RECEIPT_REJECTED file=%s error=%s',path.name,error)
            errors.append(str(error))
            path.rename(path.with_suffix('.rejected'))
    if receipts:
        cleanup=[]
        with store.render_save():
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                for _,row in receipts:
                    old=db.execute('SELECT * FROM renders WHERE face_id=? OR render_key=?',(row['faceId'],row['key'])).fetchall()
                    now=time.time();ident=row['hash'];rel='assets/'+ident[:2]+'/'+ident
                    db.execute('INSERT OR REPLACE INTO assets VALUES (?,?,?,?,?,?)',(ident,'image/png',row['bytes'],row['width'],row['height'],now))
                    db.execute('DELETE FROM renders WHERE face_id=? OR render_key=?',(row['faceId'],row['key']))
                    db.execute('INSERT INTO renders VALUES (?,?,?,?,?,?,?,?,?)',(row['key'],ident,row['width'],row['height'],now,row['deckId'],row['cardId'],row['faceId'],rel))
                    for previous in old:
                        file=previous['file_path'] if previous['file_path']!=rel and previous['file_path'].startswith('renders/') else None
                        asset=previous['asset_id'] if previous['asset_id']!=ident else None
                        if file or asset:cleanup.append({'file':file,'asset':asset})
                    registered+=1
                if cleanup:
                    db.execute('INSERT INTO documents VALUES (?,?,?,?,?,?,?)',('cleanup','render-'+uid(),1,json.dumps({'tasks':cleanup}),now,now,0))
        #Metadata must be durable before receipts or old assets can be removed.
        for path,_ in receipts:path.unlink(missing_ok=True)
    for path in obsolete:path.unlink(missing_ok=True)
    if strict and errors:raise ValidationError(errors[0])
    return {'registered':registered}