import pytest
from foundry.credits import credit_text, printing_artist, resolve_credit, SCRYFALL_ART
from foundry.domain import ValidationError

SF={'artist':'Physical Card Artist'}
FACE={'artist':'Face Artist'}

def test_face_artist_preferred():
    assert printing_artist(SF,FACE)=='Face Artist'
    assert printing_artist(SF,{'artist':'  '})=='Physical Card Artist'

@pytest.mark.parametrize('override',[None,'Wrong Artist',''])
def test_scryfall_original_cannot_be_overwritten_or_blanked(override):
    credit=resolve_credit(SF,FACE,{'artistOverride':override},{'artist':'Deck Artist'},SCRYFALL_ART)
    assert credit['display']=='Face Artist (Scryfall) • Art © respective rights holders'
    assert credit['locked'] is True

def test_missing_scryfall_artist_keeps_source_and_rights_notice():
    credit=resolve_credit({}, {}, {}, {'artist':'ChatGPT'},SCRYFALL_ART)
    assert credit['display']=='Scryfall • Art © respective rights holders'
    assert credit['missingOriginalArtist']

def test_custom_art_deck_then_card_override():
    assert resolve_credit(SF,FACE,{}, {'artist':'Deck Artist'},'uploaded override')['display']=='Deck Artist'
    assert resolve_credit(SF,FACE,{'artistOverride':'Card Artist'}, {'artist':'Deck Artist'},'uploaded override')['display']=='Card Artist'

def test_custom_art_can_explicitly_keep_printing_artist_without_scryfall_source_label():
    c=resolve_credit(SF,FACE,{'artistCreditMode':'printing'}, {'artist':'ChatGPT'},'uploaded override')
    assert c['display']=='Face Artist' and not c['locked']

@pytest.mark.parametrize('value',['{fontbelerenbsc} Artist','bad\nartist'])
def test_credit_rejects_formatting_commands_and_controls(value):
    with pytest.raises(ValidationError):credit_text(value)
