"""Complete, portable data.json deck recipes, separate from workspace backups."""
import copy
import hashlib
import json
import re
from .domain import ValidationError,uid,quantity,CC_COMMIT,CC_REPO,PIPELINE_VERSION,validate_template
from .backup import referenced_assets
from .substitutes import stored_faces
from .network import validate_remote_url
from .images import decode_image,ingest_image,sanitize_svg
from pathlib import Path
from urllib.parse import quote,urlsplit,unquote_to_bytes

MAX_DOCUMENT_BYTES=20*1024**2
HASH=re.compile(r'^[a-f0-9]{64}$')
UUID=re.compile(r'^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$',re.I)
EMPTY_IMAGE='builtin:transparent-pixel'
VECTOR_PREFIX='builtin:generated-vector:'


def vector_source(recipe):
    """Build passive vector frame layers from drawing instructions, not image bytes."""
    import xml.etree.ElementTree as ET
    count=0
    def build(node,depth=0):
        nonlocal count
        count+=1
        if depth>64 or count>20000 or not isinstance(node,dict):raise ValidationError('Invalid vector drawing instructions.')
        if set(node)!={'tag','attributes','text','tail','children'} or not isinstance(node['tag'],str) or not isinstance(node['attributes'],dict) or not isinstance(node['children'],list):
            raise ValidationError('Invalid vector drawing instructions.')
        if any(not isinstance(k,str) or not isinstance(v,str) for k,v in node['attributes'].items()) or any(v is not None and not isinstance(v,str) for v in (node['text'],node['tail'])):
            raise ValidationError('Invalid vector drawing instructions.')
        item=ET.Element(node['tag'],node['attributes']);item.text=node['text'];item.tail=node['tail']
        item.extend(build(child,depth+1) for child in node['children'])
        return item
    if not isinstance(recipe,dict) or set(recipe)!={'kind','root'} or recipe['kind']!='svg':raise ValidationError('Unsupported vector drawing recipe.')
    raw=ET.tostring(build(recipe['root']),encoding='utf-8')
    return 'data:image/svg+xml,'+quote(sanitize_svg(raw).decode(),safe='')


