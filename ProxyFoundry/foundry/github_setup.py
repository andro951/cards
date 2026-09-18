"""Import a public GitHub setup bundle without modifying any saved deck.

Artwork remains a live GitHub source. Symbols/backs are validated, downloaded
and staged as workspace assets; the UI applies the complete result to its draft
only after success. Failed or cancelled imports cannot half-update a deck.
"""
from __future__ import annotations

from pathlib import PurePosixPath
from urllib.parse import quote

from .domain import RARITIES, ValidationError, github_location
from .images import ingest_image, rarity_variants

RASTER_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
IMAGE_EXTENSIONS = RASTER_EXTENSIONS | {'.svg'}


def import_github_setup(workspace, payload, progress=lambda *a: None, cancel=lambda: False):
    """Return a complete source/symbol/back settings patch, never a saved deck.

    Canonical set_symbols/ wins over the legacy set_symbol/ alias and the
    single set_symbol image. With no symbol files, the bundled defaults are used.
    A present but invalid symbol folder is still an error, not permission to
    silently fall back. back wins over icon.
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
    art_folder = named_folder(rows, 'art')
    # Do not fetch every art image here; the normal generation path stays live.
    symbol_folder = named_folder(rows, 'set_symbols')
    if symbol_folder is None:
        symbol_folder = named_folder(rows, 'set_symbol')
    symbol_rows = {}
    single = None
    if symbol_folder is not None:
        progress(0, 0, 'Checking the four rarity symbols')
        contents = folder_rows(symbol_folder)
        unexpected = [r['name'] for items in contents.values() for r in items
                      if PurePosixPath(r['name'].lower()).suffix in IMAGE_EXTENSIONS
                      and PurePosixPath(r['name'].lower()).stem not in RARITIES]
        if unexpected:
            raise ValidationError('The set-symbol folder must contain only common.*, uncommon.*, rare.*, and mythic.* image files. Unexpected: ' + ', '.join(unexpected))
        symbol_rows = {r: named_image(contents, r) for r in RARITIES}
        missing = [r + '.png' for r, row in symbol_rows.items() if row is None]
        if missing:
            raise ValidationError('The set-symbol folder is missing: ' + ', '.join(missing) + '. All four rarity symbols are required.')
    else:
        single = named_image(rows, 'set_symbol')
        if single is not None:
            warnings.append('Generated four color-shifted symbols from set_symbol.png. This is not recommended; separate rarity images give better control. Review all four previews below.')

    back = named_image(rows, 'back')
    icon = None if back else named_image(rows, 'back_icon')
    if back and any(PurePosixPath(name).stem == 'back_icon' and PurePosixPath(name).suffix in IMAGE_EXTENSIONS for name in rows):
        warnings.append('Both back.png and back_icon.png are present. The complete back.png takes priority; the icon was not used.')
    total = (4 if symbol_rows else 1 if single else 0) + bool(back or icon)
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

    if symbol_rows:
        symbols = {r: download(row, trim_transparent_padding=True)['id'] for r, row in symbol_rows.items()}
        symbol_summary = 'folder'
    elif single:
        symbols = rarity_variants(store, download(single, trim_transparent_padding=True)['id'])
        symbol_summary = 'generated'
    else:
        symbols = workspace.symbols.defaults()
        symbol_summary = 'default'
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
              'ref': loc['ref'] if art_folder else '', 'fallback': True, 'localFiles': {}}
    progress(done, total, 'GitHub setup ready to review')
    return {'settings': {'source': source, 'symbols': symbols, **back_settings,
                         'githubSetupFolder': root_url},
            'summary': {'art': 'github' if art_folder else 'scryfall',
                        'symbols': symbol_summary,
                        'back': back_settings['backDesign']['mode']},
            'warnings': warnings}
