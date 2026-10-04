"use strict";

import { Model } from "./model.js";
import { Renderer } from "./renderer.js";

const Editor = {};
Editor.renderer = new Renderer();
Editor.model = null;
Editor.selected = "TitleText";
Editor.undo = [];
Editor.redo = [];
Editor.epoch = 0;
Editor.guides = true;
Editor.lastPositions = new Map();
Editor.pendingSave = 0;
Editor.database = null;

//#region DOM controls
Editor.element = (tag, text = "", style = {}) => {
    const element = document.createElement(tag);
    if (text)
        element.textContent = text;

    Object.assign(element.style, style);
    return element;
};
Editor.button = (text, action, parent) => {
    const button = Editor.element("button", text);
    button.type = "button"; button.onclick = () => Promise.resolve().then(action).catch(Editor.error);
    Object.assign(button.style, { padding: "8px 10px", cursor: "pointer", borderRadius: "5px", border: "1px solid #755336", background: "#30251d", color: "#ffe8c5", margin: "3px" });
    parent?.append(button);
    return button;
};
Editor.field = (parent, label, value, action, options = {}) => {
    const row = Editor.element("label", "", { display: "block", marginBottom: "10px" });
    row.append(Editor.element("span", label, { display: "block", fontSize: "13px", marginBottom: "4px", color: "#d8ba98" }));
    const control = Editor.element(options.multiline ? "textarea" : options.choices ? "select" : "input");
    control.setAttribute("aria-label", label);
    if (options.choices) {
        for (const [key, text] of options.choices) {
            const option = Editor.element("option", text); option.value = key; control.append(option);
        }
    }
    else if (!options.multiline)
        control.type = options.type || "text";

    if (options.type === "checkbox")
        control.checked = Boolean(value);
    else
        control.value = value ?? "";

    if (options.type === "number") {
        control.step = options.step || "0.01";
        if (options.min !== undefined)
            control.min = options.min;
        if (options.max !== undefined)
            control.max = options.max;
    }

    if (options.multiline)
        control.rows = 3;

    Object.assign(control.style, { boxSizing: "border-box", maxWidth: "100%", width: options.type === "checkbox" ? "auto" : "100%", padding: "7px", background: "#181818", color: "#f4e2c8", border: "1px solid #5a4636", borderRadius: "4px", font: "inherit" });
    control[options.live ? "oninput" : "onchange"] = () => {
        const next = options.type === "checkbox" ? control.checked : options.type === "number" ? control.valueAsNumber : control.value;
        Promise.resolve().then(() => action(next)).catch(Editor.error);
    };
    row.append(control); parent.append(row);
    return control;
};
Editor.section = (parent, title) => {
    const section = Editor.element("section", "", { marginTop: "16px", borderTop: "1px solid #49382b", paddingTop: "8px" });
    section.append(Editor.element("h3", title, { fontSize: "15px", margin: "6px 0 12px" }));
    parent.append(section); return section;
};
Editor.error = error => {
    Editor.status.textContent = error.message || String(error);
    Editor.status.style.color = "#ffaca0";
    console.error(error);
};
//#endregion

