import io
from concurrent.futures import ThreadPoolExecutor

from PIL import Image
import pytest

from foundry.artifact_frame import ARTIFACT_GRAY_PREFIX, ArtifactFrameCache, gray_artifact_png
from foundry.compiler import Compiler
from foundry.images import ingest_image
from foundry.network import Network
from foundry.runtime import Runtime
from foundry.storage import Store
from foundry.workspace import Workspace


def sample_png():
    image = Image.new('RGBA', (5, 1))
    image.putdata([(247, 248, 245, 255), (120, 130, 140, 200), (0, 0, 0, 128),
                   (0, 0, 0, 255), (255, 255, 255, 0)])
    output = io.BytesIO()
    image.save(output, 'PNG')
    return output.getvalue()


def test_tint_preserves_black_fills_alpha_and_shading():
    original = Image.open(io.BytesIO(sample_png())).convert('RGBA')
    result = Image.open(io.BytesIO(gray_artifact_png(sample_png()))).convert('RGBA')
    assert result.size == original.size
    assert result.getchannel('A').tobytes() == original.getchannel('A').tobytes()
    assert result.getpixel((0, 0)) == (173, 173, 173, 255)
    assert result.getpixel((1, 0)) == (90, 90, 90, 200)
    assert result.getpixel((2, 0)) == original.getpixel((2, 0))
    assert result.getpixel((3, 0)) == original.getpixel((3, 0))


def test_concurrent_requests_generate_once_and_reuse_after_restart(tmp_path):
    store = Store(tmp_path)
    cache = ArtifactFrameCache(store)
    calls = []
    def load(path):
        calls.append(path)
        return sample_png(), 'image/png'
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: cache.fetch('/artifact.png', load), range(8)))
    assert calls == ['/artifact.png']
    assert sum(not cached for _, cached in results) == 1
    assert len({raw for raw, _ in results}) == 1
    def fail(path):
        raise AssertionError('A persisted tint must not load/process its source again')
    restarted = ArtifactFrameCache(Store(tmp_path))
    assert restarted.fetch('/artifact.png', fail) == (results[0][0], True)


def test_new_version_or_source_invalidates_cache(tmp_path, monkeypatch):
    import foundry.artifact_frame as module
    cache = ArtifactFrameCache(Store(tmp_path))
    load = lambda path: (sample_png(), 'image/png')
    assert not cache.fetch('/artifact.png', load)[1]
    assert cache.fetch('/artifact.png', load)[1]
    assert not cache.fetch('/crown.png', load)[1]
    monkeypatch.setattr(module, 'CC_COMMIT', 'new-pinned-source')
    assert not cache.fetch('/artifact.png', load)[1]
    monkeypatch.setattr(module, 'ARTIFACT_GRAY_VERSION', 'neutral-gray-v2')
    assert not cache.fetch('/artifact.png', load)[1]


@pytest.mark.parametrize('kind', ['Frame', 'TitleJoined', 'CrownJoined', 'TransformCrownJoined'])
def test_runtime_material_does_not_modify_native_white_or_artifact(tmp_path, kind):
    calls = []
    def transport(url):
        calls.append(url)
        return sample_png(), 'image/png', {}
    runtime = Runtime(Network(Store(tmp_path), transport=transport))
    native_kind = kind.removesuffix('Joined')
    source = ('/img/frames/m15/transform/crowns/nickname/a.png' if kind=='TransformCrownJoined'
              else f'/img/frames/m15/nickname/m15Nickname{native_kind}A.png')
    experiment = ARTIFACT_GRAY_PREFIX + kind + '.png'
    original, _ = runtime.fetch(source)
    changed, _ = runtime.fetch(experiment)
    assert changed == gray_artifact_png(original)
    assert runtime.fetch(source)[0] == original
    assert runtime.fetch('/img/frames/m15/nickname/m15NicknameFrameW.png')[0] == original
    assert runtime.fetch(experiment)[0] == changed
    assert runtime.requested[experiment]['cache']
    assert len(calls) == (3 if kind=='TransformCrownJoined' else 2)


@pytest.fixture
def compile_material(tmp_path):
    store = Store(tmp_path)
    workspace = Workspace(store)
    art = ingest_image(store, sample_png())['id']
    compiler = Compiler(store)
    def compile(type_line, colors, nickname=False, choice='godzilla-card'):
        source = {'name': 'Artifact material test', 'layout': 'normal',
                  'type_line': type_line, 'colors': colors, 'mana_cost': '{2}',
                  'oracle_text': 'Flying', 'rarity': 'rare', 'artist': 'Artist',
                  'power': '2', 'toughness': '3'}
        if nickname:
            source['flavor_name'] = 'Alternate title'
        return compiler.compile_face(source, source, 0, {'templateOverride': choice},
                                     workspace.validate_settings({}), art)
    return compile


@pytest.mark.parametrize('legendary', [False, True])
@pytest.mark.parametrize('nickname', [False, True])
def test_artifact_material_applies_to_body_and_each_header_state(compile_material, legendary, nickname):
    result = compile_material(('Legendary ' if legendary else '') + 'Artifact Creature — Golem', [], nickname)
    frames = result['data']['frames']
    kind = ('Crown' if legendary else 'Title') + ('Joined' if nickname else '')
    assert any(frame['src'] == ARTIFACT_GRAY_PREFIX + 'Frame.png' for frame in frames)
    assert any(frame['src'] == ARTIFACT_GRAY_PREFIX + kind + '.png' for frame in frames)
    assert not any('/godzilla/' in frame['src'] and frame['src'].endswith('A.png') for frame in frames)
    assert any(frame['src'].endswith('/m15PTA.png') for frame in frames)
    assert result['data']['text']['pt']['color'] == 'black'
    assert result['data']['text']['pt']['outlineWidth'] == 0


@pytest.mark.parametrize('type_line,colors,choice', [
    ('Creature — Human', ['W'], 'godzilla-card'),
    ('Creature — Eldrazi', [], 'godzilla-card'),
    ('Artifact Creature — Golem', ['U'], 'godzilla-card'),
    ('Artifact Creature — Golem', ['W', 'U'], 'godzilla-card'),
    ('Artifact Creature — Golem', [], 'normal'),
    ('Artifact Land', [], 'godzilla-land'),
])
def test_other_materials_and_classic_artifacts_keep_native_pieces(compile_material, type_line, colors, choice):
    result = compile_material(type_line, colors, True, choice)
    assert not any(frame['src'].startswith(ARTIFACT_GRAY_PREFIX) for frame in result['data']['frames'])
    if type_line == 'Creature — Eldrazi':
        assert any(frame['src'].endswith('/m15NicknameFrameA.png') for frame in result['data']['frames'])
