"use strict";

export const Model = {};
Model.Width = 1000;
Model.Height = 1400;
Model.Variants = ["W", "U", "B", "R", "G", "M", "A", "L", "C", "V"];
Model.Clone = model => ({ ...structuredClone({ ...model, assets: {} }), assets: { ...model.assets } });
Model.Rect = (x, y, width, height) => ({ x, y, width, height });

//#region Geometry
Model.ResolveAnchor = (model, id, visited = new Set()) => {
    if (id === "Canvas")
        return Model.Rect(0, 0, Model.Width, Model.Height);

    if (visited.has(id) || !model.anchors[id])
        throw new Error(`Invalid or circular anchor: ${id}`);

    visited.add(id);
    const anchor = model.anchors[id];
    const parent = Model.ResolveAnchor(model, anchor.relativeTo, visited);
    return Model.RelativeRect(parent, anchor.rect);
};
Model.RelativeRect = (parent, rect) => Model.Rect(parent.x + rect.x * parent.width, parent.y + rect.y * parent.height, rect.width * parent.width, rect.height * parent.height);
Model.ResolvePart = (model, part) => Model.RelativeRect(Model.ResolveAnchor(model, part.placement.relativeTo), part.placement.rect);
Model.Contain = (source, target, scale = 1) => {
    const fit = Math.min(target.width / source.width, target.height / source.height) * scale;
    const width = source.width * fit;
    const height = source.height * fit;
    return Model.Rect(target.x + (target.width - width) / 2, target.y + (target.height - height) / 2, width, height);
};
Model.Cover = (source, target, scale = 1, focus = { x: 0.5, y: 0.5 }) => {
    const fit = Math.max(target.width / source.width, target.height / source.height) * scale;
    const width = source.width * fit;
    const height = source.height * fit;
    return Model.Rect(target.x + (target.width - width) * focus.x, target.y + (target.height - height) * focus.y, width, height);
};
Model.AlphaBounds = (pixels, width, height, threshold = 2) => {
    let left = width, top = height, right = -1, bottom = -1;
    for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
            if (pixels[(y * width + x) * 4 + 3] < threshold)
                continue;

            left = Math.min(left, x); top = Math.min(top, y);
            right = Math.max(right, x); bottom = Math.max(bottom, y);
        }
    }

    return right < left ? null : Model.Rect(left, top, right - left + 1, bottom - top + 1);
};
//#endregion