//#region State and storage
Editor.checkpoint = () => {
    Editor.undo.push(Model.Clone(Editor.model));
    if (Editor.undo.length > 60)
        Editor.undo.shift();

    Editor.redo = [];
};
Editor.change = action => {
    const before = Model.Clone(Editor.model);
    const validation = Promise.resolve().then(() => { action(Editor.model); return Model.Validate(Editor.model); });
    return validation.then(() => {
        Editor.undo.push(before);
        if (Editor.undo.length > 60)
            Editor.undo.shift();

        Editor.redo = []; Editor.afterChange();
    }, error => { Editor.model = before; Editor.inspect(); Editor.error(error); });
};
Editor.afterChange = () => {
    Editor.undoButton.disabled = !Editor.undo.length; Editor.redoButton.disabled = !Editor.redo.length;
    Editor.scheduleRender(); Editor.saveSoon();
};
Editor.history = forward => {
    const source = forward ? Editor.redo : Editor.undo, destination = forward ? Editor.undo : Editor.redo;
    if (!source.length)
        return;

    destination.push(Model.Clone(Editor.model)); Editor.model = source.pop();
    if (!Editor.model.parts.some(part => part.id === Editor.selected))
        Editor.selected = Editor.model.parts[0].id;

    Editor.buildSidebars(); Editor.afterChange();
};
Editor.openStorage = () => new Promise((resolve, reject) => {
    const request = indexedDB.open("bpf-template-editor-prototype-v2", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("drafts");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
});
Editor.loadDraft = () => new Promise((resolve, reject) => {
    const transaction = Editor.database.transaction("drafts", "readonly");
    const request = transaction.objectStore("drafts").get("current");
    request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error);
});
Editor.saveSoon = () => {
    clearTimeout(Editor.pendingSave);
    Editor.saveStatus.textContent = "Saving prototype draft…";
    Editor.pendingSave = setTimeout(() => {
        if (!Editor.database) {
            Editor.saveStatus.textContent = "Local autosave unavailable; download JSON to keep your work.";
            return;
        }

        const transaction = Editor.database.transaction("drafts", "readwrite");
        transaction.objectStore("drafts").put(Editor.model, "current");
        transaction.oncomplete = () => Editor.saveStatus.textContent = "Prototype draft saved in this browser";
        transaction.onerror = () => Editor.saveStatus.textContent = "Autosave failed; download JSON to keep your work.";
    }, 600);
};
Editor.scheduleRender = () => {
    const epoch = ++Editor.epoch;
    Editor.status.textContent = "Updating preview…"; Editor.status.style.color = "#d8ba98";
    requestAnimationFrame(async () => {
        if (epoch !== Editor.epoch)
            return;

        const snapshot = Model.Clone(Editor.model), stage = Editor.renderer.makeCanvas();
        const result = await Editor.renderer.render(snapshot, stage, Editor.selected, Editor.guides, () => epoch !== Editor.epoch, (completed, total) => {
            if (epoch === Editor.epoch)
                Editor.status.textContent = `Loading preview assets ${completed}/${total} · first use downloads upstream images; later edits reuse them`;
        }).catch(error => {
            if (epoch === Editor.epoch)
                Editor.error(error);

            return null;
        });
        if (!result || epoch !== Editor.epoch)
            return;

        Editor.canvas.getContext("2d").drawImage(stage, 0, 0);
        Editor.lastPositions = result.positions;
        Editor.status.textContent = result.warnings.length ? result.warnings.join("\n") : `Preview ready · ${Math.round(result.milliseconds)} ms`;
        Editor.status.style.color = result.warnings.length ? "#ffc481" : "#9fdbb2";
        Editor.canvas.dataset.ready = String(epoch);
        stage.width = 1; stage.height = 1;
    });
};
//#endregion

