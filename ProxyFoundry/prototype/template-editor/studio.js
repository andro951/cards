"use strict";

import { Editor as E } from "./editor.js";
import { Model } from "./model.js";
import { Renderer } from "./renderer.js";
import { Workflow as W } from "./workflow.js";
import { Exporter } from "./exporter.js";

const Studio = { step: 0, mode: "same", color: "W", maskSheet: true, generation: 0, reviewWarnings: [], galleryToken: 0 };
const el = E.element, button = E.button, field = E.field;
const steps = ["Start", "Parts", "Colors", "Text", "Review"];
Studio.signature = () => JSON.stringify({ name: E.model.name, anchors: E.model.anchors, palette: E.model.palette, maps: E.model.maps, parts: E.model.parts.map(({ colorSource, ...part }) => ["artwork"].includes(part.kind) || part.id === "SetSymbol" ? { ...part, asset: null, map: null } : part) });
const help = (parent, text) => parent.append(el("p", text, { color: "#b9b2a8", lineHeight: "1.6", fontSize: "13px" }));
const section = (parent, text) => E.section(parent, text);

//#region State and preview
Studio.update = async action => { await E.change(model => { action(model); W.Prune(model); }); Studio.panel(); };
E.error = error => { E.status.textContent = error.message || String(error); E.status.style.color = "#ffae9d"; console.error(error); };
E.afterChange = () => {
    E.undoButton.disabled = !E.undo.length; E.redoButton.disabled = !E.redo.length;
    const signature = Studio.signature();
    if (signature !== Studio.templateSignature) {
        Studio.templateSignature = signature; Studio.reviewWarnings = []; Studio.galleryToken++;
        if (Studio.exportButton)
            Studio.exportButton.disabled = true;
    }

    for (const [key, control] of Object.entries(Studio.sampleFields || {})) {
        if (document.activeElement !== control)
            control.value = E.model.preview[key] || "";
    }

    for (const item of Studio.colorButtons || []) {
        const active = item.dataset.color === E.model.preview.variant;
        item.setAttribute("aria-pressed", String(active)); item.style.background = active ? "#885022" : "#30251d";
    }

    if (Studio.realNameButton) {
        const active = Boolean(E.model.preview.nickname?.trim());
        Studio.realNameButton.setAttribute("aria-pressed", String(active));
        Studio.realNameButton.style.background = active ? "#885022" : "#30251d";
    }

    E.scheduleRender(); E.saveSoon();
};
E.inspect = () => Studio.panel();
E.buildSidebars = () => Studio.panel();
E.select = id => {
    const part = E.model.parts.find(item => item.id === id);
    if (id !== E.selected) {
        Studio.tintMask = part?.colorSource?.mask || null;
        Studio.mode = part?.colorSource ? "recolor" : part?.colorAssignments ? "individual" : "same";
    }

    E.selected = id; Studio.panel(); E.scheduleRender();
};
E.move = delta => Studio.update(model => {
    const index = model.parts.findIndex(part => part.id === E.selected), next = index + delta;
    if (next < 0 || next >= model.parts.length || ["text", "mana", "divider", "artwork"].includes(model.parts[next].kind))
        return;

    const part = model.parts.splice(index, 1)[0]; model.parts.splice(next, 0, part);
});
E.scheduleRender = () => {
    const epoch = ++E.epoch;
    requestAnimationFrame(async () => {
        if (epoch !== E.epoch)
            return;

        const canvas = E.renderer.makeCanvas(700, 980), model = Model.Clone(E.model);
        const result = await E.renderer.render(model, canvas, E.selected, false, () => epoch !== E.epoch, (done, total) => {
            if (epoch === E.epoch)
                E.status.textContent = `Loading preview images · ${done}/${total}. You can keep editing.`;
        }).catch(error => { if (epoch === E.epoch) E.error(error); return null; });
        if (!result || epoch !== E.epoch)
            return;

        const selected = model.parts.find(part => part.id === E.selected);
        if (E.guides && Studio.step !== 4 && selected && Model.Visible(selected, model.preview)) {
            const rect = Studio.region(selected, model), context = canvas.getContext("2d");
            context.save(); context.scale(canvas.width / Model.Width, canvas.height / Model.Height);
            context.strokeStyle = "#ffad50"; context.lineWidth = 2; context.strokeRect(rect.x, rect.y, rect.width, rect.height);
            context.fillStyle = "#ffad50"; context.fillRect(rect.x + rect.width - 6, rect.y + rect.height - 6, 12, 12); context.restore();
        }

        E.canvas.getContext("2d").clearRect(0, 0, E.canvas.width, E.canvas.height);
        E.canvas.getContext("2d").drawImage(canvas, 0, 0, E.canvas.width, E.canvas.height);
        E.lastPositions = result.positions; E.canvas.dataset.ready = String(epoch);
        Studio.previewWarnings = result.warnings;
        E.status.textContent = result.warnings.length ? result.warnings.join(" · ") : `Preview ready · ${Math.round(result.milliseconds)} ms`;
        E.status.style.color = result.warnings.length ? "#ffc481" : "#a7d8b5";
        canvas.width = 1;
    });
};
Studio.changeStep = index => { Studio.step = index; Studio.galleryToken++; Studio.panel(); E.scheduleRender(); };
Studio.reset = async () => {
    const generation = ++Studio.generation;
    const model = Model.Validate(await (await fetch("/default-template.json")).json());
    if (generation !== Studio.generation)
        return;
    E.checkpoint(); E.model = model; E.selected = "Title"; Studio.tintMask = null; Studio.mode = "same";
    E.afterChange(); Studio.changeStep(1);
};
Studio.open = () => E.pickFile("application/json,.json", async file => {
    const generation = ++Studio.generation;
    if (file.size > 64 * 1024 * 1024)
        throw new Error(`Choose a template smaller than 64 MB.`);

    const parsed = JSON.parse(await file.text()), definition = parsed.editorSource || parsed;
    if (definition.assetTable === "visualRecipe.sources") {
        const needed = new Set(definition.parts.flatMap(part => [part.asset, part.mask, ...Object.values(definition.maps[part.map] || {})]).filter(Boolean));
        definition.assets = Object.fromEntries(Object.entries(parsed.visualRecipe.sources).filter(([id]) => needed.has(id)).map(([id, source]) => {
            if (source.startsWith("/api/assets/")) {
                const asset = parsed.assets?.[source.split("/").pop()];
                if (!asset)
                    throw new Error(`This export is missing a frame image. Download it again from BulkProxyForge.`);

                source = `data:${asset.mime};base64,${asset.base64}`;
            }

            return [id, source];
        }));
    }

    const model = Model.Validate(definition);
    const native = await (await fetch("/default-template.json")).json();
    for (const [id, source] of Object.entries(native.assets)) {
        if (id.startsWith("Mask_") && !model.assets[id])
            model.assets[id] = source;
    }
    if (generation !== Studio.generation)
        return;
    E.checkpoint(); E.model = model; E.afterChange(); Studio.changeStep(1);
});
//#endregion

