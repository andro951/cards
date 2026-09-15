"""Artist provenance and optional modification text, independent of template geometry."""
from __future__ import annotations
from .domain import ValidationError

SCRYFALL_ART = 'Scryfall selected printing'
CREDIT_SEPARATOR = ' · '


def credit_text(value, label='Artist credit', *, maximum=300):
    """Credits are plain one-line text, not CardConjurer formatting commands."""
    if value is None:
        return ''
    if not isinstance(value, str):
        raise ValidationError(label + ' must be text.')
    text = value.strip()
    if len(text) > maximum:
        raise ValidationError(f'{label} must be at most {maximum} characters.')
    if any(ord(c) < 32 or ord(c) == 127 for c in text) or '{' in text or '}' in text:
        raise ValidationError(label + ' must be a single line without CardConjurer {commands}.')
    return text


def printing_artist(card, face):
    """Scryfall face credit takes precedence over its physical card's credit."""
    for source in (face, card):
        value = source.get('artist') if isinstance(source, dict) else None
        if isinstance(value, str) and value.strip():
            return credit_text(value)
    return ''


def resolve_credit(card, face, options, settings, art_origin):
    """Never attribute actual Scryfall artwork to the custom-art default/override.

    artistOverride: None inherits; '' deliberately blanks *custom* art credit.
    artistCreditMode: 'printing' explicitly retains the original credit on modified
    uploaded art; 'inherit' uses the per-face override or deck custom-art default.
    modificationCreditOverride: None inherits the deck suffix; '' suppresses it.
    """
    original = printing_artist(card, face)
    mode = options.get('artistCreditMode') or 'inherit'
    if mode not in {'inherit', 'printing'}:
        raise ValidationError('Choose the printing artist or your custom-art credit.')
    source_is_scryfall = art_origin == SCRYFALL_ART
    if source_is_scryfall or mode == 'printing':
        artist, source = original, 'scryfall' if source_is_scryfall else 'printing'
    elif options.get('artistOverride') is not None:
        artist, source = credit_text(options['artistOverride']), 'card'
    elif credit_text(settings.get('artist')):
        artist, source = credit_text(settings['artist']), 'deck'
    else:
        artist, source = original, 'printing'
    modification = options.get('modificationCreditOverride')
    if modification is None:
        modification = settings.get('modificationCredit', '')
    modification = credit_text(modification, 'Modification credit', maximum=160)
    display = CREDIT_SEPARATOR.join(x for x in (artist, modification) if x)
    if len(display) > 460:
        raise ValidationError('The combined artist credit is too long.')
    return {'originalArtist': original, 'artist': artist,
            'modificationCredit': modification, 'display': display,
            'source': source, 'locked': source_is_scryfall,
            'missingOriginalArtist': source in {'scryfall', 'printing'} and not original}