//#region Import and export
Editor.pickFile = (accept, action) => {
    const input = Editor.element("input"); input.type = "file"; input.accept = accept;
    input.hidden = true; document.body.append(input);
    input.onchange = async () => {
        if (input.files[0])
            await action(input.files[0]).catch(Editor.error);

        input.remove();
    };
    input.oncancel = () => input.remove(); input.click();
};
Editor.readImage = async file => {
    if (file.size > 24 * 1024 * 1024)
        throw new Error(`Choose an image smaller than 24 MB.`);

    const read = () => new Promise((resolve, reject) => {
        const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = () => reject(reader.error); reader.readAsDataURL(file);
    });
    if (file.type === "image/svg+xml" || file.name.toLowerCase().endsWith(".svg")) {
        const text = await file.text(), document = new DOMParser().parseFromString(text, "image/svg+xml");
        if (document.querySelector("parsererror, script, foreignObject") || !document.documentElement || document.documentElement.localName !== "svg")
            throw new Error(`Choose an SVG containing only image shapes.`);

        for (const style of document.querySelectorAll("style")) {
            if (/(?:https?:|javascript:|data:|\/\/|@import)/i.test(style.textContent))
                throw new Error(`SVG styles cannot load external resources.`);
        }

        for (const element of document.querySelectorAll("*")) {
            for (const attribute of element.attributes) {
                if (attribute.name.toLowerCase().startsWith("on") || !attribute.name.startsWith("xmlns") && /(?:https?:|javascript:|data:|\/\/|@import)/i.test(attribute.value))
                    throw new Error(`SVG images cannot contain scripts or external resources.`);
            }
        }

        const image = await Editor.renderer.loadImage(await read());
        const canvas = Editor.element("canvas"); canvas.width = image.naturalWidth; canvas.height = image.naturalHeight;
        canvas.getContext("2d").drawImage(image, 0, 0);
        return canvas.toDataURL("image/png");
    }

    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type))
        throw new Error(`Choose PNG, JPEG, WebP or SVG.`);

    const source = await read(); await Editor.renderer.loadImage(source);
    return source;
};
Editor.upload = (part, isMask = false, scope = "variant", standalone = false) => Editor.pickFile("image/png,image/jpeg,image/webp,image/svg+xml", async file => {
    const source = await Editor.readImage(file);
    const image = await Editor.renderer.loadImage(source);
    const metadata = { filename: file.name, width: image.naturalWidth, height: image.naturalHeight, alphaBounds: Editor.renderer.alphaBounds(image) };
    await Editor.change(model => {
        const current = model.parts.find(item => item.id === part.id), id = `upload_${crypto.randomUUID()}`;
        model.assets[id] = source;
        model.assetMetadata ??= {};
        model.assetMetadata[id] = metadata;
        if (isMask)
            current.mask = id;
        else if (current.map && scope === "variant") {
            if (model.parts.filter(item => item.map === current.map).length > 1) {
                const mapId = `${current.id}_variants_${crypto.randomUUID()}`;
                model.maps[mapId] = { ...model.maps[current.map] }; current.map = mapId;
            }

            model.maps[current.map][model.preview.variant] = id;
        }
        else {
            current.asset = id; current.map = null;
        }

        if (!isMask && standalone) {
            current.alignment = "piece"; current.trimAlpha = true; current.mask = null; current.scale = 1;
            if (model.anchors[current.id])
                current.placement = { relativeTo: current.id, rect: Model.Rect(0, 0, 1, 1) };
        }
        else if (!isMask && current.alignment === "piece")
            current.trimAlpha = true;
    });
    Editor.inspect();
});
Editor.download = (name, blob) => {
    const url = URL.createObjectURL(blob), link = Editor.element("a");
    link.href = url; link.download = name; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
};
Editor.exportModel = async () => {
    const model = Model.Clone(Editor.model);
    if (Editor.portable.checked) {
        Editor.status.textContent = "Embedding template images for the JSON download…";
        const used = new Set();
        const usedMaps = new Set(model.parts.map(part => part.map).filter(Boolean));
        for (const map of Object.keys(model.maps)) {
            if (!usedMaps.has(map))
                delete model.maps[map];
        }

        for (const part of model.parts) {
            if (part.asset)
                used.add(part.asset);
            if (part.mask)
                used.add(part.mask);
            if (part.map) {
                for (const asset of Object.values(model.maps[part.map])) {
                    used.add(asset);
                }
            }
        }

        for (const id of Object.keys(model.assets)) {
            if (!used.has(id))
                delete model.assets[id];
        }

        for (const id of used) {
            if (model.assets[id].startsWith("data:"))
                continue;

            const image = await Editor.renderer.loadImage(model.assets[id]);
            const canvas = Editor.element("canvas"); canvas.width = image.naturalWidth; canvas.height = image.naturalHeight;
            canvas.getContext("2d").drawImage(image, 0, 0); model.assets[id] = canvas.toDataURL("image/png");
            canvas.width = 1; canvas.height = 1;
        }
    }

    Model.Validate(model);
    Editor.download(`${model.name.replace(/[^a-z0-9_-]/gi, "_")}.template.json`, new Blob([JSON.stringify(model, null, 2)], { type: "application/json" }));
    Editor.status.textContent = "Template JSON downloaded.";
};
Editor.exportPNG = async () => {
    const canvas = Editor.element("canvas"); canvas.width = 2000; canvas.height = 2800;
    const result = await Editor.renderer.render(Model.Clone(Editor.model), canvas);
    const blob = await new Promise(resolve => canvas.toBlob(resolve, "image/png"));
    if (!blob)
        throw new Error(`PNG export failed.`);

    Editor.download("template-preview.png", blob);
    Editor.status.textContent = result.warnings.length ? `PNG downloaded with warnings: ${result.warnings.join("; ")}` : "2000 × 2800 PNG downloaded.";
};
Editor.importJSON = () => Editor.pickFile("application/json,.json", async file => {
    if (file.size > 100 * 1024 * 1024)
        throw new Error(`Choose a template JSON smaller than 100 MB.`);

    const model = Model.Validate(JSON.parse(await file.text()));
    Editor.checkpoint(); Editor.model = model; Editor.selected = model.parts[0].id;
    Editor.buildSidebars(); Editor.afterChange();
});
Editor.showJSON = () => {
    const dialog = Editor.element("dialog", "", { width: "min(900px, 85vw)", background: "#201c19", color: "#f3dec3", border: "1px solid #78502b" });
    dialog.append(Editor.element("h2", "Template JSON"));
    const text = Editor.element("textarea"); text.readOnly = true; text.value = JSON.stringify(Editor.model, null, 2);
    text.setAttribute("aria-label", "Template JSON"); Object.assign(text.style, { width: "100%", height: "65vh", boxSizing: "border-box" }); dialog.append(text);
    Editor.button("Close", () => dialog.close(), dialog);
    dialog.onclose = () => dialog.remove(); document.body.append(dialog); dialog.showModal();
};
//#endregion

