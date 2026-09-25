from pathlib import Path
from foundry.workspace import DEFAULT_SETTINGS, FRONT_SETTINGS

def test_hosted_land_library_feature_is_removed():
    assert 'useLandLibrary' not in DEFAULT_SETTINGS
    assert 'useLandLibrary' not in FRONT_SETTINGS
    setup=Path('site/setup.js').read_text(encoding='utf-8')
    workspace=Path('foundry/workspace.py').read_text(encoding='utf-8')
    assert 'use-land-library' not in setup
    assert 'full-art land library' not in setup.lower()
    assert 'HOSTED_LAND_LIBRARY' not in workspace
    assert not Path('full_art_lands').exists()
