"""One source of truth for the routine and extended pytest groups."""

EXTENDED_MODULES={
    'test_art_series_native.py',
    'test_batch_bridge.py',
    'test_browser.py',
    'test_browser_storage.py',
    'test_dom_offline.py',
    'test_downloads_browser.py',
    'test_emblem_native.py',
    'test_helper_native.py',
    'test_extension.py',
    'test_github_setup_browser.py',
    'test_godzilla_browser.py',
    'test_modal_focus.py',
    'test_native_deck.py',
    'test_order_dialog.py',
    'test_print_bridge.py',
    'test_prepare_native.py',
    'test_station_native.py',
    'test_station_lands_native.py',
    'test_token_native.py',
    'test_website.py',
}
EXTENDED_TESTS={
    'tests/test_github_setup.py::test_live_existing_eggs_fall_folder',
    'tests/test_runtime.py::test_colorless_saga_creature_gap_asset_exists_at_pinned_commit',
    'tests/test_station_source_probe.py::test_station_source_probe',
    'tests/test_transfer_batches.py::test_real_278_card_multi_gigabyte_archive',
}


def group_for_nodeid(nodeid):
    module=nodeid.split('::',1)[0].replace('\\','/').rsplit('/',1)[-1]
    normalized=nodeid.replace('\\','/')
    return 'extended' if module in EXTENDED_MODULES or normalized in EXTENDED_TESTS else 'routine'