//#region Layer list and preview inputs
Editor.select = id => { Editor.selected = id; Editor.layerList(); Editor.inspect(); Editor.scheduleRender(); };
Editor.layerList = () => {
    Editor.layers.replaceChildren();
    for (const part of [...Editor.model.parts].reverse()) {
        const button = Editor.button(`${part.visible ? "●" : "○"} ${part.name}`, () => Editor.select(part.id), Editor.layers);
        Object.assign(button.style, { width: "calc(100% - 6px)", textAlign: "left", background: part.id === Editor.selected ? "#78481f" : "#30251d" });
        button.setAttribute("aria-pressed", String(part.id === Editor.selected)); button.dataset.part = part.id;
    }
};
Editor.previewInputs = () => {
    Editor.samples.replaceChildren();
    Editor.field(Editor.samples, "Template name", Editor.model.name, value => Editor.change(model => model.name = value));
    Editor.field(Editor.samples, "Preview color / image variant", Editor.model.preview.variant, value => Editor.change(model => {
        model.preview.variant = value; model.preview.accentColors = [value];
    }).then(() => Editor.buildSidebars()), { choices: Model.Variants.map(code => [code, ({ W: "White", U: "Blue", B: "Black", R: "Red", G: "Green", M: "Multicolor", A: "Artifact", L: "Land", C: "Colorless / Eldrazi", V: "Vehicle" })[code]]) });
    Editor.field(Editor.samples, "First accent color", Editor.model.preview.accentColors[0], value => Editor.change(model => model.preview.accentColors[0] = value), { choices: Model.Variants.map(code => [code, code]) });
    Editor.field(Editor.samples, "Second accent color", Editor.model.preview.accentColors[1] || "", value => Editor.change(model => {
        const first = "WUBRG".includes(model.preview.accentColors[0]) ? model.preview.accentColors[0] : "U";
        model.preview.accentColors = value ? [first, value] : [model.preview.variant];
    }).then(Editor.previewInputs), { choices: [["", "None"], ...[..."WUBRG"].map(code => [code, code])] });
    Editor.field(Editor.samples, "Legendary", Editor.model.preview.legendary, value => Editor.change(model => model.preview.legendary = value), { type: "checkbox" });
    for (const [key, label] of [["name", "Real name"], ["nickname", "Nickname"], ["mana", "Mana cost"], ["type", "Type line"], ["rules", "Rules text"], ["flavor", "Flavor text"], ["pt", "Power / toughness"], ["credit", "Footer credit"]]) {
        Editor.field(Editor.samples, label, Editor.model.preview[key], value => Editor.change(model => model.preview[key] = value), { multiline: ["rules", "flavor"].includes(key), live: true });
    }

    Editor.button("Upload preview artwork", () => Editor.upload(Editor.model.parts.find(part => part.kind === "artwork"), false, "all"), Editor.samples);
    Editor.field(Editor.samples, "Artwork covers the whole card", Editor.model.parts.find(part => part.kind === "artwork").placement.relativeTo === "Canvas", value => Editor.change(model => model.parts.find(part => part.kind === "artwork").placement = { relativeTo: value ? "Canvas" : "ArtWindow", rect: Model.Rect(0, 0, 1, 1) }), { type: "checkbox" });
    const palette = Editor.section(Editor.samples, "Pinline gradient palette");
    for (const code of "WUBRG") {
        Editor.field(palette, `${code} accent color`, Editor.model.palette[code], value => Editor.change(model => model.palette[code] = value), { type: "color" });
    }
};
Editor.move = delta => Editor.change(model => {
    const index = model.parts.findIndex(part => part.id === Editor.selected), part = model.parts[index];
    const target = index + delta;
    if (target < 0 || target >= model.parts.length)
        return;

    if ((["text", "mana", "divider"].includes(part.kind)) !== (["text", "mana", "divider"].includes(model.parts[target].kind)))
        throw new Error(`Text and symbols stay above the frame composite. Move within the same group.`);

    model.parts.splice(index, 1); model.parts.splice(target, 0, part);
}).then(Editor.layerList);
Editor.addPart = () => {
    const dialog = Editor.element("dialog", "", { background: "#201c19", color: "#f3dec3", width: "360px" });
    dialog.append(Editor.element("h2", "Add a layer"));
    const name = Editor.field(dialog, "Layer name", "New image", () => {});
    const kind = Editor.field(dialog, "Layer kind", "image", () => {}, { choices: [["image", "Image"], ["text", "Text"], ["fill", "Solid fill"], ["divider", "Rules divider"]] });
    const anchor = Editor.field(dialog, "Default size / anchor", "PT_Box", () => {}, { choices: ["Canvas", ...Object.keys(Editor.model.anchors)].map(id => [id, id]) });
    Editor.button("Add layer", async () => {
        const id = `part_${crypto.randomUUID()}`;
        await Editor.change(model => {
            const part = Model.NewPart(id, kind.value, anchor.value); part.name = name.value || "New layer";
            if (part.kind === "text") {
                part.field = "rules"; part.style = { font: "mplantin", size: 46, minSize: 24, color: "#000000", outline: 0, outlineColor: "#ffffff", align: "left", lineHeight: 1.1, oneLine: false };
            }

            if (["text", "divider"].includes(part.kind))
                model.parts.push(part);
            else
                model.parts.splice(model.parts.findIndex(item => ["text", "mana", "divider"].includes(item.kind)), 0, part);
        });
        dialog.close(); Editor.select(id);
    }, dialog);
    Editor.button("Cancel", () => dialog.close(), dialog); dialog.onclose = () => dialog.remove(); document.body.append(dialog); dialog.showModal();
};
Editor.buildSidebars = () => { Editor.layerList(); Editor.previewInputs(); Editor.inspect(); };
//#endregion