def vector_identity(recipe):
    return hashlib.sha256(json.dumps(recipe,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def map_images(value,store=None,restore=False,vectors=None):
    from .template_model import TRANSPARENT
    if isinstance(value,dict):return {key:map_images(item,store,restore,vectors) for key,item in value.items()}
    if isinstance(value,list):return [map_images(item,store,restore,vectors) for item in value]
    if restore and isinstance(value,str) and value.startswith(VECTOR_PREFIX):
        recipe=(vectors or {}).get(value[len(VECTOR_PREFIX):])
        return vector_source(recipe)
    if restore and value==EMPTY_IMAGE:return TRANSPARENT
    if not restore and value==TRANSPARENT:return EMPTY_IMAGE
    if not restore and isinstance(value,str) and value.startswith('data:image/'):
        import base64
        try:
            header,payload=value.split(',',1)
            raw=base64.b64decode(payload,validate=True) if ';base64' in header.lower() else unquote_to_bytes(payload)
        except (ValueError,IndexError) as error:raise ValidationError('Invalid embedded source image.') from error
        if header.split(';',1)[0].lower()=='data:image/svg+xml':
            import xml.etree.ElementTree as ET
            def drawing(node):return {'tag':node.tag,'attributes':dict(node.attrib),'text':node.text,'tail':node.tail,'children':[drawing(child) for child in node]}
            recipe={'kind':'svg','root':drawing(ET.fromstring(sanitize_svg(raw)))}
            ident=vector_identity(recipe)
            if vectors is None:raise ValidationError('Vector drawing registry is missing.')
            vectors[ident]=recipe
            return VECTOR_PREFIX+ident
        asset=ingest_image(store,raw)
        return '/api/assets/'+asset['id']
    return value


def recipe_fingerprint(deck):
    from .domain import stable_hash
    ignored={'compiled','lastRender','preparedAt','preparationKey','acceptedArt','acceptedWarningKey','originalArtist','group','_preparationSymbols','error'}
    def inputs(item):
        if isinstance(item,dict):return {key:inputs(value) for key,value in item.items() if key not in ignored}
        if isinstance(item,list):return [inputs(value) for value in item]
        return item
    return stable_hash(inputs({'cards':deck['cards'],'settings':deck['settings']}))


def reusable_recipe(deck):
    snapshot=deck.get('recipeSnapshot')
    return bool(snapshot and snapshot.get('fingerprint')==recipe_fingerprint(deck) and
                all(face.get('compiled') and not face.get('error') for card in deck['cards'] for face in stored_faces(card)))


def is_complete(value):
    return isinstance(value,dict) and value.get('version')==2 and value.get('format')=='bulk-proxy-forge-deck'


def required_images(value):
    found=set()
    def visit(item):
        if isinstance(item,dict):
            for key,v in item.items():
                if key in {'artId','artOverride','backAsset','backOverride','meldBackAsset','iconAsset','asset_id'} and isinstance(v,str) and HASH.fullmatch(v):found.add(v)
                visit(v)
        elif isinstance(item,list):
            for v in item:visit(v)
        elif isinstance(item,str):found.update(re.findall(r'/api/assets/([a-f0-9]{64})',item))
    visit([value['deck'],value.get('templates',[])])
    settings=value['deck']['settings']
    found.update(settings.get('symbols',{}).values())
    found.update(settings.get('source',{}).get('localFiles',{}).values())
    return found


def validate(value,*,require_renderer=True):
    if not is_complete(value):raise ValidationError('Choose a complete Bulk Proxy Forge data.json (version 2).')
    if value.get('includesRenders') is not False:raise ValidationError('Complete data.json stores build inputs, not generated images.')
    renderer=value.get('renderer')
    if not isinstance(renderer,dict) or (require_renderer and (renderer.get('commit')!=CC_COMMIT or renderer.get('pipeline')!=PIPELINE_VERSION)):
        raise ValidationError('This deck recipe needs a different renderer version. Use its recorded Bulk Proxy Forge release to rebuild it exactly.')
    deck=value.get('deck')
    vectors=value.get('vectors',{})
    if not isinstance(vectors,dict) or len(vectors)>10000:raise ValidationError('Invalid vector drawing registry.')
    for ident,recipe in vectors.items():
        if not HASH.fullmatch(ident) or vector_identity(recipe)!=ident:raise ValidationError('Invalid vector drawing identity.')
        vector_source(recipe)
    def check_vectors(item):
        if isinstance(item,dict):
            for v in item.values():check_vectors(v)
        elif isinstance(item,list):
            for v in item:check_vectors(v)
        elif isinstance(item,str) and item.startswith(VECTOR_PREFIX) and item[len(VECTOR_PREFIX):] not in vectors:
            raise ValidationError('A required vector drawing recipe is missing.')
    check_vectors([deck,value.get('templates',[])])
    if not isinstance(deck,dict) or not isinstance(deck.get('settings'),dict) or not isinstance(deck.get('cards'),list):
        raise ValidationError('The complete data.json is missing its deck or settings.')
    if not UUID.fullmatch(str(deck.get('id',''))):raise ValidationError('Invalid data.json deck identifier.')
    from .card_data import validate_entries
    if not isinstance(value.get('cards'),list):raise ValidationError('data.json cards must be an array.')
    validate_entries(value['cards'])
    for field in ('source','symbols','templateRules'):
        if not isinstance(deck['settings'].get(field,{}),dict):raise ValidationError('Invalid complete deck '+field+' settings.')
    def no_embedded_images(item):
        if isinstance(item,dict):
            for v in item.values():no_embedded_images(v)
        elif isinstance(item,list):
            for v in item:no_embedded_images(v)
        elif isinstance(item,str) and item.lower().startswith(('data:image/','blob:')):
            raise ValidationError('Replace embedded or temporary images with permanent image locations before exporting data.json.')
    no_embedded_images(value)
    if not isinstance(deck.get('name'),str) or not deck['name'].strip() or len(deck['name'])>200:
        raise ValidationError('The complete data.json needs a valid deck name.')
    if len(deck['cards'])>10000:raise ValidationError('The complete data.json contains too many cards.')
    seen=set()
    for card in deck['cards']:
        if not isinstance(card,dict) or not isinstance(card.get('scryfall'),dict) or not isinstance(card.get('faces'),list) or not 1<=len(card['faces'])<=2:
            raise ValidationError('The complete data.json contains an invalid card.')
        quantity(card.get('quantity'))
        for item in [card,*stored_faces(card)]:
            ident=item.get('id') if isinstance(item,dict) else None
            if not isinstance(ident,str) or not UUID.fullmatch(ident) or ident in seen:
                raise ValidationError('The complete data.json contains invalid or duplicate card/face identifiers.')
            seen.add(ident)
        for face in stored_faces(card):
            # Native textless/basic-land layouts intentionally omit text boxes.
            # Keep structural/script validation without treating renders as
            # user-authored reusable templates.
            if face.get('compiled'):validate_template(face['compiled'].get('data'),require_text_boxes=False)
    images=value.get('images')
    if not isinstance(images,dict) or len(images)>25000:raise ValidationError('Invalid data.json image sources.')
    for ident,entry in images.items():
        if not HASH.fullmatch(ident) or not isinstance(entry,dict) or entry.get('sha256')!=ident:
            raise ValidationError('Invalid data.json image identity.')
        if not isinstance(entry.get('mime'),str) or not entry['mime'].startswith('image/'):
            raise ValidationError('A data.json source is not an image.')
        if 'base64' in entry:raise ValidationError('Complete data.json files use image locations, not embedded images.')
        if ('recipe' in entry)==('url' in entry):raise ValidationError('Each image needs one permanent HTTPS source or a build recipe.')
        if 'url' in entry:
            validate_remote_url(entry['url'])
            if entry.get('transform','raw') not in {'raw','image','trim-transparent'}:raise ValidationError('Unsupported image source transform.')
        elif not isinstance(entry['recipe'],dict) or entry['recipe'].get('kind')!='back-icon' or not HASH.fullmatch(str(entry['recipe'].get('icon',''))):
            raise ValidationError('Unsupported image build recipe.')
    templates=value.get('templates',[])
    if not isinstance(templates,list) or len(templates)>1000:raise ValidationError('Invalid data.json templates.')
    template_ids=set()
    for template in templates:
        if not isinstance(template,dict) or not UUID.fullmatch(str(template.get('id',''))) or template['id'] in template_ids:
            raise ValidationError('Invalid or duplicate data.json template.')
        template_ids.add(template['id'])
        if template.get('schemaVersion') in {2,3}:
            from .template_model import validate_model
            validate_model(template)
        else:validate_template(template.get('data'))
    if not required_images(value)<=set(images):raise ValidationError('The data.json is missing a required image source.')
    visited=set()
    def recipe_dependencies(ident,active):
        if ident in active:raise ValidationError('Circular image build recipe.')
        if ident in visited:return
        if ident not in images:raise ValidationError('A required image source is missing from data.json.')
        entry=images[ident]
        if 'recipe' in entry:recipe_dependencies(entry['recipe']['icon'],active|{ident})
        visited.add(ident)
    for ident in images:recipe_dependencies(ident,set())
    return value


def permanent_url(workspace,url):
    parsed=urlsplit(str(url))
    if parsed.hostname in {'github.com','www.github.com','raw.githubusercontent.com'}:
        from .domain import github_location
        loc=github_location(url)
        commit=loc['ref']
        if not re.fullmatch(r'[a-f0-9]{40}',commit):
            commit=workspace.net.fresh_json('https://api.github.com/repos/'+loc['repo']+'/commits/'+quote(commit,safe=''))['sha']
        if not re.fullmatch(r'[a-f0-9]{40}',commit):raise ValidationError('Could not pin the image source to a GitHub commit.')
        url='https://raw.githubusercontent.com/'+loc['repo']+'/'+commit+'/'+quote(loc['folder'],safe='/')
    return validate_remote_url(url)


def source_for_image(workspace,ident,url):
    url=permanent_url(workspace,url)
    raw,mime,_=workspace.net.fetch(url,immutable=True)
    if hashlib.sha256(raw).hexdigest()==ident:return {'url':url,'transform':'raw'}
    for trim in (False,True):
        asset=ingest_image(workspace.store,raw,trim_transparent_padding=trim)
        if asset['id']==ident:return {'url':url,'transform':'trim-transparent' if trim else 'image'}
    raise ValidationError('The image at this URL does not match the selected image. Publish the original image or its saved processed version.')


def export_document(workspace,ident,*,allow_missing=False):
    deck=copy.deepcopy(workspace.deck(ident))
    deck.setdefault('recipeId',deck['id'])
    for field in ('summary','tokens','printStatus','upgradeRequired','revision','createdAt','updatedAt','deleted','githubCardDataState'):
        deck.pop(field,None)
    templates={}
    for value in [*deck['settings'].get('templateRules',{}).values(),
                  *(face.get('templateOverride') for card in deck['cards'] for face in stored_faces(card))]:
        template=workspace.store.get('templates',value) if value else None
        if template:
            template=copy.deepcopy(template)
            for field in ('revision','createdAt','updatedAt','deleted'):template.pop(field,None)
            templates[value]=template
    for card in deck['cards']:
        for face in stored_faces(card):
            face.pop('lastRender',None)
            compiled=face.get('compiled') or {}
            compiled.pop('render',None)
    deck.pop('recipeSnapshot',None)
    vectors={}
    deck=map_images(deck,workspace.store,vectors=vectors)
    templates=map_images(templates,workspace.store,vectors=vectors)
    value={'version':2,'format':'bulk-proxy-forge-deck','cards':copy.deepcopy(deck.get('cardData',[])),
           'artist':deck['settings'].get('artist',''),'deck':deck,'templates':list(templates.values()),'images':{},
           'renderer':{'pipeline':PIPELINE_VERSION,'repository':CC_REPO,'commit':CC_COMMIT},
           'includesRenders':False}
    if vectors:value['vectors']=vectors
    for field in ('tokenAssignments','tokenTreatments','artVariants'):
        if field in deck['settings']:value[field]=copy.deepcopy(deck['settings'][field])
    with workspace.store.connect() as db:
        sources={}
        source_rows=list(db.execute('SELECT asset_id,url FROM http_cache ORDER BY fetched DESC'))
        for row in source_rows:
            sources.setdefault(row['asset_id'],row['url'])
    # Setup imports crop symbols/back icons. Their processed content hashes do
    # not match the original downloads in http_cache. Retain the source recipe,
    # and recover historical imports from the existing URL/trim cache identity.
    from .domain import stable_hash
    setup_images={item['id']:item for item in workspace.store.list('github-setup-images')}
    processed_sources={}
    for item in setup_images.values():
        if item.get('source'):processed_sources.setdefault(item['assetId'],item['source'])
    for row in source_rows:
        if not row['url'].startswith('https://raw.githubusercontent.com/'):continue
        for trim in (True,False):
            cached=setup_images.get(stable_hash({'url':row['url'],'trim':trim,'version':1}))
            if cached:processed_sources.setdefault(cached['assetId'],{'url':row['url'],'transform':'trim-transparent' if trim else 'image'})
    #Known package images have permanent GitHub locations. Preserve the exact
    #normalization step used when bundled symbols were imported.
    root=Path(__file__).resolve().parents[1]
    try:commit=json.loads((root/'build.json').read_text())['sourceCommit']
    except (OSError,ValueError,KeyError):commit='506a2e62bce8b8f39423e7580c40907306d04792'
    value['renderer']['applicationCommit']=commit
    bundled={}
    for directory in ('symbols','backs','substitutes'):
        for path in (root/'assets'/directory).glob('*.png'):
            raw=path.read_bytes();raw_id=hashlib.sha256(raw).hexdigest()
            url='https://raw.githubusercontent.com/andro951/cards/'+commit+'/ProxyFoundry/'+path.relative_to(root).as_posix()
            bundled[raw_id]={'url':url,'transform':'raw'}
            if directory=='symbols':
                asset=ingest_image(workspace.store,raw,trim_transparent_padding=True)
                bundled[asset['id']]={'url':url,'transform':'trim-transparent'}
    recipes={item['assetId']:{'recipe':{'kind':'back-icon','icon':item['design']['iconAsset']}}
             for item in workspace.store.list('backComposites') if item.get('design',{}).get('iconAsset')}
    ids=referenced_assets([deck,value['templates']])
    ids.update(recipe['recipe']['icon'] for ident,recipe in recipes.items() if ident in ids)
    missing=[]
    labels={}
    for rarity,asset in deck['settings'].get('symbols',{}).items():labels[asset]=rarity.title()+' set symbol'
    if deck['settings'].get('backAsset'):labels[deck['settings']['backAsset']]='Deck back'
    for card in deck['cards']:
        for face in stored_faces(card):
            asset=(face.get('compiled') or {}).get('artId') or face.get('artOverride')
            if asset:labels.setdefault(asset,face.get('name',card.get('name','Card'))+' artwork')
    for asset_id in sorted(ids):
        asset=workspace.store.asset(asset_id)
        if not asset or not asset['mime'].startswith('image/'):continue
        entry={'sha256':asset_id,'mime':asset['mime'],'size':asset['size'],'width':asset.get('width'),'height':asset.get('height')}
        entry['label']=labels.get(asset_id,'Custom image')
        url=sources.get(asset_id)
        try:
            if url:validate_remote_url(url)
        except ValidationError:url=None
        source=deck.get('imageSources',{}).get(asset_id) or processed_sources.get(asset_id) or bundled.get(asset_id) or recipes.get(asset_id)
        if source and 'url' in source:source={**source,'url':permanent_url(workspace,source['url'])}
        if source:entry.update(source)
        elif url:entry.update(url=permanent_url(workspace,url),transform='raw')
        else:missing.append(asset_id)
        value['images'][asset_id]=entry
    if missing:
        if allow_missing:return {'document':value,'missing':missing,'revision':workspace.store.get('decks',ident)['revision']}
        raise ValidationError(str(len(missing))+' image(s) need permanent URLs before exporting complete data.json.')
    validate(value)
    if len(json.dumps(value,ensure_ascii=False).encode())>MAX_DOCUMENT_BYTES:raise ValidationError('The deck recipe exceeds 20 MB.')
    if allow_missing:return {'document':value,'missing':[],'revision':workspace.store.get('decks',ident)['revision']}
    return value


def import_document(workspace,value,progress=lambda *a:None,cancel=lambda:False):
    steps=import_document_steps(workspace,value,progress,cancel)
    while True:
        try:next(steps)
        except StopIteration as finished:return finished.value


def import_document_steps(workspace,value,progress=lambda *a:None,cancel=lambda:False):
    validate(value)
    #Validate and stage every dependency before publishing a new deck. Originals
    #are never replaced, including when importing a file from this workspace.
    resolving=set()
    def resolve(ident):
        if workspace.store.asset(ident):
            if hashlib.sha256(workspace.store.asset_path(ident).read_bytes()).hexdigest()!=ident:
                raise ValidationError('A cached source image failed its SHA-256 check.')
            return
        if ident in resolving:raise ValidationError('Circular image build recipe.')
        entry=value['images'].get(ident)
        if not entry:raise ValidationError('A required image source is missing from data.json.')
        resolving.add(ident)
        if 'recipe' in entry:
            icon=entry['recipe']['icon'];resolve(icon)
            actual=workspace.backs.icon(icon)['id']
        else:
            raw,mime,_=workspace.net.fetch(entry['url'],immutable=True)
            transform=entry.get('transform','raw')
            if transform=='raw':
                if hashlib.sha256(raw).hexdigest()!=ident:raise ValidationError('An image source changed or failed its SHA-256 check. The deck was not imported.')
                if entry['mime']=='image/svg+xml':
                    sanitize_svg(raw);actual=workspace.store.add_asset(raw,entry['mime'],entry.get('width'),entry.get('height'))['id']
                else:
                    image=decode_image(raw);actual=workspace.store.add_asset(raw,entry['mime'],image.width,image.height)['id']
            else:actual=ingest_image(workspace.store,raw,trim_transparent_padding=transform=='trim-transparent')['id']
        if actual!=ident:raise ValidationError('An image build recipe produced different pixels. The deck was not imported.')
        resolving.remove(ident)
    for index,ident in enumerate(value['images']):
        if cancel():raise ValidationError('Complete deck import cancelled.')
        resolve(ident)
        progress(index+1,len(value['images']),'Restoring source image '+str(index+1))
        yield
    if cancel():raise ValidationError('Complete deck import cancelled.')
    deck=map_images(copy.deepcopy(value['deck']),restore=True,vectors=value.get('vectors',{}))
    for field in ('summary','tokens','printStatus','upgradeRequired','revision','createdAt','updatedAt','deleted','githubCardDataState','pendingImport'):
        deck.pop(field,None)
    recipe_id=deck.get('recipeId',deck['id'])
    mapping={deck.get('id'):uid()}
    for card in deck['cards']:
        for item in [card,*stored_faces(card)]:mapping[item['id']]=uid()
    for template in value.get('templates',[]):mapping[template['id']]=uid()
    def remap(item):
        if isinstance(item,dict):return {mapping.get(key,key):remap(v) for key,v in item.items()}
        if isinstance(item,list):return [remap(v) for v in item]
        if isinstance(item,str):
            if item in mapping:return mapping[item]
            for original,replacement in mapping.items():
                if original and item.startswith(original+'/'):return replacement+item[len(original):]
            return item
        return item
    deck=remap(deck)
    deck['recipeId']=recipe_id
    templates=remap(map_images(copy.deepcopy(value.get('templates',[])),restore=True,vectors=value.get('vectors',{})))
    deck['imageSources']={ident:{key:entry[key] for key in ('url','transform','recipe') if key in entry} for ident,entry in value['images'].items()}
    #Validate settings against staged templates without persisting partial decks.
    rules=deck['settings'].get('templateRules',{})
    known={template['id'] for template in templates}
    from .compiler import BUILTINS
    available={template['id'] for template in BUILTINS}|known
    if any(choice not in available for choice in rules.values()):raise ValidationError('A selected custom template is missing from data.json.')
    from .token_assignments import validate_assignments,validate_treatments
    validate_assignments(deck['settings'].get('tokenAssignments',[]))
    validate_treatments(deck['settings'].get('tokenTreatments',[]))
    for template in templates:workspace.store.put('templates',template)
    try:deck['settings']=workspace.validate_settings(deck['settings'])
    except BaseException:
        for template in templates:workspace.store.purge('templates',template['id'])
        raise
    deck['status']='prepared' if all(face.get('compiled') for card in deck['cards'] for face in card['faces']) else 'draft'
    #The document contains inputs only. Generated images are rebuilt normally.
    from .domain import stable_hash
    for card in deck['cards']:
        render_keys={}
        for face in stored_faces(card):
            compiled=face.get('compiled') or {}
            compiled.pop('render',None)
            if compiled.get('renderKey'):
                previous=compiled['renderKey'];key=stable_hash({'content':compiled.get('contentRenderKey',previous),'deck':deck['id'],'face':face['id']})
                render_keys[previous]=key;compiled['renderKey']=key
                if face.get('acceptedWarningKey')==previous:face['acceptedWarningKey']=key
        if card.get('substitute') and card['substitute'].get('sourceRenderKey') in render_keys:
            card['substitute']['sourceRenderKey']=render_keys[card['substitute']['sourceRenderKey']]
    #The top-level overlays stay editable by older artwork tools. Apply them to
    #the snapshot too, so later rules/approval updates do not restore stale data.
    workspace._apply_card_data(deck,value.get('cards',[]),allow_missing=True)
    #The complete snapshot owns deck settings. Compatibility overlays may also
    #contain artist/token rows for other decks that share the project file.
    deck['recipeSnapshot']={'renderer':value.get('renderer',{}),'fingerprint':recipe_fingerprint(deck)}
    saved=workspace.store.put('decks',deck)
    return workspace.deck(saved['id'])
