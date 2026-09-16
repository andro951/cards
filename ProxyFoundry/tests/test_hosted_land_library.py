from pathlib import Path

from foundry.workspace import DEFAULT_SETTINGS, FRONT_SETTINGS, HOSTED_LAND_LIBRARY


def test_land_library_is_app_hosted_and_not_user_configurable():
    assert HOSTED_LAND_LIBRARY == "https://github.com/andro951/cards/tree/main/ProxyFoundry/full_art_lands"
    assert "landLibrary" not in DEFAULT_SETTINGS
    assert "landLibrary" not in FRONT_SETTINGS
    assert Path("full_art_lands").is_dir()
    assert any(p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"} for p in Path("full_art_lands").iterdir())


def test_land_library_ui_is_one_checkbox_only():
    setup=Path("site/setup.js").read_text(encoding="utf-8")
    settings=Path("site/settings.js").read_text(encoding="utf-8")
    workspace=Path("foundry/workspace.py").read_text(encoding="utf-8")
    assert setup.count('id="use-land-library"') == 1
    assert 'id="land-library"' not in setup
    assert "GitHub land-art folder" not in setup
    assert "Optional custom full-art land library" not in setup
    assert "global-land-library" not in settings
    assert "s.get('landLibrary')" not in workspace
    assert "self.global_settings().get('landLibrary')" not in workspace