//#region Inspector
Editor.inspect = () => {
    Editor.inspector.replaceChildren();
    const part = Editor.model.parts.find(item => item.id === Editor.selected);
    if (!part)
        return;

    Editor.inspector.append(Editor.element("h2", part.name, { fontSize: "20px" }));
    const update = (key, value) => Editor.change(model => model.parts.find(item => item.id === part.id)[key] = value);
    Editor.field(Editor.inspector, "Layer name", part.name, value => update("name", value).then(Editor.layerList));
    Editor.field(Editor.inspector, "Visible", part.visible, value => update("visible", value).then(Editor.layerList), { type: "checkbox" });
    Editor.field(Editor.inspector, "Show when", part.when, value => update("when", value), { choices: [["always", "Always"], ["legendary", "Legendary"], ["nickname", "Has nickname"], ["pt", "Has power/toughness"], ["rulesAndFlavor", "Has rules and flavor"]] });
    Editor.field(Editor.inspector, "Opacity", part.opacity, value => update("opacity", value), { type: "number", min: 0, max: 1 });
    Editor.button("Move toward front", () => Editor.move(1), Editor.inspector);
    Editor.button("Move toward back", () => Editor.move(-1), Editor.inspector);
    Editor.button("Duplicate", async () => {
        const id = `part_${crypto.randomUUID()}`;
        await Editor.change(model => {
            const index = model.parts.findIndex(item => item.id === part.id), duplicate = structuredClone(model.parts[index]);
            duplicate.id = id; duplicate.name += " copy";
            if (duplicate.map) {
                const mapId = `map_${crypto.randomUUID()}`;
                model.maps[mapId] = { ...model.maps[duplicate.map] }; duplicate.map = mapId;
            }

            model.parts.splice(index + 1, 0, duplicate);
        });
        Editor.select(id);
    }, Editor.inspector);
    if (part.kind !== "artwork")
        Editor.button("Delete layer", async () => {
            await Editor.change(model => model.parts = model.parts.filter(item => item.id !== part.id));
            Editor.selected = Editor.model.parts[0].id; Editor.layerList(); Editor.inspect();
        }, Editor.inspector);

    const layout = Editor.section(Editor.inspector, "Placement");
    Editor.field(layout, "Relative to", part.placement.relativeTo, value => Editor.change(model => model.parts.find(item => item.id === part.id).placement.relativeTo = value).then(Editor.inspect), { choices: ["Canvas", ...Object.keys(Editor.model.anchors)].map(id => [id, id]) });
    Editor.inspector.append(Editor.element("p", "Positions and text-box sizes are fractions of the chosen anchor. Drag the selected region in the preview to move it.", { fontSize: "12px", color: "#c3a88d" }));
    for (const key of ["x", "y", "width", "height"]) {
        Editor.field(layout, `Region ${key}`, part.placement.rect[key], value => Editor.change(model => model.parts.find(item => item.id === part.id).placement.rect[key] = value), { type: "number" });
    }

    const anchorId = part.placement.relativeTo;
    if (anchorId !== "Canvas") {
        const anchor = Editor.section(Editor.inspector, `Shared anchor: ${anchorId}`);
        anchor.append(Editor.element("p", "Moving this anchor also moves its text and related symbols.", { fontSize: "12px" }));
        for (const key of ["x", "y", "width", "height"]) {
            Editor.field(anchor, `Anchor ${key}`, Editor.model.anchors[anchorId].rect[key], value => Editor.change(model => model.anchors[anchorId].rect[key] = value), { type: "number" });
        }
    }

    if (["image", "artwork", "divider"].includes(part.kind)) {
        const images = Editor.section(Editor.inspector, "Image and mask");
        Editor.field(images, "Image alignment", part.alignment, value => Editor.change(model => {
            const current = model.parts.find(item => item.id === part.id); current.alignment = value;
            current.trimAlpha = value === "piece";
            if (value === "full-card")
                current.placement = { relativeTo: "Canvas", rect: Model.Rect(0, 0, 1, 1) };
            else {
                current.mask = null;
                if (model.anchors[current.id])
                    current.placement = { relativeTo: current.id, rect: Model.Rect(0, 0, 1, 1) };
            }
        }).then(Editor.inspect), { choices: [["piece", "Standalone piece · fit default region"], ["full-card", "Full-card alignment · preserve padding"]] });
        if (part.alignment === "piece") {
            Editor.field(images, "Trim nearly transparent padding (alpha < 2)", part.trimAlpha, value => update("trimAlpha", value), { type: "checkbox" });
            Editor.field(images, "Scale from default fit", part.scale, value => update("scale", value), { type: "number", min: part.kind === "artwork" ? 1 : 0.01, max: 10 });
        }

        const source = Editor.renderer.sourceFor(Editor.model, part);
        if (source) {
            const thumbnail = Editor.element("img"); thumbnail.src = source; thumbnail.alt = `${part.name} source image`;
            Object.assign(thumbnail.style, { maxWidth: "100%", maxHeight: "110px", objectFit: "contain", background: "#555555" }); images.append(thumbnail);
            images.append(Editor.element("p", source.startsWith("data:") ? "Uploaded image stored in the template." : source, { fontSize: "11px", overflowWrap: "anywhere" }));
            const assetId = part.map ? Editor.model.maps[part.map][Editor.model.preview.variant] || Editor.model.maps[part.map].C : part.asset;
            const metadata = Editor.model.assetMetadata?.[assetId];
            if (metadata)
                images.append(Editor.element("p", `${metadata.filename} · ${metadata.width} × ${metadata.height} · ${metadata.alphaBounds ? `visible bounds ${metadata.alphaBounds.width} × ${metadata.alphaBounds.height}` : "fully transparent"}`, { fontSize: "12px" }));
        }

        Editor.button(part.map ? `Replace ${Editor.model.preview.variant} variant image` : "Upload image", () => Editor.upload(part), images);
        if (["Rules", "Title", "Type", "PT_Box", "Crown", "Subtitle"].includes(part.id))
            Editor.button("Upload standalone piece (all colors)", () => Editor.upload(part, false, "all", true), images);
        if (part.map)
            Editor.button("Use one uploaded image for all colors", () => Editor.upload(part, false, "all"), images);

        Editor.button("Remove image", () => Editor.change(model => {
            const current = model.parts.find(item => item.id === part.id); current.map = null; current.asset = null;
        }).then(Editor.inspect), images);
        Editor.field(images, "Existing image set", part.map || "", value => Editor.change(model => {
            const current = model.parts.find(item => item.id === part.id); current.map = value || null;
            if (value === "FrameImages") {
                current.alignment = "full-card"; current.trimAlpha = false;
                current.placement = { relativeTo: "Canvas", rect: Model.Rect(0, 0, 1, 1) };
                if (model.assets[`Mask_${current.id}`])
                    current.mask = `Mask_${current.id}`;
            }
        }).then(Editor.inspect), { choices: [["", "Single uploaded image"], ...Object.keys(Editor.model.maps).map(id => [id, id])] });
        Editor.field(images, "Mask (full-card coordinates)", part.mask || "", value => update("mask", value || null), { choices: [["", "No mask"], ...Object.keys(Editor.model.assets).filter(id => id.startsWith("Mask_") || id.startsWith("upload_")).map(id => [id, id])] });
        images.append(Editor.element("p", "Masks use transparency: opaque pixels keep the image; transparent pixels remove it. Their full-card padding is preserved.", { fontSize: "12px", color: "#c3a88d" }));
        Editor.button("Upload full-card mask", () => Editor.upload(part, true), images);
        Editor.field(images, "Color treatment", part.treatment, value => update("treatment", value), { choices: [["none", "Native image"], ["pinline", "Two-color pinline gradient"], ["crown", "Two-color crown image blend"]] });
        Editor.field(images, "Compositing", part.blend, value => update("blend", value), { choices: [["source-over", "Normal"], ["destination-out", "Erase frame only (cutout)"]] });
    }

    if (["fill", "divider"].includes(part.kind))
        Editor.field(Editor.inspector, "Fill color", part.color, value => update("color", value), { type: "color" });

    if (part.kind === "text") {
        const text = Editor.section(Editor.inspector, "Text");
        if (["rules", "flavor"].includes(part.field)) {
            Editor.field(text, "Share rules/flavor flow", part.flow === "rules", value => update("flow", value ? "rules" : null), { type: "checkbox" });
            text.append(Editor.element("p", "Shared flow uses the rules region and positions flavor after the measured rules. Turn it off to position this text independently.", { fontSize: "12px" }));
        }

        Editor.field(text, "Card field", part.field, value => update("field", value), { choices: ["displayName", "name", "nickname", "type", "rules", "flavor", "pt", "credit"].map(field => [field, field]) });
        const style = (key, value) => Editor.change(model => model.parts.find(item => item.id === part.id).style[key] = value);
        Editor.field(text, "Font", part.style.font, value => style("font", value), { choices: ["belerenb", "belerenbsc", "mplantin", "mplantini", "serif", "sans-serif"].map(font => [font, font]) });
        Editor.field(text, "Font size", part.style.size, value => style("size", value), { type: "number", min: 1, max: 200, step: 0.5 });
        Editor.field(text, "Minimum fitted size", part.style.minSize, value => style("minSize", value), { type: "number", min: 1, step: 0.5 });
        Editor.field(text, "Text color", part.style.color, value => style("color", value), { type: "color" });
        Editor.field(text, "Outline width", part.style.outline, value => style("outline", value), { type: "number", min: 0, max: 20 });
        Editor.field(text, "Outline color", part.style.outlineColor, value => style("outlineColor", value), { type: "color" });
        Editor.field(text, "Alignment", part.style.align, value => style("align", value), { choices: ["left", "center", "right"].map(align => [align, align]) });
        Editor.field(text, "Line height", part.style.lineHeight, value => style("lineHeight", value), { type: "number", min: 0.5, max: 3 });
        Editor.field(text, "Single line", part.style.oneLine, value => style("oneLine", value), { type: "checkbox" });
    }

    if (part.kind === "mana")
        Editor.field(Editor.inspector, "Mana symbol size", part.symbolSize, value => update("symbolSize", value), { type: "number", min: 1 });

    if (part.kind === "artwork") {
        for (const axis of ["x", "y"]) {
            Editor.field(Editor.inspector, `Artwork focus ${axis}`, part.focus?.[axis] ?? 0.5, value => Editor.change(model => {
                const current = model.parts.find(item => item.id === part.id);
                current.focus ??= { x: 0.5, y: 0.5 }; current.focus[axis] = value;
            }), { type: "number", min: 0, max: 1 });
        }
    }
};
//#endregion