//#region Image inputs
Studio.recolor = async (source, color, mask = null) => {
    const image = await E.renderer.loadImage(source), scale = Math.min(1, 2010 / image.naturalWidth, 2814 / image.naturalHeight);
    const canvas = E.renderer.makeCanvas(Math.max(1, Math.round(image.naturalWidth * scale)), Math.max(1, Math.round(image.naturalHeight * scale))), context = canvas.getContext("2d");
    context.drawImage(image, 0, 0, canvas.width, canvas.height); context.globalCompositeOperation = "multiply";
    context.fillStyle = color; context.fillRect(0, 0, canvas.width, canvas.height);
    context.globalCompositeOperation = "destination-in"; context.drawImage(image, 0, 0, canvas.width, canvas.height);
    if (mask) {
        const tinted = E.renderer.makeCanvas(canvas.width, canvas.height), tint = tinted.getContext("2d");
        tint.drawImage(canvas, 0, 0); tint.globalCompositeOperation = "destination-in";
        tint.drawImage(await E.renderer.loadImage(mask), 0, 0, canvas.width, canvas.height);
        context.globalCompositeOperation = "source-over"; context.clearRect(0, 0, canvas.width, canvas.height); context.drawImage(image, 0, 0, canvas.width, canvas.height);
        context.globalCompositeOperation = "destination-out"; context.drawImage(await E.renderer.loadImage(mask), 0, 0, canvas.width, canvas.height);
        context.globalCompositeOperation = "source-over"; context.drawImage(tinted, 0, 0); tinted.width = 1;
    }

    const result = canvas.toDataURL("image/png"); canvas.width = 1; return result;
};
Studio.assignUpload = (part, fullSheet = false) => E.pickFile("image/png,image/jpeg,image/webp,image/svg+xml", async file => {
    const mode = Studio.mode, code = Studio.color, tintMask = Studio.tintMask, maskSheet = Studio.maskSheet, generation = Studio.generation, palette = { ...E.model.palette };
    const source = await E.readImage(file);
    if (mode === "recolor") {
        E.status.textContent = "Preparing color treatments…";
        const treatments = {};
        for (const variant of Model.Variants) {
            treatments[variant] = await Studio.recolor(source, palette[variant] || ({ M: "#c3a24f", A: "#b1b4b8", L: "#b4a18e", C: "#c6c6c6", V: "#967453" })[variant], tintMask);
            await new Promise(resolve => setTimeout(resolve, 0));
        }

        if (generation !== Studio.generation)
            return;

        await Studio.update(model => {
            const current = model.parts.find(item => item.id === part.id);
            for (const variant of Model.Variants) {
                W.Assign(model, current, treatments[variant], `${file.name} · ${W.ColorNames[variant]}`, variant);
            }

            current.colorAssignments.reuse = true; current.colorSource = { source, filename: file.name, mask: tintMask || null };
            Studio.applyUploadLayout(model, current, fullSheet, undefined, maskSheet);
        });
    }
    else {
        if (generation !== Studio.generation)
            return;
        await Studio.update(model => {
            const current = model.parts.find(item => item.id === part.id);
            const id = W.Assign(model, current, source, file.name, mode === "individual" ? code : null);
            Studio.applyUploadLayout(model, current, fullSheet, id, maskSheet);
        });
    }
});
Studio.applyUploadLayout = (model, part, fullSheet, asset = part.asset, maskSheet = Studio.maskSheet) => {
    if (fullSheet) {
        const map = part.map, assignments = part.colorAssignments, colorSource = part.colorSource;
        W.SetSheet(model, asset, maskSheet);
        for (const id of W.SheetParts) {
            const item = model.parts.find(layer => layer.id === id);
            item.map = map; item.asset = map ? null : asset; item.colorAssignments = assignments ? structuredClone(assignments) : undefined;
            if (id === "Pinline" && map && maskSheet)
                item.treatment = "pinline";
        }

        if (colorSource)
            model.parts.find(item => item.id === "Frame").colorSource = colorSource;

        return;
    }

    part.alignment = "piece"; part.mask = null; part.trimAlpha = true; part.scale = 1;
    part.treatment = part.map && ["Crown", "Pinline"].includes(part.id) ? part.id.toLowerCase() : "none";
    if (model.anchors[part.id])
        part.placement = { relativeTo: part.id, rect: Model.Rect(0, 0, 1, 1) };
};
Studio.imageControls = (parent, part, fullSheet = false) => {
    const source = E.renderer.sourceFor(E.model, part);
    if (source) {
        const thumb = el("img", "", { maxWidth: "100%", width: "120px", height: "110px", objectFit: "contain", background: "#36332f", borderRadius: "6px" });
        thumb.src = source; thumb.alt = `${part.name} current image`; parent.append(thumb);
    }

    field(parent, "Image colors", Studio.mode, value => { Studio.mode = value; Studio.panel(); }, { choices: [["same", "One image · keep its colors"], ["recolor", "One image · create color treatments"], ["individual", "Separate images for each color"]] });
    if (Studio.mode === "individual") {
        field(parent, "Assign to color", Studio.color, value => { Studio.color = value; }, { choices: Model.Variants.map(code => [code, W.ColorNames[code]]) });
        button("Upload several color images", () => Studio.batch(part, fullSheet), parent);
    }

    if (Studio.mode === "recolor") {
        help(parent, "A light, neutral image works best. Texture and transparency are kept. Use a tint mask if only part should change color.");
        button(Studio.tintMask ? "Replace tint mask" : "Optional: upload tint mask", () => E.pickFile("image/png,image/webp", async file => { Studio.tintMask = await E.readImage(file); Studio.panel(); }), parent);
        if (Studio.tintMask)
            button("Remove tint mask", () => { Studio.tintMask = null; Studio.panel(); }, parent);
    }

    button(fullSheet ? "Upload frame sheet" : "Upload replacement image", () => Studio.assignUpload(part, fullSheet), parent);
    if (part.colorAssignments) {
        field(parent, "Use a shared image for unassigned colors", part.colorAssignments.reuse, value => Studio.update(model => model.parts.find(item => item.id === part.id).colorAssignments.reuse = value), { type: "checkbox" });
        for (const code of Model.Variants) {
            const id = E.model.maps[part.map][code] || E.model.maps[part.map].C;
            help(parent, `${W.ColorNames[code]}: ${part.colorAssignments.assigned.includes(code) ? E.model.assetMetadata?.[id]?.filename || "Assigned" : part.colorAssignments.reuse ? "Shared image" : "Needs image"}`);
        }
    }
};
Studio.batch = (part, fullSheet) => {
    const input = el("input"); input.type = "file"; input.multiple = true; input.accept = "image/png,image/jpeg,image/webp,image/svg+xml";
    input.onchange = () => Promise.resolve().then(async () => {
        const files = [...input.files];
        if (!files.length)
            return;

        if (files.length > 10)
            throw new Error(`Choose up to 10 color images at once.`);

        const dialog = el("dialog", "", { background: "#201c19", color: "#eee6db", border: "1px solid #755336", borderRadius: "12px", padding: "24px", maxWidth: "600px", width: "calc(100vw - 80px)", maxHeight: "80vh", overflowY: "auto" });
        dialog.append(el("h2", "Assign your color images")); help(dialog, "Check the suggested colors before applying.");
        const assignments = files.map(file => ({ file, control: field(dialog, file.name, W.GuessColor(file.name) || "", () => {}, { choices: [["", "Choose a color"], ...Model.Variants.map(code => [code, W.ColorNames[code]])] }) }));
        const message = el("p"); dialog.append(message);
        button("Apply color images", async () => {
            const codes = assignments.map(item => item.control.value);
            if (codes.some(code => !code) || new Set(codes).size !== codes.length) {
                message.textContent = "Choose a different color for each image."; return;
            }

            const prepared = [];
            for (const item of assignments) {
                message.textContent = `Reading ${item.file.name}…`;
                prepared.push({ ...item, source: await E.readImage(item.file) });
            }

            await Studio.update(model => {
                const current = model.parts.find(item => item.id === part.id);
                for (const item of prepared) {
                    W.Assign(model, current, item.source, item.file.name, item.control.value);
                }

                Studio.applyUploadLayout(model, current, fullSheet);
            });
            dialog.close();
        }, dialog);
        button("Cancel", () => dialog.close(), dialog); dialog.onclose = () => dialog.remove(); document.body.append(dialog); dialog.showModal();
    }).catch(E.error);
    input.click();
};
//#endregion

