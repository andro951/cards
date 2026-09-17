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
    credit=resolve_credit(SF,FACE,{'artistOverride':override},{'artist':'Deck Artist','modificationCredit':'Modified by ChatGPT'},SCRYFALL_ART)
    assert credit['display']=='Face Artist · Modified by ChatGPT'
    assert credit['locked'] is True

def test_missing_scryfall_artist_does_not_use_custom_default():
    credit=resolve_credit({}, {}, {}, {'artist':'ChatGPT'},SCRYFALL_ART)
    assert credit['display']=='' and credit['missingOriginalArtist']

def test_custom_art_deck_then_card_override():
    assert resolve_credit(SF,FACE,{}, {'artist':'Deck Artist'},'uploaded override')['display']=='Deck Artist'
    assert resolve_credit(SF,FACE,{'artistOverride':'Card Artist'}, {'artist':'Deck Artist'},'uploaded override')['display']=='Card Artist'

def test_modified_upload_can_explicitly_keep_printing_artist():
    c=resolve_credit(SF,FACE,{'artistCreditMode':'printing'}, {'artist':'ChatGPT','modificationCredit':'Modified by ChatGPT'},'uploaded override')
    assert c['display']=='Face Artist · Modified by ChatGPT' and not c['locked']

def test_modification_override_and_suppression():
    settings={'artist':'Artist','modificationCredit':'Modified by ChatGPT'}
    assert resolve_credit(SF,FACE,{},settings,'custom')['display']=='Artist · Modified by ChatGPT'
    assert resolve_credit(SF,FACE,{'modificationCreditOverride':''},settings,'custom')['display']=='Artist'
    assert resolve_credit(SF,FACE,{'modificationCreditOverride':'Restored by Isaac'},settings,'custom')['display']=='Artist · Restored by Isaac'

def test_suffix_does_not_replace_or_mutate_cached_original():
    for _ in range(3):
        c=resolve_credit(SF,FACE,{}, {'modificationCredit':'Modified by ChatGPT'},SCRYFALL_ART)
        assert c['display'].count('Modified by ChatGPT')==1
    assert FACE['artist']=='Face Artist'

@pytest.mark.parametrize('text',['Wrong\nName','{elemidinfo-artist}','\x00','x'*301,42])
def test_plain_credit_validation(text):
    with pytest.raises(ValidationError):credit_text(text)


def test_custom_art_without_credit_never_assumes_printing_artist():
    c=resolve_credit(SF,FACE,{}, {},'uploaded override')
    assert c['artist']=='' and c['display']==''
    assert c['source']=='missing-custom' and c['missingCustomArtist']

def test_explicit_blank_custom_artist_is_intentional_not_missing():
    c=resolve_credit(SF,FACE,{'artistOverride':''}, {},'uploaded override')
    assert c['artist']=='' and c['source']=='card'
    assert not c['missingCustomArtist']