//#region Canvas interaction
Editor.pointer = event => {
    const rect = Editor.canvas.getBoundingClientRect();
    return { x: (event.clientX - rect.left) * Model.Width / rect.width, y: (event.clientY - rect.top) * Model.Height / rect.height };
};
Editor.installDrag = () => {
    let drag = null;
    Editor.canvas.onpointerdown = event => {
        const point = Editor.pointer(event), selected = Editor.model.parts.find(part => part.id === Editor.selected);
        let part = selected, box = Editor.lastPositions.get(part.id);
        if (!box || point.x < box.x || point.x > box.x + box.width || point.y < box.y || point.y > box.y + box.height) {
            part = [...Editor.model.parts].reverse().find(item => {
                const rect = Editor.lastPositions.get(item.id);
                return item.alignment !== "full-card" && rect && point.x >= rect.x && point.x <= rect.x + rect.width && point.y >= rect.y && point.y <= rect.y + rect.height;
            });
        }

        if (!part)
            return;

        Editor.select(part.id); Editor.checkpoint();
        drag = { id: part.id, point, original: { ...part.placement.rect }, anchor: Model.ResolveAnchor(Editor.model, part.placement.relativeTo) };
        Editor.canvas.setPointerCapture(event.pointerId); event.preventDefault();
    };
    Editor.canvas.onpointermove = event => {
        if (!drag)
            return;

        const point = Editor.pointer(event), part = Editor.model.parts.find(item => item.id === drag.id);
        part.placement.rect.x = Math.max(-5, Math.min(5, drag.original.x + (point.x - drag.point.x) / drag.anchor.width));
        part.placement.rect.y = Math.max(-5, Math.min(5, drag.original.y + (point.y - drag.point.y) / drag.anchor.height));
        Editor.scheduleRender();
    };
    const end = () => {
        if (!drag)
            return;

        drag = null; Editor.inspect(); Editor.afterChange();
    };
    Editor.canvas.onpointerup = end; Editor.canvas.onpointercancel = end;
};
//#endregion

