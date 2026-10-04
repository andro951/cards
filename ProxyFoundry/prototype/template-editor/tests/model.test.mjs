import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { Model } from '../model.js';

const seed = () => JSON.parse(fs.readFileSync(new URL('../default-template.json', import.meta.url)));

test('default template has fixed ratio and resolves every placement', () => {
    const model = Model.Validate(seed());
    assert.equal(Model.Width / Model.Height, 5 / 7);
    for (const part of model.parts) {
        const rect = Model.ResolvePart(model, part);
        assert.ok(rect.width > 0 && rect.height > 0);
    }
    assert.equal(model.assets.FrameImages_C, '/img/frames/m15/regular/eldrazi.png');
});

test('tiny wide pieces fill the default width without stretching height', () => {
    const fitted = Model.Contain(Model.Rect(0, 0, 20, 2), Model.Rect(100, 200, 188, 73.3));
    assert.equal(fitted.width, 188);
    assert.equal(fitted.height, 18.8);
    assert.equal(fitted.y, 200 + (73.3 - 18.8) / 2);
});

test('tall pieces fill height first and scale remains proportional', () => {
    const target = Model.Rect(0, 0, 188, 73.3);
    const fitted = Model.Contain(Model.Rect(0, 0, 10, 30), target, 2);
    assert.equal(fitted.height, 146.6);
    assert.ok(Math.abs(fitted.width / fitted.height - 1 / 3) < 1e-10);
});

test('alpha cropping ignores invisible padding but retains alpha exactly 2', () => {
    const pixels = new Uint8ClampedArray(10 * 14 * 4);
    pixels[3] = 1;
    pixels[(5 * 10 + 3) * 4 + 3] = 2;
    pixels[(6 * 10 + 7) * 4 + 3] = 255;
    assert.deepEqual(Model.AlphaBounds(pixels, 10, 14), Model.Rect(3, 5, 5, 2));
    assert.equal(Model.AlphaBounds(new Uint8ClampedArray(16), 2, 2), null);
});

test('moving a shared title anchor moves text and mana together', () => {
    const model = seed();
    const title = model.parts.find(part => part.id === 'TitleText');
    const mana = model.parts.find(part => part.id === 'ManaCost');
    const before = [Model.ResolvePart(model, title), Model.ResolvePart(model, mana)];
    model.anchors.Title.rect.x += 0.1;
    const after = [Model.ResolvePart(model, title), Model.ResolvePart(model, mana)];
    assert.ok(Math.abs(after[0].x - before[0].x - 100) < 1e-9);
    assert.ok(Math.abs(after[1].x - before[1].x - 100) < 1e-9);
});

test('cover uses full canvas bounds and preserves image proportions', () => {
    const fitted = Model.Cover(Model.Rect(0, 0, 500, 700), Model.Rect(0, 0, 1000, 1400));
    assert.deepEqual(fitted, Model.Rect(0, 0, 1000, 1400));
    const wide = Model.Cover(Model.Rect(0, 0, 1400, 700), Model.Rect(0, 0, 1000, 1400));
    assert.equal(wide.width, 2800);
    assert.equal(wide.x, -900);
});

test('history shares immutable image strings but isolates maps and placement', () => {
    const model = seed(), copy = Model.Clone(model);
    copy.maps.FrameImages.U = copy.maps.FrameImages.R;
    copy.anchors.Title.rect.x = 0.9;
    copy.assets.test = 'data:image/png;base64,AAAA';
    assert.notEqual(copy.maps.FrameImages.U, model.maps.FrameImages.U);
    assert.notEqual(copy.anchors.Title.rect.x, model.anchors.Title.rect.x);
    assert.equal(model.assets.test, undefined);
});

for (const [name, mutate] of [
    ['wrong canvas', model => model.canvas = 'landscape'],
    ['duplicate layer', model => model.parts.push(model.parts[0])],
    ['circular anchor', model => model.anchors.Title.relativeTo = 'Title'],
    ['missing asset', model => model.parts[1].asset = 'missing'],
    ['executable URL', model => model.assets.FrameImages_U = 'javascript:alert(1)'],
    ['remote image URL', model => model.assets.FrameImages_U = 'https://evil.test/image.png'],
    ['negative width', model => model.parts[0].placement.rect.width = -1],
    ['missing fallback', model => delete model.maps.PTImages.C],
    ['invalid two-color accent', model => model.preview.accentColors = ['M', 'R']],
    ['unbounded font size', model => model.parts.find(part => part.kind === 'text').style.size = Infinity],
    ['missing artwork', model => model.parts = model.parts.filter(part => part.kind !== 'artwork')]
]) {
    test(`validation rejects ${name}`, () => {
        const model = seed(); mutate(model);
        assert.throws(() => Model.Validate(model));
    });
}