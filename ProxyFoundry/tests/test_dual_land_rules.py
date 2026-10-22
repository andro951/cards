import io
from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import Image

from foundry import dual_land_rules
from foundry.compiler import Compiler
from foundry.network import Network
from foundry.runtime import Runtime
from foundry.storage import Store


def fixture_png():
    source = Image.new('RGBA', (4, 1))
    source.putdata([(255, 255, 255, 255), (220, 220, 220, 128),
                    (0, 0, 0, 255), (255, 255, 255, 0)])
    output = io.BytesIO()
    source.save(output, 'PNG')
    return output.getvalue()


@pytest.mark.parametrize('code', list('WUBRG'))
def test_white_texture_highlights_receive_visible_color_without_changing_alpha(code):
    raw = fixture_png()
    original = Image.open(io.BytesIO(raw)).convert('RGBA')
    result = Image.open(io.BytesIO(dual_land_rules.colored_rules_png(raw, code))).convert('RGBA')
    assert result.size == original.size
    assert result.getchannel('A').tobytes() == original.getchannel('A').tobytes()
    assert result.getpixel((0, 0)) == (*dual_land_rules.TINTS[code], 255)
    assert result.getpixel((2, 0)) == (0, 0, 0, 255)
    assert all(result.getpixel((1, 0))[c] < result.getpixel((0, 0))[c] for c in range(3))
    assert min(result.getpixel((1, 0))[:3]) >= 110
    assert max(result.getpixel((0, 0))[:3]) - min(result.getpixel((0, 0))[:3]) >= 12


def test_concurrent_runtime_requests_generate_once_and_persist_for_next_run(tmp_path):
    calls = []
    def transport(url):
        calls.append(url)
        assert url.endswith('/img/frames/m15/regular/m15FrameU.png')
        return fixture_png(), 'image/png', {}
    store = Store(tmp_path)
    runtime = Runtime(Network(store, transport=transport))
    path = dual_land_rules.PREFIX + 'm15FrameU.png'
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: runtime.fetch(path), range(8)))
    assert len(calls) == 1
    assert all(result == results[0] for result in results)
    assert runtime.fetch('/img/frames/m15/regular/m15FrameU.png')[0] == fixture_png()
    def fail(*args, **kwargs):
        raise AssertionError('Cached rules material must not load or recolor its source again')
    restarted = Runtime(Network(store, transport=fail))
    assert restarted.cached(path)
    restarted.ensure(path)
    assert restarted.fetch(path) == results[0]
    assert restarted.requested[path]['cache']


def test_material_refresh_is_limited_to_classic_two_color_lands():
    compiler = Compiler(None)
    face = {'types': ['Land'], 'land_colors': ['U', 'R']}
    assert compiler.template_identity('land', 'normal', face)[1] == compiler.template_identity('land', 'normal')[1] + 3
    for choice in ('auto', 'godzilla-land'):
        assert compiler.template_identity('land', choice, face) == compiler.template_identity('land', choice)
    for colors in ([], ['U'], ['W', 'U', 'R']):
        assert compiler.template_identity('land', 'normal', {**face, 'land_colors': colors}) == compiler.template_identity('land', 'normal')
    assert compiler.template_identity('standard', 'normal', {'types': ['Creature'], 'colors': ['U', 'R']}) == compiler.template_identity('standard', 'normal')
