"""Load the preserved compiler as a library. No monkeypatches or template edits."""
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'vendor/card_tools'
def load(name,relative):
    spec=importlib.util.spec_from_file_location(name,ROOT/relative)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
compiler=load('pf_v54_compiler','pipeline/card_data_to_cardconjurer.py')
ingest=load('pf_v54_ingest','pipeline/scryfall_to_card_data.py')
deck_parser=load('pf_v54_deck','pipeline/scryfall_deck_to_cardconjurer.py')
tokens=load('pf_v54_tokens','tools/make_copy_tokens.py')
image_tools=load('pf_v54_images','tools/download_scryfall_deck_images_zip.py')
