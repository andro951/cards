import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { Model } from "../model.js";
import { Workflow as W } from "../workflow.js";

const seed = JSON.parse(await readFile(new URL("../default-template.json", import.meta.url), "utf8"));
test("structural frames retain their body while title pieces use card colors", () => {
    for (const variant of ["A", "L", "V"]) {
        const card = { variant, accentColors: ["U"] };
        assert.equal(Model.ColorFor({ id: "Frame" }, card), variant);
        assert.equal(Model.ColorFor({ id: "Title" }, card), "U");
        assert.equal(Model.ColorFor({ id: "Crown" }, { ...card, accentColors: ["U", "R"] }), "M");
    }
});
test("editing a split custom sheet part isolates its colors and clears old recoloring", () => {
    const model = Model.Clone(seed), frame = model.parts.find(p => p.id === "Frame"), title = model.parts.find(p => p.id === "Title");
    frame.map = title.map = "custom"; model.maps.custom = { C: "original", U: "blue" };
    frame.colorAssignments = { assigned: ["U"], reuse: true }; title.colorAssignments = structuredClone(frame.colorAssignments);
    title.colorSource = { source: "old" };
    W.Assign(model, title, "data:image/png;base64,AAAA", "new-blue.png", "U");
    assert.equal(model.maps[frame.map].U, "blue");
    assert.notEqual(frame.map, title.map);
    assert.equal(title.colorSource, undefined);
});
test("filename suggestions match whole words, not arbitrary letters", () => {
    assert.equal(W.GuessColor("my_blue_frame.png"), "U");
    assert.equal(W.GuessColor("frame_R.webp"), "R");
    assert.equal(W.GuessColor("crown.png"), null);
});
test("per-color upload retains fallback but flags every unassigned color", () => {
    const model = Model.Clone(seed), part = model.parts.find(p => p.id === "Title");
    W.Assign(model, part, "data:image/png;base64,AAAA", "blue.png", "U");
    assert.equal(W.Coverage(model).length, 9);
    part.colorAssignments.reuse = true;
    assert.equal(W.Coverage(model).length, 0);
});
test("replacing one part never changes a shared native map", () => {
    const model = Model.Clone(seed), native = { ...model.maps.FrameImages };
    W.Assign(model, model.parts.find(p => p.id === "Title"), "data:image/png;base64,AAAA", "blue.png", "U");
    assert.deepEqual(model.maps.FrameImages, native);
});
test("moving the subtitle moves its nested text and keeps relative attachment", () => {
    const model = Model.Clone(seed), part = model.parts.find(p => p.id === "Subtitle");
    const text = model.parts.find(p => p.id === "SubtitleText"), before = Model.ResolvePart(model, text);
    const rect = Model.ResolveAnchor(model, "Subtitle");
    W.MoveRegion(model, part, { ...rect, x: rect.x + 30, y: rect.y + 20 });
    assert.equal(Model.ResolvePart(model, text).x, before.x + 30);
    assert.equal(Model.ResolvePart(model, text).y, before.y + 20);
    assert.equal(model.anchors.Subtitle.relativeTo, "Title");
});
test("moving a native masked title moves its sheet and attached text together", () => {
    const model = Model.Clone(seed), part = model.parts.find(p => p.id === "Title"), rect = Model.ResolveAnchor(model, "Title");
    const before = Model.ResolvePart(model, model.parts.find(p => p.id === "TitleText"));
    W.MoveRegion(model, part, { ...rect, x: rect.x + 10 });
    assert.equal(Model.ResolvePart(model, part).x, 10);
    assert.equal(Model.ResolvePart(model, model.parts.find(p => p.id === "TitleText")).x, before.x + 10);
});
test("complete custom sheets disable duplicate masked body parts", () => {
    const model = Model.Clone(seed);
    W.SetSheet(model, "custom", false);
    assert.equal(model.parts.filter(p => W.SheetParts.includes(p.id) && p.visible).length, 1);
    assert.equal(model.parts.find(p => p.id === "Frame").mask, null);
});