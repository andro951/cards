"use strict";

import { Model } from "./model.js";

export const Workflow = {};
Workflow.ColorNames = { W: "White", U: "Blue", B: "Black", R: "Red", G: "Green", M: "Multicolor", A: "Artifact", L: "Land", C: "Colorless", V: "Vehicle" };
Workflow.SheetParts = ["Border", "Frame", "Rules", "Title", "Type", "Pinline"];
Workflow.Color = (card) => card.variant;
Workflow.Coverage = model => model.parts.filter(part => part.visible && part.colorAssignments && !part.colorAssignments.reuse).flatMap(part => Model.Variants.filter(code => !part.colorAssignments.assigned.includes(code)).map(code => `${part.name}: assign ${Workflow.ColorNames[code]} or choose shared fallback.`));
Workflow.Check = model => {
    const errors = [...Workflow.Coverage(model)];
    for (const part of model.parts.filter(part => part.visible)) {
        if (part.kind === "image" && part.id !== "SetSymbol" && !part.asset && !part.map && !part.mask)
            errors.push(`${part.name}: upload an image or hide this part.`);

        if (part.id === "Watermark" && (part.asset || part.map))
            errors.push(`Watermarks are not supported by this export yet. Hide the watermark.`);

        if (part.kind === "divider" && part.asset)
            errors.push(`Custom divider images are not supported yet. Use the automatic divider.`);

        if (part.kind === "artwork" && (part.opacity !== 1 || part.scale !== 1 || part.focus && (part.focus.x !== .5 || part.focus.y !== .5)))
            errors.push(`Use centered artwork at its default scale and opacity; artwork positioning is chosen per card in BulkProxyForge.`);
    }

    for (const id of ["TitleText", "TypeText"]) {
        if (!model.parts.find(part => part.id === id)?.visible)
            errors.push(`Enable the ${id === "TitleText" ? "title" : "type"} text before exporting.`);
    }

    const rules = model.parts.find(part => part.field === "rules" && part.visible && part.flow === "rules"), flavor = model.parts.find(part => part.field === "flavor" && part.visible && part.flow === "rules");
    if (rules && flavor && (flavor.style.font !== "mplantini" || ["color", "align", "outline", "outlineColor", "lineHeight"].some(key => flavor.style[key] !== rules.style[key])))
        errors.push(`Shared flavor flow uses Plantin italic and the rules text's color, alignment and outline. Match those settings or turn off shared flow to position flavor separately.`);

    return errors;
};
Workflow.GuessColor = filename => {
    const words = filename.toLowerCase().replace(/\.[^.]+$/, "").split(/[^a-z]+/);
    return Model.Variants.find(code => words.includes(code.toLowerCase()) || words.includes(Workflow.ColorNames[code].toLowerCase())) || null;
};
Workflow.Assign = (model, part, source, filename, code = null) => {
    delete part.colorSource;
    const id = `upload_${crypto.randomUUID()}`;
    model.assets[id] = source; model.assetMetadata ??= {}; model.assetMetadata[id] = { filename };
    if (!code) {
        part.asset = id; part.map = null; delete part.colorAssignments;
        return id;
    }

    if (!part.colorAssignments) {
        part.map = `colors_${crypto.randomUUID()}`;
        model.maps[part.map] = { C: id };
        part.asset = null; part.colorAssignments = { assigned: [], reuse: false };
    }
    else if (model.parts.some(other => other !== part && other.map === part.map)) {
        const map = `colors_${crypto.randomUUID()}`;
        model.maps[map] = { ...model.maps[part.map] }; part.map = map;
    }

    model.maps[part.map][code] = id;
    if (!part.colorAssignments.assigned.includes(code))
        part.colorAssignments.assigned.push(code);

    return id;
};
Workflow.Prune = model => {
    const used = new Set(model.parts.flatMap(part => [part.asset, part.mask, ...Object.values(model.maps[part.map] || {})]).filter(Boolean));
    for (const id of Object.keys(model.assets)) {
        if (!used.has(id) && !id.startsWith("Mask_")) {
            delete model.assets[id];
            if (model.assetMetadata)
                delete model.assetMetadata[id];
        }
    }

    const maps = new Set(model.parts.map(part => part.map).filter(Boolean));
    for (const id of Object.keys(model.maps)) {
        if (!maps.has(id))
            delete model.maps[id];
    }
};
Workflow.SetSheet = (model, asset, useMasks) => {
    for (const id of Workflow.SheetParts) {
        const part = model.parts.find(item => item.id === id);
        part.visible = useMasks || id === "Frame";
        part.asset = asset; part.map = null; part.mask = useMasks ? `Mask_${id}` : null;
        delete part.colorSource; delete part.colorAssignments;
        part.alignment = "full-card"; part.trimAlpha = false;
        part.placement = { relativeTo: "Canvas", rect: Model.Rect(0, 0, 1, 1) };
        part.treatment = "none";
    }
};
Workflow.MoveRegion = (model, part, next) => {
    const anchor = model.anchors[part.id];
    if (anchor) {
        const before = Model.ResolveAnchor(model, part.id);
        const parent = Model.ResolveAnchor(model, anchor.relativeTo);
        anchor.rect = Model.Rect((next.x - parent.x) / parent.width, (next.y - parent.y) / parent.height, next.width / parent.width, next.height / parent.height);
        if (part.alignment === "full-card") {
            //A masked sheet is moved by the same transform as its associated text region.
            const box = Model.ResolvePart(model, part);
            const sx = next.width / before.width, sy = next.height / before.height;
            part.placement = { relativeTo: "Canvas", rect: Model.Rect((next.x + (box.x - before.x) * sx) / Model.Width, (next.y + (box.y - before.y) * sy) / Model.Height, box.width * sx / Model.Width, box.height * sy / Model.Height) };
        }

        return;
    }

    const parent = Model.ResolveAnchor(model, part.placement.relativeTo);
    part.placement.rect = Model.Rect((next.x - parent.x) / parent.width, (next.y - parent.y) / parent.height, next.width / parent.width, next.height / parent.height);
};
Workflow.Samples = [
    { label: "Ordinary", variant: "U", accentColors: ["U"], legendary: false, name: "Tidewatch Adept", nickname: "", mana: "{2}{U}", type: "Creature — Human Wizard", rules: "Flying\nWhen this creature enters, draw a card.", flavor: "Every tide brings a new story.", pt: "2/3" },
    { label: "Legendary · two colors", variant: "M", accentColors: ["U", "R"], legendary: true, name: "Aria, Keeper of Storms", nickname: "The Stormcaller", mana: "{3}{U}{R}", type: "Legendary Creature — Human Wizard", rules: "Flying, haste\nWhenever you cast your second spell each turn, draw a card.", flavor: "A storm is only a story waiting to be told.", pt: "4/4" },
    { label: "Long text", variant: "G", accentColors: ["G"], legendary: false, name: "Keeper of the Forgotten Grove", nickname: "", mana: "{4}{G}{G}", type: "Creature — Elf Druid", rules: "Reach\nWhen this creature enters, you may search your library for a basic land card, reveal it, put it into your hand, then shuffle.\nWhenever a land enters under your control, put a +1/+1 counter on this creature. This ability triggers only once each turn.", flavor: "The oldest roots remember every traveler.", pt: "3/5" },
    { label: "Land · no power/toughness", variant: "L", accentColors: ["U"], legendary: false, name: "Quiet Harbor", nickname: "", mana: "", type: "Land", rules: "This land enters tapped.\n{T}: Add {U}.", flavor: "Safe passage, even in the darkest storm.", pt: "" }
];