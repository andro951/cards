"""Import a public GitHub setup bundle without modifying any saved deck.

Artwork remains a live GitHub source. Symbols/backs are validated, downloaded
and staged as workspace assets; the UI applies the complete result to its draft
only after success. Failed or cancelled imports cannot half-update a deck.
"""
from __future__ import annotations

import json
from pathlib import PurePosixPath
from urllib.parse import quote

from .domain import RARITIES, ValidationError, github_location
from .images import ingest_image

RASTER_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
IMAGE_EXTENSIONS = RASTER_EXTENSIONS | {'.svg'}
DATA_JSON_MAX_BYTES = 2 * 1024 * 1024
DATA_JSON_MAX_CARDS = 10000


def parse_card_data_json(raw):
    """Validate the optional v1 nickname/flavor metadata file."""
    if not isinstance(raw, (bytes, bytearray)) or len(raw) > DATA_JSON_MAX_BYTES:
        raise ValidationError('data.json must be a UTF-8 JSON file no larger than 2 MB.')
    try:
        value = json.loads(bytes(raw).decode('utf-8-sig'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError('data.json is not valid UTF-8 JSON.') from exc
    if not isinstance(value, dict):
        raise ValidationError('data.json must contain a JSON object.')
    unknown_root = set(value) - {'version', 'cards'}
    if unknown_root:
        raise ValidationError('data.json has unsupported top-level field(s): ' + ', '.join(sorted(unknown_root)) + '.')
    if value.get('version') != 1:
        raise ValidationError('data.json version must be 1.')
    cards = value.get('cards')
    if not isinstance(cards, list):
        raise ValidationError('data.json cards must be an array.')
    if len(cards) > DATA_JSON_MAX_CARDS:
        raise ValidationError('data.json may contain at most 10,000 card entries.')

    def clean(item, key, label, maximum, *, multiline=False, required=False):
        raw_value = item.get(key, '')
        if raw_value is None:
            raw_value = ''
        if not isinstance(raw_value, str):
            raise ValidationError(label + ' must be text.')
        text = raw_value.strip()
        if required and not text:
            raise ValidationError(label + ' is required.')
        if len(text) > maximum:
            raise ValidationError(label + ' is too long.')
        allowed = {'\n', '\t'} if multiline else set()
        if any((ord(ch) < 32 and ch not in allowed) or ord(ch) == 127 for ch in text):
            raise ValidationError(label + ' contains unsupported control characters.')
        return text

    result = []
    seen = set()
    allowed_keys = {'name', 'nickname', 'flavor_text', 'artist'}
    for index, item in enumerate(cards, 1):
        if not isinstance(item, dict):
            raise ValidationError(f'data.json card entry {index} must be an object.')
        unknown = set(item) - allowed_keys
        if unknown:
            raise ValidationError(
                f'data.json card entry {index} has unsupported field(s): ' + ', '.join(sorted(unknown)) + '.'
            )
        name = clean(item, 'name', f'data.json card entry {index} name', 300, required=True)
        nickname = clean(item, 'nickname', f'data.json nickname for {name}', 300)
        flavor = clean(item, 'flavor_text', f'data.json flavor_text for {name}', 20000, multiline=True)
        artist = clean(item, 'artist', f'data.json artist for {name}', 300)
        if not nickname and not flavor and not artist:
            continue
        if name in seen:
            raise ValidationError('data.json contains more than one nonempty entry for ' + name + '.')
        seen.add(name)
        entry = {'name': name}
        if nickname:
            entry['nickname'] = nickname
        if flavor:
            entry['flavor_text'] = flavor
        if artist:
            entry['artist'] = artist
        result.append(entry)
    return result


def validate_card_data_for_deck(workspace, deck_id, entries):
    deck = workspace.deck(str(deck_id))
    names = {str(face.get('name') or '') for card in deck.get('cards', []) for face in card.get('faces', [])}
    missing = [entry['name'] for entry in entries if entry['name'] not in names]
    if missing:
        preview = ', '.join(missing[:8]) + ('…' if len(missing) > 8 else '')
        raise ValidationError('data.json card name(s) were not found in this deck: ' + preview + '. Names must exactly match a card face.')
    return entries


def import_card_data_url(workspace, payload):
    url = str(payload.get('url') or '').strip()
    if len(url) > 4096:
        raise ValidationError('The GitHub data.json link is too long.')
    if not url.startswith(('https://github.com/', 'https://www.github.com/', 'https://raw.githubusercontent.com/')):
        raise ValidationError('Use a public GitHub data.json file link.')
    loc = github_location(url)
    if not loc['folder'].lower().endswith('/data.json') and loc['folder'].lower() != 'data.json':
        raise ValidationError('Choose a GitHub file named data.json.')
    raw_url = 'https://raw.githubusercontent.com/' + loc['repo'] + '/' + quote(loc['ref'], safe='') + '/' + quote(loc['folder'], safe='/')
    raw, _, _ = workspace.net.fetch(raw_url, refresh=True, ttl=0)
    entries = parse_card_data_json(raw)
    return validate_card_data_for_deck(workspace, payload['deckId'], entries)


def import_symbol_folder(workspace, payload, progress=lambda *a: None, cancel=lambda: False):
    """Import four rarity images from a public GitHub folder."""
    url=payload.get('url')
    if not isinstance(url,str) or not url.strip() or len(url)>4096:
        raise ValidationError('Paste a public GitHub set-symbol folder link.')
    loc=github_location(url)
    if loc['default_ref']:
        repo=workspace.net.json('https://api.github.com/repos/'+loc['repo'],ttl=0)
        if not isinstance(repo,dict) or not isinstance(repo.get('default_branch'),str):
            raise ValidationError('GitHub did not return the repository default branch.')
        loc=github_location(url,repo['default_branch'])
    if not loc['folder']:
        raise ValidationError('Choose the folder containing four rarity images.')
    ref=quote(loc['ref'],safe='')
    api='https://api.github.com/repos/'+loc['repo']+'/contents/'+quote(loc['folder'],safe='/')+'?ref='+ref
    rows=workspace.net.json(api,ttl=0)
    if not isinstance(rows,list) or len(rows)>=1000:
        raise ValidationError('That GitHub link must be a small image folder.')
    found={}
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('name'),str):
            raise ValidationError('GitHub returned an invalid file listing.')
        name=row['name'];path=loc['folder'].rstrip('/')+'/'+name
        if not name or '/' in name or '\\' in name or row.get('path')!=path:
            raise ValidationError('GitHub returned an unexpected file path.')
        suffix=PurePosixPath(name.lower()).suffix
        if suffix not in IMAGE_EXTENSIONS:continue
        stem=PurePosixPath(name.lower()).stem
        if stem not in RARITIES or stem in found:
            raise ValidationError('Use exactly one image each named common, uncommon, rare, and mythic.')
        if suffix not in RASTER_EXTENSIONS or row.get('type')!='file' or row.get('submodule_git_url') or row.get('target'):
            raise ValidationError(name+': use a regular PNG, JPG, or WebP image.')
        found[stem]=row
    missing=[rarity for rarity in RARITIES if rarity not in found]
    if missing:raise ValidationError('The set-symbol folder is missing: '+', '.join(missing)+'.')
    result={}
    for index,rarity in enumerate(RARITIES):
        if cancel():raise ValidationError('Set-symbol import cancelled.')
        progress(index,4,'Importing '+rarity+' symbol')
        path=found[rarity]['path']
        raw_url='https://raw.githubusercontent.com/'+loc['repo']+'/'+ref+'/'+quote(path,safe='/')
        raw,_,_=workspace.net.fetch(raw_url,refresh=True,ttl=0)
        result[rarity]=ingest_image(workspace.store,raw,trim_transparent_padding=True)['id']
    progress(4,4,'Four rarity symbols imported')
    return {'symbols':result}


def import_github_setup(workspace, payload, progress=lambda *a: None, cancel=lambda: False):
    """Return a complete source/symbol/back settings patch, never a saved deck.

    Canonical set_symbols/ wins over the legacy set_symbol/ alias and the
    single set_symbol image. A present but invalid symbol folder is an error,
    not permission to silently recolor the single image. back wins over icon.
    """
    net, store = workspace.net, workspace.store
    url = payload.get('url')
    if not isinstance(url, str) or not url.strip():
        raise ValidationError('Paste the GitHub project folder link first.')
    if len(url) > 4096:
        raise ValidationError('The GitHub folder link is too long.')
    loc = github_location(url)
    warnings = []

    def check_cancel():
        if cancel():
            raise ValidationError('GitHub setup import cancelled. Your setup was not changed.')

    check_cancel()
    progress(0, 0, 'Reading GitHub project folder')
    if loc['default_ref']:
        repo = net.json('https://api.github.com/repos/' + loc['repo'], ttl=0)
        if not isinstance(repo, dict) or not isinstance(repo.get('default_branch'), str):
            raise ValidationError('GitHub did not return the repository default branch.')
        loc = github_location(url, repo['default_branch'])
    ref = quote(loc['ref'], safe='')
    base = 'https://github.com/' + loc['repo'] + '/tree/' + ref
    root_url = base + ('/' + quote(loc['folder'], safe='/') if loc['folder'] else '')

    def folder_rows(folder):
        check_cancel()
        api = 'https://api.github.com/repos/' + loc['repo'] + '/contents/'
        rows = net.json(api + quote(folder, safe='/') + '?ref=' + ref, ttl=0)
        if not isinstance(rows, list):
            raise ValidationError('That GitHub link is a file, not a project folder.')
        # The Contents API's directory limit must never look like a complete bundle.
        if len(rows) >= 1000:
            raise ValidationError('This setup folder has too many entries to inspect safely. Use a smaller project folder.')
        names = {}
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('name'), str):
                raise ValidationError('GitHub returned an invalid folder listing.')
            name = row['name']
            path = folder.rstrip('/') + '/' + name if folder else name
            if not name or name in {'.', '..'} or any(c in name for c in '/\\\x00') or row.get('path') != path:
                raise ValidationError('GitHub returned an unsafe or unexpected file path.')
            # Build download URLs ourselves; never follow untrusted download_url fields.
            names.setdefault(name.lower(), []).append(row)
        return names

    def named_folder(rows, name):
        matches = rows.get(name, [])
        if len(matches) > 1:
            raise ValidationError('Duplicate ' + name + ' folders. Keep only one.')
        if not matches:
            return None
        row = matches[0]
        if row.get('type') != 'dir':
            raise ValidationError(name + ' must be a regular GitHub folder, not a file or symlink.')
        return row['path']

    def named_file(rows, name):
        matches = rows.get(name.lower(), [])
        if len(matches) > 1:
            raise ValidationError('Duplicate ' + name + ' files. Keep only one.')
        if not matches:
            return None
        row = matches[0]
        if row.get('type') != 'file' or row.get('submodule_git_url') or row.get('target'):
            raise ValidationError(name + ' must be a regular GitHub file, not a symlink or submodule.')
        return row

    def named_image(rows, stem):
        matches = [r for items in rows.values() for r in items
                   if PurePosixPath(r['name'].lower()).stem == stem
                   and PurePosixPath(r['name'].lower()).suffix in IMAGE_EXTENSIONS]
        if len(matches) > 1:
            raise ValidationError('Duplicate ' + stem + ' images. Keep exactly one ' + stem + '.png.')
        if not matches:
            return None
        row = matches[0]
        if row.get('type') != 'file' or row.get('submodule_git_url') or row.get('target'):
            raise ValidationError(row['name'] + ' must be a regular image file, not a symlink or submodule.')
        if PurePosixPath(row['name'].lower()).suffix not in RASTER_EXTENSIONS:
            raise ValidationError(row['name'] + ': export SVG to PNG for GitHub setup import, or upload it individually below.')
        return row

    rows = folder_rows(loc['folder'])
    if PurePosixPath(loc['folder']).name.lower()=='art' and not named_folder(rows,'art'):
        parent=str(PurePosixPath(loc['folder']).parent)
        if parent=='.':parent=''
        parent_rows=folder_rows(parent)
        if named_folder(parent_rows,'art')==loc['folder']:
            loc={**loc,'folder':parent}
            rows=parent_rows
            root_url=base+('/'+quote(parent,safe='/') if parent else '')
            warnings.append('The link points to the art folder. Imported setup from its parent project folder: '+root_url)
    data_row = named_file(rows, 'data.json')
    art_folder = named_folder(rows, 'art')
    # Do not fetch every art image here; the normal generation path stays live.
    symbol_folder = None
    symbol_rows = {}
    # A completely empty symbol folder is equivalent to no override at all.
    # If both folder spellings exist, the canonical plural folder is checked first.
    for candidate in (named_folder(rows, 'set_symbols'), named_folder(rows, 'set_symbol')):
        if candidate is None:
            continue
        progress(0, 0, 'Checking the four rarity symbols')
        contents = folder_rows(candidate)
        image_rows = [r for items in contents.values() for r in items
                      if PurePosixPath(r['name'].lower()).suffix in IMAGE_EXTENSIONS]
        if not image_rows:
            continue
        unexpected = [r['name'] for r in image_rows
                      if PurePosixPath(r['name'].lower()).stem not in RARITIES]
        if unexpected:
            raise ValidationError('The set-symbol folder must contain only common.*, uncommon.*, rare.*, and mythic.* image files. Unexpected: ' + ', '.join(unexpected))
        candidate_rows = {r: named_image(contents, r) for r in RARITIES}
        missing = [r + '.png' for r, row in candidate_rows.items() if row is None]
        if missing:
            raise ValidationError('The set-symbol folder is missing: ' + ', '.join(missing) + '. Use all four rarity symbols, or leave the folder empty to use the bundled defaults.')
        symbol_folder = candidate
        symbol_rows = candidate_rows
        break

    if named_image(rows, 'set_symbol'):
        raise ValidationError('Use four rarity images in set_symbols/; one-image symbol generation is no longer supported.')
    symbol_mode = 'folder' if symbol_rows else 'default'

    back = named_image(rows, 'back')
    icon = None if back else named_image(rows, 'back_icon')
    if back and any(PurePosixPath(name).stem == 'back_icon' and PurePosixPath(name).suffix in IMAGE_EXTENSIONS for name in rows):
        warnings.append('Both back.png and back_icon.png are present. The complete back.png takes priority; the icon was not used.')
    total = (4 if symbol_rows else 0) + bool(back or icon) + bool(data_row)
    done = 0

    def download(row, *, trim_transparent_padding=False):
        nonlocal done
        check_cancel()
        progress(done, total, 'Importing ' + row['name'])
        raw_url = 'https://raw.githubusercontent.com/' + loc['repo'] + '/' + ref + '/' + quote(row['path'], safe='/')
        raw, _, _ = net.fetch(raw_url, refresh=True, ttl=0)
        check_cancel()
        try:
            image = ingest_image(store, raw, trim_transparent_padding=trim_transparent_padding)
        except ValidationError as exc:
            raise ValidationError(row['name'] + ': ' + str(exc)) from exc
        done += 1
        progress(done, total, 'Imported ' + row['name'])
        return image

    card_data = []
    if data_row:
        check_cancel()
        progress(done, total, 'Importing data.json')
        raw_url = 'https://raw.githubusercontent.com/' + loc['repo'] + '/' + ref + '/' + quote(data_row['path'], safe='/')
        raw, _, _ = net.fetch(raw_url, refresh=True, ttl=0)
        check_cancel()
        card_data = parse_card_data_json(raw)
        deck_id = payload.get('deckId')
        if deck_id and card_data:
            validate_card_data_for_deck(workspace, deck_id, card_data)
        done += 1
        progress(done, total, 'Imported data.json')

    if symbol_rows:
        symbols = {r: download(row, trim_transparent_padding=True)['id'] for r, row in symbol_rows.items()}
    else:
        symbols = workspace.default_symbols()
    if back:
        back_settings = {'backAsset': download(back, trim_transparent_padding=True)['id'], 'backDesign': {'mode': 'custom'}}
    elif icon:
        output = workspace.backs.icon(download(icon)['id'])
        warnings.extend(output['placement'].get('warnings', []))
        back_settings = {'backAsset': output['id'], 'backDesign': output['design']}
    else:
        back_settings = workspace.backs.settings({'backDesign': {'mode': 'default'}})
    check_cancel()
    source = {'mode': 'github' if art_folder else 'scryfall',
              'githubFolder': base + '/' + quote(art_folder, safe='/') if art_folder else '',
              'ref': loc['ref'] if art_folder else '', 'fallback': False, 'localFiles': {}}
    progress(done, total, 'GitHub setup ready to review')
    summary = {'art': 'github' if art_folder else 'scryfall',
               'symbols': symbol_mode,
               'back': back_settings['backDesign']['mode']}
    if data_row:
        summary['data'] = len(card_data)
    return {'settings': {'source': source, 'symbols': symbols, **back_settings,
                         'githubSetupFolder': root_url,
                         'dataJsonSource': {'kind':'github','value':data_row['path']} if data_row else None},
            'cardData': card_data,
            'summary': summary,
            'warnings': warnings}