//#region Validation and bindings
Model.SafeSource = source => typeof source === "string" && (/^\/(?:img|fonts)\/[A-Za-z0-9_ .%/-]+\.(?:png|jpe?g|webp|svg|ttf|otf|woff2?)$/i.test(source) && !source.split("/").includes("..") || /^data:image\/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(source));
Model.Validate = value => {
    if (!value || value.format !== "bulk-proxy-forge-visual-template" || value.schemaVersion !== 2 || value.canvas !== "card-5x7")
        throw new Error(`Choose a version 2 visual template with a fixed 5:7 canvas.`);

    if (!Array.isArray(value.parts) || value.parts.length > 100 || !value.parts.length || !value.anchors || !value.assets || !value.maps || !value.preview)
        throw new Error(`Template needs parts, anchors, assets, maps and preview data.`);

    if (typeof value.name !== "string" || !value.name.trim() || value.name.length > 200)
        throw new Error(`Give the template a name of 1–200 characters.`);

    if (Object.keys(value.assets).length > 300 || Object.keys(value.anchors).length > 100)
        throw new Error(`Template has too many assets or anchors.`);

    if (!Model.Variants.includes(value.preview.variant) || !Array.isArray(value.preview.accentColors) || value.preview.accentColors.length < 1 || value.preview.accentColors.length > 2 || value.preview.accentColors.some(code => !Model.Variants.includes(code)) || value.preview.accentColors.length === 2 && value.preview.accentColors.some(code => !"WUBRG".includes(code)))
        throw new Error(`Choose valid preview colors. Two-color accents use W/U/B/R/G.`);

    if (!value.palette || [..."WUBRG"].some(code => !/^#[a-f\d]{6}$/i.test(value.palette[code])))
        throw new Error(`Each frame color needs a six-digit palette color.`);

    for (const field of ["name", "nickname", "type", "mana", "rules", "flavor", "pt", "credit"]) {
        if (typeof value.preview[field] !== "string" || value.preview[field].length > 20000)
            throw new Error(`Invalid preview text: ${field}`);
    }

    const ids = new Set();
    const checkRect = rect => {
        if (!rect || ![rect.x, rect.y, rect.width, rect.height].every(Number.isFinite) || Math.abs(rect.x) > 5 || Math.abs(rect.y) > 5 || rect.width <= 0 || rect.height <= 0 || rect.width > 5 || rect.height > 5)
            throw new Error(`Positions must be finite and sizes positive.`);
    };
    for (const [id, anchor] of Object.entries(value.anchors)) {
        checkRect(anchor.rect);
        Model.ResolveAnchor(value, id);
    }

    for (const [id, source] of Object.entries(value.assets)) {
        if (!Model.SafeSource(source) || source.length > 40 * 1024 * 1024)
            throw new Error(`Unsupported image source: ${id}`);
    }

    for (const map of Object.values(value.maps)) {
        if (!map || typeof map !== "object" || Array.isArray(map))
            throw new Error(`Image variants must be a map.`);

        for (const [code, asset] of Object.entries(map)) {
            if (!Model.Variants.includes(code) || !Object.hasOwn(value.assets, asset))
                throw new Error(`Unknown variant or missing image: ${code}`);
        }
    }

    for (const part of value.parts) {
        if (!part || typeof part.id !== "string" || ids.has(part.id) || !["image", "artwork", "text", "mana", "fill", "divider"].includes(part.kind))
            throw new Error(`Each part needs a unique ID and a supported kind.`);

        ids.add(part.id);
        if (!part.placement)
            throw new Error(`Missing placement: ${part.id}`);

        checkRect(part.placement.rect); Model.ResolvePart(value, part);
        for (const key of [part.asset, part.mask].filter(Boolean)) {
            if (!Object.hasOwn(value.assets, key))
                throw new Error(`Missing asset ${key}`);
        }

        if (part.map && !Object.hasOwn(value.maps, part.map))
            throw new Error(`Unknown image map ${part.map}`);

        if (part.map && !Object.hasOwn(value.maps[part.map], "C"))
            throw new Error(`Image maps need a Colorless fallback.`);

        if (!["always", "legendary", "nickname", "pt", "rulesAndFlavor"].includes(part.when) || !["piece", "full-card"].includes(part.alignment) || !Number.isFinite(part.opacity) || part.opacity < 0 || part.opacity > 1 || !Number.isFinite(part.scale) || part.scale <= 0 || part.scale > 10)
            throw new Error(`Invalid visibility, sizing or opacity: ${part.id}`);

        if (!["source-over", "destination-out"].includes(part.blend) || !["none", "pinline", "crown"].includes(part.treatment))
            throw new Error(`Invalid compositing treatment: ${part.id}`);

        if (part.kind === "artwork" && (part.scale < 1 || part.focus && (!Number.isFinite(part.focus.x) || !Number.isFinite(part.focus.y) || part.focus.x < 0 || part.focus.x > 1 || part.focus.y < 0 || part.focus.y > 1)))
            throw new Error(`Artwork zoom must be at least 1 and focus coordinates between 0 and 1.`);

        if (["fill", "divider"].includes(part.kind) && !/^#[a-f\d]{6}$/i.test(part.color))
            throw new Error(`Choose a valid fill color: ${part.id}`);

        if (part.kind === "text" && (!part.style || !Number.isFinite(part.style.size) || part.style.size < 1 || part.style.size > 200 || !["belerenb", "belerenbsc", "mplantin", "mplantini", "serif", "sans-serif"].includes(part.style.font) || !["left", "center", "right"].includes(part.style.align) || !Number.isFinite(part.style.lineHeight) || part.style.lineHeight < 0.5 || part.style.lineHeight > 3 || !Number.isFinite(part.style.minSize) || part.style.minSize < 1 || part.style.minSize > part.style.size || !Number.isFinite(part.style.outline) || part.style.outline < 0 || part.style.outline > 20))
            throw new Error(`Invalid text style: ${part.id}`);

        if (part.kind === "text" && (!["displayName", "name", "nickname", "type", "rules", "flavor", "pt", "credit"].includes(part.field) || !/^#[a-f\d]{6}$/i.test(part.style.color) || !/^#[a-f\d]{6}$/i.test(part.style.outlineColor)))
            throw new Error(`Invalid text binding or color: ${part.id}`);

        if (part.kind === "mana" && (part.field !== "mana" || !Number.isFinite(part.symbolSize) || part.symbolSize <= 0 || part.symbolSize > 200))
            throw new Error(`Invalid mana symbol size: ${part.id}`);
    }

    if (value.parts.filter(part => part.kind === "artwork").length !== 1 || !value.anchors.ArtWindow)
        throw new Error(`Template needs exactly one artwork layer and an ArtWindow anchor.`);

    return value;
};
Model.Visible = (part, card) => part.visible && ({ always: true, legendary: card.legendary, nickname: Boolean(card.nickname?.trim()), pt: Boolean(card.pt?.trim()), rulesAndFlavor: Boolean(card.rules?.trim() && card.flavor?.trim()) })[part.when];
Model.Content = (part, card) => part.field === "displayName" ? card.nickname || card.name : String(card[part.field] || "");
Model.NewPart = (id, kind = "image", anchor = "Canvas") => ({ id, name: id, kind, visible: true, when: "always", placement: { relativeTo: anchor, rect: Model.Rect(0, 0, 1, 1) }, alignment: "piece", trimAlpha: true, scale: 1, opacity: 1, blend: "source-over", treatment: "none", color: "#000000", asset: null, map: null, mask: null });
//#endregion