//#region Setup
Editor.start = async () => {
    Object.assign(document.body.style, { margin: "0", background: "#151310", color: "#f4e1c4", font: "14px system-ui, sans-serif" });
    const header = Editor.element("header", "", { padding: "12px 18px", borderBottom: "1px solid #69492e" });
    header.append(Editor.element("h1", "BulkProxyForge · Template Editor Prototype", { margin: "0 0 8px", fontSize: "22px" }));
    header.append(Editor.element("p", "Separate prototype · fixed 5:7 card · production decks are untouched", { margin: "0 0 10px", color: "#baa68e" }));
    const toolbar = Editor.element("nav"); header.append(toolbar);
    Editor.button("Import template JSON", Editor.importJSON, toolbar);
    Editor.button("Download template JSON", Editor.exportModel, toolbar);
    Editor.button("Download preview PNG", Editor.exportPNG, toolbar);
    Editor.button("View JSON", Editor.showJSON, toolbar);
    Editor.button("Retry preview", () => Editor.scheduleRender(), toolbar);
    Editor.undoButton = Editor.button("Undo", () => Editor.history(false), toolbar); Editor.undoButton.disabled = true;
    Editor.redoButton = Editor.button("Redo", () => Editor.history(true), toolbar); Editor.redoButton.disabled = true;
    Editor.button("Reset to M15", async () => {
        const model = Model.Validate(await (await fetch("/default-template.json")).json());
        Editor.checkpoint(); Editor.model = model; Editor.selected = "TitleText"; Editor.buildSidebars(); Editor.afterChange();
    }, toolbar);
    Editor.portable = Editor.field(toolbar, "Embed all template images in downloaded JSON (larger file)", false, () => {}, { type: "checkbox" });
    Editor.saveStatus = Editor.element("div", "", { color: "#baa68e", fontSize: "12px" }); header.append(Editor.saveStatus); document.body.append(header);
    Editor.status = Editor.element("pre", "Loading template…", { whiteSpace: "pre-wrap", padding: "8px 18px", margin: "0", font: "13px system-ui", color: "#d8ba98" });
    Editor.status.setAttribute("role", "status"); document.body.append(Editor.status);
    const main = Editor.element("main", "", { display: "flex", gap: "14px", padding: "0 16px 20px", alignItems: "flex-start", flexWrap: "wrap" });
    const left = Editor.element("aside", "", { width: "240px", flex: "0 0 240px" });
    left.append(Editor.element("h2", "Layers", { fontSize: "18px" }));
    left.append(Editor.element("p", "Front at top. Text/symbols stay above frame images.", { fontSize: "12px", color: "#baa68e" }));
    Editor.button("Add layer", Editor.addPart, left);
    Editor.layers = Editor.element("div", "", { maxHeight: "370px", overflow: "auto" }); left.append(Editor.layers);
    left.append(Editor.element("h2", "Preview card", { fontSize: "18px" })); Editor.samples = Editor.element("section"); left.append(Editor.samples);
    const center = Editor.element("section", "", { flex: "1 1 350px", minWidth: "280px", maxWidth: "650px" });
    Editor.field(center, "Show placement guides", true, value => { Editor.guides = value; Editor.scheduleRender(); }, { type: "checkbox" });
    Editor.canvas = Editor.element("canvas"); Editor.canvas.width = Model.Width; Editor.canvas.height = Model.Height;
    Editor.canvas.setAttribute("aria-label", "Live card template preview"); Editor.canvas.setAttribute("role", "img");
    Object.assign(Editor.canvas.style, { width: "100%", display: "block", touchAction: "none", cursor: "move", border: "1px solid #755336" }); center.append(Editor.canvas);
    Editor.inspector = Editor.element("aside", "", { width: "290px", flex: "0 0 290px" });
    main.append(left, center, Editor.inspector); document.body.append(main);
    const fitPreview = () => {
        Editor.canvas.style.width = `${Math.min(center.clientWidth - 2, Math.max(300, window.innerHeight - 290) * 5 / 7)}px`;
        center.style.position = window.innerWidth > 1100 ? "sticky" : "static";
        center.style.top = "12px";
    };
    window.addEventListener("resize", fitPreview); fitPreview();
    Editor.model = Model.Validate(await (await fetch("/default-template.json")).json());
    Editor.database = await Editor.openStorage().catch(error => { Editor.saveStatus.textContent = `Autosave unavailable: ${error.message}`; return null; });
    if (Editor.database) {
        const saved = await Editor.loadDraft().catch(error => { Editor.error(error); return null; });
        if (saved)
            Editor.model = await Promise.resolve().then(() => Model.Validate(saved)).catch(error => { Editor.error(error); return Editor.model; });
    }

    Editor.buildSidebars(); Editor.installDrag(); Editor.scheduleRender();
    document.addEventListener("keydown", event => {
        if (event.target.matches("input, textarea, select"))
            return;

        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
            event.preventDefault(); Editor.history(event.shiftKey);
        }
    });
    window.TemplateEditor = Editor;
};
Editor.start().catch(error => {
    if (Editor.status)
        Editor.error(error);
    else
        document.body.append(Editor.element("p", error.message));
});
//#endregion