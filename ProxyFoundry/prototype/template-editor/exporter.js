"use strict";

import { Model } from "./model.js";
import { Renderer } from "./renderer.js";
import { Workflow } from "./workflow.js";

export const Exporter = {};
Exporter.Rect = rect => ({ x: rect.x / Model.Width, y: rect.y / Model.Height, width: rect.width / Model.Width, height: rect.height / Model.Height });
Exporter.Portable = async (model, progress = () => {}) => {
    const result = Model.Clone(model), used = new Set();
    result.parts = result.parts.map(part => {
        if (part.kind === "artwork")
            return { ...part, asset: null, map: null };

        if (part.asset)
            used.add(part.asset);

        if (part.mask)
            used.add(part.mask);

        if (part.map) {
            for (const asset of Object.values(result.maps[part.map])) {
                used.add(asset);
            }
        }

        return part;
    });
    result.assets = {}; let count = 0;
    for (const id of used) {
        const source = model.assets[id];
        if (source.startsWith("data:"))
            result.assets[id] = source;
        else {
            const blob = await (await fetch(source)).blob();
            result.assets[id] = await new Promise((resolve, reject) => {
                const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = () => reject(reader.error); reader.readAsDataURL(blob);
            });
        }

        progress(++count, used.size); await new Promise(resolve => setTimeout(resolve, 0));
    }

    const maps = new Set(result.parts.map(part => part.map).filter(Boolean));
    result.maps = Object.fromEntries(Object.entries(result.maps).filter(([id]) => maps.has(id)));
    result.assetMetadata = Object.fromEntries(Object.entries(result.assetMetadata || {}).filter(([id]) => used.has(id)));
    return Model.Validate(result);
};
Exporter.Build = async (model, progress = () => {}) => {
    Model.Validate(model);
    const missing = Workflow.Check(model);
    if (missing.length)
        throw new Error(missing.join("\n"));

    const unsupported = model.parts.filter(part => part.visible && ["Watermark", "FooterText"].includes(part.id) && part.id === "Watermark" && (part.asset || part.map));
    if (unsupported.length)
        throw new Error(`Watermark exporting is not supported yet. Remove it before exporting.`);

    const source = await Exporter.Portable(model), sources = { ...source.assets };
    const renderer = new Renderer(), layers = [], text = {}, bindings = {}, textRules = {};
    const sourceIds = new Map(Object.entries(sources).map(([id, image]) => [image, id]));
    const register = image => {
        if (!sourceIds.has(image)) {
            const id = `baked_${crypto.randomUUID()}`; sourceIds.set(image, id); sources[id] = image;
        }

        return sourceIds.get(image);
    };
    const imageParts = model.parts.filter(part => part.visible && ["image", "fill"].includes(part.kind) && part.id !== "SetSymbol");
    let count = 0;
    for (const part of imageParts) {
        if (!part.asset && !part.map && !part.mask && part.kind !== "fill")
            continue;

        const layer = { name: part.name, role: part.id, when: part.when, mode: part.blend, images: {} };
        const codes = part.map ? Model.Variants : ["C"];
        const options = codes.map(code => ({ key: code, variant: code, accents: [code] }));
        if (["pinline", "crown"].includes(part.treatment)) {
            for (let first = 0; first < 5; first++) {
                for (let second = first + 1; second < 5; second++) {
                    const colors = ["WUBRG"[first], "WUBRG"[second]];
                    options.push({ key: [...colors].sort().join(""), variant: "M", accents: colors });
                }
            }
        }

        const baked = new Map();
        for (const option of options) {
            const nativeSheet = part.alignment === "full-card" && JSON.stringify(part.placement.rect) === JSON.stringify(Model.Rect(0, 0, 1, 1)) && part.placement.relativeTo === "Canvas" && option.accents.length === 1 && part.blend === "source-over" && part.kind === "image";
            if (nativeSheet) {
                const asset = part.map ? model.maps[part.map][option.variant] || model.maps[part.map].C : part.asset;
                layer.images[option.key] = { asset, mask: part.mask || null, bounds: { x: 0, y: 0, width: 1, height: 1 } };
                continue;
            }

            const signature = JSON.stringify([renderer.sourceFor(model, part, option.variant), part.treatment === "crown" ? option.accents.map(code => renderer.sourceFor(model, part, code)) : part.treatment === "pinline" ? option.accents : []]);
            if (!baked.has(signature)) {
                const snapshot = Model.Clone(model);
                snapshot.parts = snapshot.parts.filter(item => item.kind === "artwork" || item.id === part.id);
                snapshot.parts.forEach(item => { item.visible = item.kind !== "artwork"; item.when = "always"; if (item.id === part.id) { item.blend = "source-over"; item.opacity = 1; } });
                snapshot.preview.variant = option.variant; snapshot.preview.accentColors = option.accents;
                const canvas = renderer.makeCanvas(2000, 2800);
                await renderer.render(snapshot, canvas);
                const image = renderer.frameCache;
                const context = image.getContext("2d", { willReadFrequently: true });
                const bounds = Model.AlphaBounds(context.getImageData(0, 0, image.width, image.height).data, image.width, image.height);
                if (!bounds)
                    throw new Error(`${part.name} has no visible pixels.`);

                const crop = renderer.makeCanvas(bounds.width, bounds.height);
                crop.getContext("2d").drawImage(image, bounds.x, bounds.y, bounds.width, bounds.height, 0, 0, bounds.width, bounds.height);
                baked.set(signature, { asset: register(crop.toDataURL("image/png")), mask: null, bounds: { x: bounds.x / image.width, y: bounds.y / image.height, width: bounds.width / image.width, height: bounds.height / image.height } });
                canvas.width = 1; crop.width = 1;
            }

            layer.images[option.key] = baked.get(signature);
            progress(`${part.name} · ${option.key}`, ++count); await new Promise(resolve => setTimeout(resolve, 0));
        }

        layer.opacity = part.opacity * 100; layers.push(layer);
    }

    for (const part of model.parts.filter(item => item.visible && ["text", "mana"].includes(item.kind))) {
        const field = part.kind === "mana" ? "mana" : ({ displayName: "title", name: "subtitle", type: "type", rules: "rules", flavor: "flavor", pt: "pt", nickname: "nickname", credit: "credit" })[part.field];
        if (!field)
            throw new Error(`Unsupported text field: ${part.name}`);

        const slot = ({ TitleText: "title", TypeText: "type", RulesText: "rules", FlavorText: "flavor", PTText: "pt", SubtitleText: "subtitle", ManaCost: "mana" })[part.id] || part.id;
        const rect = Exporter.Rect(Model.ResolvePart(model, part));
        const style = part.style || { font: "belerenb", size: part.symbolSize, color: "#000000", align: "right", oneLine: true, outline: 0, outlineColor: "#ffffff" };
        text[slot] = { ...rect, name: part.name, text: "", font: style.font === "serif" ? "mplantin" : style.font === "sans-serif" ? "gothammedium" : style.font, size: style.size / Model.Height, minSize: style.minSize / Model.Height || 0.015, color: style.color, align: style.align, oneLine: Boolean(style.oneLine), noVerticalCenter: true, lineSpacing: (style.lineHeight || 1.1) - 1, outlineWidth: style.outline / Model.Height, outlineColor: style.outlineColor, manaCost: part.kind === "mana", italic: style.font === "mplantini" };
        bindings[slot] = field;
        textRules[slot] = { when: part.when, flow: part.flow || null, reserveFor: part.reserveFor || null, opacity: part.opacity };
    }

    if (!text.title || !text.type)
        throw new Error(`Title and type text must be enabled before exporting.`);

    const symbol = model.parts.find(part => part.id === "SetSymbol" && part.visible);
    const art = model.parts.find(part => part.kind === "artwork");
    const base = await (await fetch("/native-base.json")).json();
    const data = { ...base, width: 2010, height: 2814, version: "m15Regular", frames: [], text, artBounds: Exporter.Rect(Model.ResolvePart(model, art)), setSymbolBounds: symbol ? { ...Exporter.Rect(Model.ResolvePart(model, symbol)), horizontal: "left", vertical: "top" } : { x: 0, y: 0, width: 0.0001, height: 0.0001 }, manaSymbols: [], watermarkOpacity: 0 };
    const regions = Object.fromEntries(Object.entries(bindings).map(([slot, field]) => [slot, { field: ["title", "type", "mana", "rules", "flavor", "pt"].includes(field) ? field : `native:${slot}`, geometry: "fixed", offset: {} }]));
    source.assets = {}; source.assetTable = "visualRecipe.sources";
    const result = { format: "bulk-proxy-forge-template", schemaVersion: 3, name: model.name, groups: ["standard", "legendary", "land", "legendary-land", "basic-land"], baseGroup: "standard", legendary: true, data, regions, visualRecipe: { version: 1, sources, layers, bindings, textRules, divider: model.parts.some(part => part.visible && part.kind === "divider"), ptBounds: model.anchors.PT_Box ? Exporter.Rect(Model.ResolveAnchor(model, "PT_Box")) : null }, editorSource: source };
    if (Object.keys(sources).length > 200)
        throw new Error("This template exceeds the app's 200-image limit. Remove unused parts or share color images.");
    const size = new Blob([JSON.stringify(result)]).size;
    if (size > 64 * 1024 * 1024)
        throw new Error(`This template exceeds the app's 64 MB import limit. Reduce uploaded image sizes.`);

    return result;
};