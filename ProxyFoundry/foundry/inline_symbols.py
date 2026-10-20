"""Translate Scryfall tokens to existing native renderer symbol names."""


def text_fields(data):
    for section in ('text','bottomInfo'):
        for field in (data.get(section) or {}).values():
            if isinstance(field,dict) and isinstance(field.get('text'),str):yield field


def has_untap_alias(data):
    return any('{Q}' in field['text'] or '{q}' in field['text'] for field in text_fields(data))


def normalize_untap_aliases(data):
    for field in text_fields(data):
        text=field['text']
        if '{Q}' in text or '{q}' in text:
            field['text']=text.replace('{Q}','{untap}').replace('{q}','{untap}')
