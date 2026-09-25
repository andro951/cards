"""Artist provenance for card-footer credits, independent of template geometry."""
from __future__ import annotations
from .domain import ValidationError

SCRYFALL_ART = 'Scryfall selected printing'
SCRYFALL_RIGHTS_SUFFIX = ' (Scryfall) • Art © respective rights holders'

def credit_text(value, label='Artist credit', *, maximum=300):
    if value is None:return ''
    if not isinstance(value,str):raise ValidationError(label+' must be text.')
    text=value.strip()
    if len(text)>maximum:raise ValidationError(f'{label} must be at most {maximum} characters.')
    if any(ord(c)<32 or ord(c)==127 for c in text) or '{' in text or '}' in text:
        raise ValidationError(label+' must be a single line without CardConjurer {commands}.')
    return text

def printing_artist(card,face):
    for source in (face,card):
        value=source.get('artist') if isinstance(source,dict) else None
        if isinstance(value,str) and value.strip():return credit_text(value)
    return ''

def resolve_credit(card,face,options,settings,art_origin):
    original=printing_artist(card,face)
    mode=options.get('artistCreditMode') or 'inherit'
    if mode not in {'inherit','printing'}:raise ValidationError('Choose the printing artist or your custom-art credit.')
    source_is_scryfall=art_origin==SCRYFALL_ART
    if source_is_scryfall or mode=='printing':
        artist,source=original,'scryfall' if source_is_scryfall else 'printing'
    elif options.get('artistOverride') is not None:
        artist,source=credit_text(options['artistOverride']),'card'
    elif credit_text(settings.get('artist')):
        artist,source=credit_text(settings['artist']),'deck'
    else:
        artist,source='','missing-custom'
    if source_is_scryfall:
        display=artist+SCRYFALL_RIGHTS_SUFFIX if artist else 'Scryfall • Art © respective rights holders'
    else:
        display=artist
    if len(display)>460:raise ValidationError('The artist credit is too long.')
    return {'originalArtist':original,'artist':artist,'display':display,'source':source,
            'locked':source_is_scryfall,
            'missingOriginalArtist':source in {'scryfall','printing'} and not original,
            'missingCustomArtist':source=='missing-custom'}