//#region Guided panels
Studio.panel = () => {
    Studio.controls.replaceChildren();
    for (const item of Studio.stepButtons) {
        const active = Number(item.dataset.step) === Studio.step;
        item.setAttribute("aria-current", active ? "step" : "false"); item.style.background = active ? "#885022" : "#211e1b";
    }

    Studio.controls.append(el("h2", `${Studio.step + 1}. ${steps[Studio.step]}`, { margin: "0 0 15px", fontSize: "23px" }));
    [Studio.startPanel, Studio.partsPanel, Studio.colorsPanel, Studio.textPanel, Studio.reviewPanel][Studio.step]();
    const navigation = el("nav", "", { display: "flex", justifyContent: "space-between", marginTop: "24px", paddingTop: "12px", borderTop: "1px solid #49382b" });
    if (Studio.step > 0)
        button("Back", () => Studio.changeStep(Studio.step - 1), navigation);

    if (Studio.step < 4)
        button(`Next: ${steps[Studio.step + 1]}`, () => Studio.changeStep(Studio.step + 1), navigation);

    Studio.controls.append(navigation);
};
Studio.startPanel = () => {
    const parent = Studio.controls;
    field(parent, "Template name", E.model.name, value => E.change(model => model.name = value));
    help(parent, "Start with working parts, then change only what you need. Your card always stays 5:7.");
    button("Start from CardConjurer M15", Studio.reset, parent);
    button("Open editable template", Studio.open, parent);
    const custom = section(parent, "Use a frame you made");
    help(custom, "Upload a transparent full-card sheet, or add separate pieces in Parts. A sheet should have a transparent artwork opening.");
    field(custom, "Split sheet with existing M15 masks", Studio.maskSheet, value => { Studio.maskSheet = value; }, { type: "checkbox" });
    help(custom, "Turn this off for a complete frame with its own layout. Native crowns and power/toughness remain available in Parts.");
    Studio.imageControls(custom, E.model.parts.find(part => part.id === "Frame"), true);
    const art = section(parent, "Test artwork");
    button("Upload test artwork", () => E.upload(E.model.parts.find(part => part.kind === "artwork"), false, "all"), art);
    help(art, "Only used for preview. It is excluded from exported templates.");
    field(art, "Full-card artwork", E.model.parts.find(part => part.kind === "artwork").placement.relativeTo === "Canvas", value => Studio.update(model => model.parts.find(part => part.kind === "artwork").placement = { relativeTo: value ? "Canvas" : "ArtWindow", rect: Model.Rect(0, 0, 1, 1) }), { type: "checkbox" });
};
Studio.partChooser = (parent, filter) => {
    const list = el("nav", "", { display: "flex", flexWrap: "wrap", gap: "4px", marginBottom: "18px" });
    for (const part of E.model.parts.filter(filter)) {
        const item = button(`${part.visible ? "" : "○ "}${part.name}`, () => E.select(part.id), list);
        item.dataset.part = part.id; item.setAttribute("aria-pressed", String(E.selected === part.id));
        if (E.selected === part.id)
            item.style.borderColor = "#ffa644";
    }

    parent.append(list);
};
Studio.partsPanel = () => {
    const parent = Studio.controls;
    help(parent, "Select a part here or on the card. Drag it to move it; drag its lower-right corner to resize. Text follows its frame region.");
    Studio.partChooser(parent, part => !["text", "mana", "divider"].includes(part.kind));
    let part = E.model.parts.find(part => part.id === E.selected);
    if (!part || ["text", "mana"].includes(part.kind)) {
        E.selected = "Title"; part = E.model.parts.find(part => part.id === "Title");
    }

    parent.append(el("h3", part.name));
    if (part.kind !== "artwork")
        button("Restore M15 part", () => Studio.restore(part.id), parent);
    field(parent, "Show this part", part.visible, value => Studio.update(model => model.parts.find(item => item.id === part.id).visible = value), { type: "checkbox" });
    field(parent, "When it appears", part.when, value => Studio.update(model => model.parts.find(item => item.id === part.id).when = value), { choices: [["always", "Always"], ["legendary", "Legendary cards"], ["nickname", "Cards with nicknames"], ["pt", "Cards with power/toughness"], ["rulesAndFlavor", "Rules and flavor together"]] });
    Studio.imageControls(section(parent, "Replace artwork for this part"), part);
    field(parent, "Opacity (%)", part.opacity * 100, value => E.change(model => model.parts.find(item => item.id === part.id).opacity = value / 100), { type: "number", min: 0, max: 100, step: 1 });
    Studio.geometry(parent, part);
    const advanced = el("details"); advanced.append(el("summary", "Advanced: masks, alignment and layers")); parent.append(advanced);
    field(advanced, "Image alignment", part.alignment, value => Studio.update(model => {
        const current = model.parts.find(item => item.id === part.id); current.alignment = value; current.trimAlpha = value === "piece";
        current.placement = { relativeTo: value === "full-card" ? "Canvas" : model.anchors[part.id] ? part.id : "Canvas", rect: Model.Rect(0, 0, 1, 1) };
    }), { choices: [["piece", "Fit this piece to its region"], ["full-card", "Preserve full-card alignment"]] });
    button("Upload transparency mask", () => E.upload(part, true), advanced);
    button("Remove mask", () => Studio.update(model => model.parts.find(item => item.id === part.id).mask = null), advanced);
    field(advanced, "Cut out layers beneath this part", part.blend === "destination-out", value => Studio.update(model => model.parts.find(item => item.id === part.id).blend = value ? "destination-out" : "source-over"), { type: "checkbox" });
    button("Bring forward", () => E.move(1).then(Studio.panel), advanced);
    button("Send backward", () => E.move(-1).then(Studio.panel), advanced);
    button("Add another part", E.addPart, advanced);
    help(advanced, "Text stays above the frame layers. Masks use transparency and full-card coordinates.");
};
Studio.geometry = (parent, part) => {
    const frame = section(parent, "Position and size"), rect = Studio.region(part);
    for (const [key, label] of [["x", "Left (%)"], ["y", "Top (%)"], ["width", "Width (%)"], ["height", "Height (%)"]]) {
        const dimension = ["x", "width"].includes(key) ? Model.Width : Model.Height;
        field(frame, label, Math.round(rect[key] / dimension * 10000) / 100, value => E.change(model => {
            const current = model.parts.find(item => item.id === part.id), next = Studio.region(current, model); next[key] = value * dimension / 100;
            W.MoveRegion(model, current, next);
        }), { type: "number", min: key === "width" || key === "height" ? 0.1 : -100, max: 200, step: 0.1 });
    }
};
Studio.region = (part, model = E.model) => model.anchors[part.id] ? Model.ResolveAnchor(model, part.id) : Model.ResolvePart(model, part);
Studio.restore = async id => {
    const original = await (await fetch("/default-template.json")).json();
    await Studio.update(model => {
        const index = model.parts.findIndex(part => part.id === id), part = original.parts.find(part => part.id === id);
        if (!part)
            throw new Error(`This is a custom part. Remove its replacement instead.`);

        Object.assign(model.assets, original.assets);
        if (part.map) {
            const map = `restored_${id}`; model.maps[map] = { ...original.maps[part.map] }; part.map = map;
        }

        model.parts[index] = part;
        if (original.anchors[id])
            model.anchors[id] = original.anchors[id];
    });
};
Studio.colorsPanel = () => {
    const parent = Studio.controls;
    help(parent, "Check each treatment. Select a part to provide individual images or use one recolorable image. Missing assignments stay visible until you resolve them.");
    Studio.partChooser(parent, part => part.kind === "image" && part.visible);
    const part = E.model.parts.find(item => item.id === E.selected && item.kind === "image");
    if (part)
        Studio.imageControls(parent, part);

    const palette = section(parent, "Recolor palette and two-color accents");
    for (const code of "WUBRG") {
        field(palette, `${W.ColorNames[code]} tint`, E.model.palette[code], value => Studio.palette(code, value), { type: "color" });
    }

    help(palette, "Recolorable uploads update automatically. Existing colored images keep their own colors.");
    const errors = W.Coverage(E.model);
    help(parent, errors.length ? errors.join("\n") : "All enabled parts have a color treatment or an explicit shared image.");
};
Studio.palette = async (code, color) => {
    Studio.paletteEpochs ??= {};
    const epoch = Studio.paletteEpochs[code] = (Studio.paletteEpochs[code] || 0) + 1, generation = Studio.generation;
    const parts = E.model.parts.filter(part => part.colorSource).map(part => ({ id: part.id, colorSource: part.colorSource }));
    const images = await Promise.all(parts.map(async part => ({ ...part, source: await Studio.recolor(part.colorSource.source, color, part.colorSource.mask) })));
    if (epoch !== Studio.paletteEpochs[code] || generation !== Studio.generation)
        return;
    await Studio.update(model => {
        model.palette[code] = color;
        for (const image of images) {
            const part = model.parts.find(item => item.id === image.id);
            if (!part?.map || part.colorSource.source !== image.colorSource.source)
                continue;

            const id = `upload_${crypto.randomUUID()}`; model.assets[id] = image.source;
            model.assetMetadata[id] = { filename: `${image.colorSource.filename} · ${W.ColorNames[code]}` }; model.maps[part.map][code] = id;
        }
    });
};
Studio.textPanel = () => {
    const parent = Studio.controls;
    help(parent, "Text fits automatically. Edit its normal size and appearance; edit the sample text below the preview to check longer content.");
    Studio.partChooser(parent, part => ["text", "mana", "divider"].includes(part.kind));
    const part = E.model.parts.find(item => item.id === E.selected);
    if (!part || !["text", "mana", "divider"].includes(part.kind)) {
        E.selected = "TitleText"; Studio.panel(); return;
    }

    parent.append(el("h3", part.name));
    field(parent, "Show text", part.visible, value => Studio.update(model => model.parts.find(item => item.id === part.id).visible = value), { type: "checkbox" });
    if (part.kind === "divider") {
        help(parent, "Placed automatically between shared rules and flavor text. Turn off shared flow to position the text boxes independently.");
        return;
    }
    if (["rules", "flavor"].includes(part.field)) {
        field(parent, "Flow rules and flavor together", part.flow === "rules", value => Studio.update(model => model.parts.filter(item => ["rules", "flavor"].includes(item.field)).forEach(item => item.flow = value ? "rules" : null)), { type: "checkbox" });
        help(parent, "Shared flow automatically positions the italic flavor and divider after the rules. Separate flow lets you place and style each box independently.");
    }
    if (part.style) {
        const update = (key, value) => E.change(model => model.parts.find(item => item.id === part.id).style[key] = value);
        field(parent, "Font", part.style.font, value => update("font", value), { choices: [["belerenb", "Beleren"], ["belerenbsc", "Beleren small caps"], ["mplantin", "Plantin"], ["mplantini", "Plantin italic"], ["sans-serif", "Sans serif"], ["serif", "Serif"]] });
        field(parent, "Text size", part.style.size, value => E.change(model => { const current = model.parts.find(item => item.id === part.id); current.style.size = value; current.style.minSize = Math.min(value, current.style.minSize); }), { type: "number", min: 1, max: 200, step: 1 });
        field(parent, "Minimum size", part.style.minSize, value => update("minSize", value), { type: "number", min: 1, max: part.style.size, step: 1 });
        field(parent, "Text color", part.style.color, value => update("color", value), { type: "color" });
        field(parent, "Alignment", part.style.align, value => update("align", value), { choices: [["left", "Left"], ["center", "Center"], ["right", "Right"]] });
        field(parent, "Outline size", part.style.outline, value => update("outline", value), { type: "number", min: 0, max: 20, step: 1 });
        field(parent, "Outline color", part.style.outlineColor, value => update("outlineColor", value), { type: "color" });
    }
    else if (part.kind === "mana")
        field(parent, "Mana symbol size", part.symbolSize, value => E.change(model => model.parts.find(item => item.id === part.id).symbolSize = value), { type: "number", min: 1, max: 200, step: 1 });

    Studio.geometry(parent, part);
};
Studio.reviewPanel = () => {
    const parent = Studio.controls, errors = W.Check(E.model);
    help(parent, "Check a range of cards before importing. Export includes every color image and your editable source; test artwork is excluded.");
    for (const error of errors) {
        help(parent, error);
    }

    const review = button("Check representative cards", Studio.review, parent);
    review.disabled = Boolean(errors.length);
    Studio.gallery = el("section", "", { display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(130px,1fr))", gap: "14px", marginTop: "15px" }); parent.append(Studio.gallery);
    Studio.reviewStatus = el("p"); parent.append(Studio.reviewStatus);
    Studio.exportButton = button("Download importable template", Studio.export, parent); Studio.exportButton.disabled = true;
    button("Download editable source", async () => E.download(`${E.model.name}.editable.json`, new Blob([JSON.stringify(await Exporter.Portable(E.model), null, 2)], { type: "application/json" })), parent);
    help(parent, "In BulkProxyForge, open Templates → Import Template and select the importable JSON. This version supports ordinary cards and lands; specialty layouts will be added separately.");
    Studio.reviewStatus.textContent = "Run the review to enable production export.";
};
Studio.review = async () => {
    const token = ++Studio.galleryToken, snapshot = Model.Clone(E.model), renderer = new Renderer();
    Studio.gallery.replaceChildren(); Studio.reviewWarnings = [];
    const samples = [...W.Samples, ...Model.Variants.map(code => ({ ...W.Samples[1], label: W.ColorNames[code], variant: code, accentColors: [code] }))];
    for (let first = 0; first < 5; first++) {
        for (let second = first + 1; second < 5; second++) {
            const colors = ["WUBRG"[first], "WUBRG"[second]];
            samples.push({ ...W.Samples[1], label: colors.map(code => W.ColorNames[code]).join(" / "), accentColors: colors });
        }
    }
    Studio.reviewStatus.textContent = `Checking 0/${samples.length}…`;
    for (let i = 0; i < samples.length; i++) {
        if (token !== Studio.galleryToken)
            return;

        Object.assign(snapshot.preview, samples[i]);
        const figure = el("figure", "", { margin: 0 }), canvas = renderer.makeCanvas(280, 392);
        const result = await renderer.render(snapshot, canvas);
        if (token !== Studio.galleryToken)
            return;

        Object.assign(canvas.style, { width: "100%", height: "auto", cursor: "pointer" });
        const inspect = button(`Inspect ${samples[i].label}`, () => E.change(model => Object.assign(model.preview, samples[i])), figure);
        inspect.prepend(canvas); inspect.style.padding = "0"; inspect.style.maxWidth = "100%";
        figure.append(el("figcaption", samples[i].label, { marginTop: "5px", fontSize: "12px" })); Studio.gallery.append(figure);
        Studio.reviewWarnings.push(...result.warnings.map(message => `${samples[i].label}: ${message}`));
        Studio.reviewStatus.textContent = `Checking ${i + 1}/${samples.length}…`; await new Promise(resolve => setTimeout(resolve, 0));
    }

    Studio.reviewStatus.textContent = Studio.reviewWarnings.length ? Studio.reviewWarnings.join("\n") : `${samples.length} samples checked. Ready to export.`;
    Studio.exportButton.disabled = Boolean(Studio.reviewWarnings.length);
};
Studio.export = async () => {
    const exportButton = Studio.exportButton, signature = Studio.templateSignature;
    exportButton.disabled = true; const snapshot = Model.Clone(E.model);
    const result = await Exporter.Build(snapshot, label => { E.status.textContent = `Building portable template · ${label}. You can keep editing.`; }).catch(error => { exportButton.disabled = false; throw error; });
    E.download(`${snapshot.name}.bpf-template.json`, new Blob([JSON.stringify(result)], { type: "application/json" }));
    const changed = signature !== Studio.templateSignature;
    E.status.textContent = changed ? "Downloaded the version from before your latest edits. Review and export again to include them." : "Template downloaded. Import it from BulkProxyForge → Templates.";
    exportButton.disabled = changed;
};
//#endregion

//#region Canvas interaction and boot
Studio.drag = () => {
    let drag = null;
    E.canvas.onpointerdown = event => {
        if (Studio.step === 0 || Studio.step === 4)
            return;

        const point = E.pointer(event), eligible = E.model.parts.filter(part => Model.Visible(part, E.model.preview) && (Studio.step === 3 ? ["text", "mana"].includes(part.kind) : part.kind === "image"));
        const hit = part => { const rect = Studio.region(part); return point.x >= rect.x - 8 && point.x <= rect.x + rect.width + 8 && point.y >= rect.y - 8 && point.y <= rect.y + rect.height + 8; };
        const part = eligible.find(part => part.id === E.selected && hit(part)) || [...eligible].reverse().find(part => part.placement.relativeTo !== "Canvas" && hit(part)) || eligible.find(part => W.SheetParts.includes(part.id) && part.id !== "Frame" && hit(part));
        if (!part)
            return;

        E.select(part.id); E.checkpoint(); const rect = Studio.region(part);
        drag = { id: part.id, point, rect, resize: Math.abs(point.x - rect.x - rect.width) < 22 && Math.abs(point.y - rect.y - rect.height) < 22, model: Model.Clone(E.model) };
        E.canvas.setPointerCapture(event.pointerId); event.preventDefault();
    };
    E.canvas.onpointermove = event => {
        if (!drag)
            return;

        const point = E.pointer(event), next = { ...drag.rect };
        if (drag.resize) {
            next.width = Math.max(8, drag.rect.width + point.x - drag.point.x); next.height = Math.max(8, drag.rect.height + point.y - drag.point.y);
        }
        else {
            next.x += point.x - drag.point.x; next.y += point.y - drag.point.y;
        }

        E.model = Model.Clone(drag.model); W.MoveRegion(E.model, E.model.parts.find(part => part.id === drag.id), next); E.scheduleRender();
    };
    const end = () => { if (!drag) return; drag = null; E.afterChange(); Studio.panel(); };
    E.canvas.onpointerup = end; E.canvas.onpointercancel = end;
};
Studio.boot = async () => {
    Object.assign(document.body.style, { margin: "0", background: "#12110f", color: "#eee6db", font: "14px system-ui, sans-serif" });
    E.model = Model.Validate(await (await fetch("/default-template.json")).json()); E.selected = "Title";
    E.database = await E.openStorage().catch(error => { console.warn("Draft storage unavailable", error); return null; });
    if (E.database) {
        const saved = await E.loadDraft().catch(error => { console.warn("Draft could not load", error); return null; });
        if (saved)
            E.model = await Promise.resolve().then(() => Model.Validate(saved)).catch(error => { console.warn("Invalid draft", error); return E.model; });
    }

    const watermark = E.model.parts.find(part => part.id === "Watermark");
    if (watermark && !watermark.asset && !watermark.map)
        watermark.visible = false;

    const header = el("header", "", { padding: "16px 24px", borderBottom: "1px solid #49382b" });
    header.append(el("h1", "Template Studio", { fontSize: "23px", margin: "0 0 6px" }));
    const toolbar = el("nav", "", { display: "flex", flexWrap: "wrap", gap: "5px" });
    E.undoButton = button("Undo", () => E.history(false), toolbar); E.redoButton = button("Redo", () => E.history(true), toolbar);
    E.undoButton.disabled = true; E.redoButton.disabled = true;
    button("Open template", Studio.open, toolbar);
    button("Download preview PNG", E.exportPNG, toolbar);
    button("Retry preview", E.scheduleRender, toolbar);
    const old = el("a", "Open original advanced prototype", { color: "#bea17f", padding: "10px", fontSize: "12px" }); old.href = "/classic"; toolbar.append(old);
    header.append(toolbar); document.body.append(header);
    const navigation = el("nav", "", { display: "flex", flexWrap: "wrap", padding: "12px 24px", gap: "6px" });
    Studio.stepButtons = steps.map((name, index) => { const item = button(`${index + 1} ${name}`, () => Studio.changeStep(index), navigation); item.dataset.step = index; return item; });
    document.body.append(navigation);
    const main = el("main", "", { display: "flex", flexWrap: "wrap", gap: "28px", alignItems: "flex-start", padding: "8px 24px 30px", maxWidth: "1450px", margin: "auto" });
    Studio.controls = el("section", "", { flex: "1 1 360px", minWidth: "0", maxWidth: "650px", background: "#1c1915", border: "1px solid #49382b", padding: "24px", borderRadius: "12px", boxSizing: "border-box" });
    const preview = el("section", "", { flex: "1 1 340px", minWidth: "0", maxWidth: "620px", position: "sticky", top: "14px", textAlign: "center" });
    const presets = el("nav", "", { display: "flex", flexWrap: "wrap", justifyContent: "center", marginBottom: "8px" });
    button("Ordinary", () => E.change(model => Object.assign(model.preview, { variant: "U", accentColors: ["U"], legendary: false })), presets);
    button("Legendary · two colors", () => E.change(model => Object.assign(model.preview, { variant: "M", accentColors: ["U", "R"], legendary: true })), presets);
    Studio.realNameButton = button("Real-name bar", () => E.change(model => {
        if (model.preview.nickname?.trim()) {
            Studio.previewNickname = model.preview.nickname; model.preview.nickname = "";
        }
        else
            model.preview.nickname = Studio.previewNickname || "Preview nickname";
    }), presets);
    const hasNickname = Boolean(E.model.preview.nickname?.trim());
    Studio.realNameButton.setAttribute("aria-pressed", String(hasNickname));
    Studio.realNameButton.style.background = hasNickname ? "#885022" : "#30251d";

    preview.append(presets);
    const colorControls = el("nav", "", { display: "flex", flexWrap: "wrap", justifyContent: "center", marginBottom: "10px" });
    Studio.colorButtons = [];
    for (const code of Model.Variants) {
        const item = button(W.ColorNames[code], () => E.change(model => { model.preview.variant = code; model.preview.accentColors = [code]; }), colorControls);
        item.dataset.color = code; item.setAttribute("aria-pressed", String(code === E.model.preview.variant));
        if (code === E.model.preview.variant)
            item.style.background = "#885022";

        Studio.colorButtons.push(item);
    }

    preview.append(colorControls);
    E.canvas = E.renderer.makeCanvas(700, 980); E.canvas.setAttribute("aria-label", "Live template preview; drag selected region to position it");
    Object.assign(E.canvas.style, { width: "auto", height: "auto", maxHeight: "calc(100vh - 235px)", maxWidth: "100%", borderRadius: "12px", touchAction: "none", cursor: "move" }); preview.append(E.canvas);
    E.status = el("p", "Loading preview…", { fontSize: "12px", lineHeight: "1.5", whiteSpace: "pre-line" }); E.status.setAttribute("role", "status"); preview.append(E.status);
    E.saveStatus = el("p", "", { fontSize: "12px", color: "#aaa298" }); preview.append(E.saveStatus);
    field(preview, "Show placement guides", E.guides, value => { E.guides = value; E.scheduleRender(); }, { type: "checkbox" });
    const sampleFields = el("details", "", { textAlign: "left" }); sampleFields.append(el("summary", "Edit sample card text")); preview.append(sampleFields);
    Studio.sampleFields = {};
    for (const [key, label] of [["name", "Sample real name"], ["nickname", "Sample nickname"], ["mana", "Sample mana"], ["type", "Sample type"], ["rules", "Sample rules"], ["flavor", "Sample flavor"], ["pt", "Sample power/toughness"]]) {
        Studio.sampleFields[key] = field(sampleFields, label, E.model.preview[key], value => E.change(model => model.preview[key] = value), { multiline: ["rules", "flavor"].includes(key), live: true });
    }

    main.append(Studio.controls, preview); document.body.append(main);
    const resize = () => {
        const narrow = innerWidth < 900;
        preview.style.order = narrow ? "-1" : "0"; preview.style.position = narrow ? "static" : "sticky";
        E.canvas.style.maxHeight = narrow ? "45vh" : "calc(100vh - 235px)";
    };
    window.addEventListener("resize", resize); resize();
    Studio.templateSignature = Studio.signature();
    Studio.panel(); Studio.drag(); E.scheduleRender(); window.TemplateEditor = E; window.TemplateStudio = Studio;
    document.addEventListener("keydown", event => {
        if (!event.target.matches("input, textarea, select") && (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
            event.preventDefault(); E.history(event.shiftKey);
        }
    });
};
Studio.boot().catch(error => { if (E.status) E.error(error); else document.body.append(el("p", error.message)); });
//#endregion