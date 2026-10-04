"use strict";

import { Model } from "./model.js";

export class Renderer {
    constructor() {
        this.images = new Map();
        this.fonts = new Map();
        this.bounds = new Map();
        this.imageIds = new WeakMap();
        this.nextImageId = 1;
        this.frameCache = null;
        this.frameCacheKey = "";
        this.frameWarnings = [];
    }

    //#region Assets
    loadImage = source => {
        if (!this.images.has(source)) {
            const pending = new Promise((resolve, reject) => {
                const image = new Image();
                image.onload = () => {
                    if (image.naturalWidth * image.naturalHeight > 25000000) {
                        reject(new Error(`Image exceeds 25 million pixels.`));
                        return;
                    }

                    this.imageIds.set(image, this.nextImageId++);
                    resolve(image);
                };
                image.onerror = () => reject(new Error(`Could not load ${source.startsWith("data:") ? "uploaded image" : source}`));
                image.src = source;
            });
            this.images.set(source, pending);
            pending.catch(() => this.images.delete(source));
        }

        return this.images.get(source);
    };
    loadFont = name => {
        const paths = { belerenb: "beleren-b.ttf", belerenbsc: "beleren-bsc.ttf", mplantin: "mplantin.ttf", mplantini: "mplantin-i.ttf" };
        if (!paths[name])
            return Promise.resolve();

        if (!this.fonts.has(name)) {
            const face = new FontFace(name, `url(/fonts/${paths[name]})`);
            const pending = face.load().then(font => document.fonts.add(font));
            this.fonts.set(name, pending);
            pending.catch(() => this.fonts.delete(name));
        }

        return this.fonts.get(name);
    };
    makeCanvas = (width = Model.Width, height = Model.Height) => {
        const canvas = document.createElement("canvas");
        canvas.width = width; canvas.height = height;
        return canvas;
    };
    alphaBounds = image => {
        if (!this.bounds.has(image)) {
            const canvas = document.createElement("canvas");
            canvas.width = image.naturalWidth; canvas.height = image.naturalHeight;
            const context = canvas.getContext("2d", { willReadFrequently: true });
            context.drawImage(image, 0, 0);
            const bounds = Model.AlphaBounds(context.getImageData(0, 0, canvas.width, canvas.height).data, canvas.width, canvas.height);
            this.bounds.set(image, bounds);
            canvas.width = 1; canvas.height = 1;
        }

        return this.bounds.get(image);
    };
    sourceFor = (model, part, code = model.preview.variant) => model.assets[part.map ? model.maps[part.map][code] || model.maps[part.map].C : part.asset];
    symbolPath = token => `/img/manaSymbols/${token.toLowerCase().replaceAll(/[{}\/]/g, "")}.svg`;
    tokens = text => text.match(/\{[^}]+\}|\n|[^\S\n]+|[^\s{]+|\{/g) || [];
    //#endregion

    //#region Layout and drawing
    drawImage = (context, image, part, target, warnings) => {
        const original = Model.Rect(0, 0, image.naturalWidth, image.naturalHeight);
        const crop = part.alignment === "piece" && part.trimAlpha ? this.alphaBounds(image) : original;
        if (!crop) {
            warnings.push(`${part.name}: image is entirely transparent.`);
            return;
        }

        if (part.alignment === "full-card") {
            if (Math.abs(image.naturalWidth / image.naturalHeight - 5 / 7) > 0.015)
                warnings.push(`${part.name}: full-card image is not 5:7; check alignment or use standalone-piece fitting.`);

            context.drawImage(image, target.x, target.y, target.width, target.height);
            return;
        }

        const fitted = Model.Contain(crop, target, part.scale);
        context.drawImage(image, crop.x, crop.y, crop.width, crop.height, fitted.x, fitted.y, fitted.width, fitted.height);
    };
    gradient = (context, rect, colors, palette) => {
        const gradient = context.createLinearGradient(rect.x, 0, rect.x + rect.width, 0);
        gradient.addColorStop(0, palette[colors[0]]); gradient.addColorStop(0.4, palette[colors[0]]);
        for (let index = 1; index < 20; index++) {
            const t = index / 20;
            const amount = t * t * (3 - 2 * t);
            const rgb = color => color.match(/[a-f\d]{2}/gi).map(hex => parseInt(hex, 16));
            const a = rgb(palette[colors[0]]), b = rgb(palette[colors[1]]);
            gradient.addColorStop(0.4 + 0.2 * t, `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * amount)).join(",")})`);
        }

        gradient.addColorStop(0.6, palette[colors[1]]); gradient.addColorStop(1, palette[colors[1]]);
        return gradient;
    };
    textLayout = (context, text, part, rect, size) => {
        context.font = `${size}px ${part.style.font}`;
        const lines = [[]]; let width = 0;
        for (const token of this.tokens(text)) {
            const symbol = /^\{[^}]+\}$/.test(token);
            const tokenWidth = symbol ? size * 0.82 : context.measureText(token).width;
            if (token === "\n" || !part.style.oneLine && width + tokenWidth > rect.width && lines.at(-1).length) {
                lines.push([]); width = 0;
                if (token === "\n" || /^\s+$/.test(token))
                    continue;
            }

            lines.at(-1).push({ text: token, width: tokenWidth, symbol }); width += tokenWidth;
        }

        const lineWidth = line => line.reduce((sum, token) => sum + token.width, 0);
        return { lines, height: lines.length * size * part.style.lineHeight, width: Math.max(0, ...lines.map(lineWidth)), lineWidth };
    };
    fitText = (context, text, part, rect) => {
        let size = part.style.size;
        let layout = this.textLayout(context, text, part, rect, size);
        while (size > part.style.minSize && (layout.height > rect.height || layout.width > rect.width)) {
            size = Math.max(part.style.minSize, size - 0.5);
            layout = this.textLayout(context, text, part, rect, size);
        }

        return { ...layout, size, overflow: layout.height > rect.height + 0.1 || layout.width > rect.width + 0.1 };
    };
    drawText = (context, text, part, rect, layout, symbols) => {
        context.save(); context.font = `${layout.size}px ${part.style.font}`;
        context.fillStyle = part.style.color; context.strokeStyle = part.style.outlineColor || "#000000";
        context.lineWidth = part.style.outline; context.lineJoin = "round"; context.textBaseline = "top";
        let y = rect.y;
        for (const line of layout.lines) {
            const width = layout.lineWidth(line);
            let x = rect.x + (part.style.align === "center" ? (rect.width - width) / 2 : part.style.align === "right" ? rect.width - width : 0);
            for (const token of line) {
                if (token.symbol) {
                    const image = symbols.get(this.symbolPath(token.text));
                    if (image)
                        context.drawImage(image, x, y + layout.size * 0.08, token.width, token.width);
                    else
                        context.fillText(token.text, x, y);
                }
                else {
                    if (part.style.outline > 0)
                        context.strokeText(token.text, x, y);

                    context.fillText(token.text, x, y);
                }

                x += token.width;
            }

            y += layout.size * part.style.lineHeight;
        }

        context.restore();
    };
    //#endregion

    render = async (model, canvas, selection = null, showGuides = false, cancelled = () => false, progress = () => {}) => {
        const started = performance.now();
        Model.Validate(model);
        const warnings = [], visible = model.parts.filter(part => Model.Visible(part, model.preview));
        const sources = new Set(), fontNames = new Set(), symbolSources = new Set();
        for (const part of visible) {
            const source = this.sourceFor(model, part);
            if (source)
                sources.add(source);

            if (part.mask)
                sources.add(model.assets[part.mask]);

            if (part.map && part.treatment === "crown" && model.preview.accentColors.length === 2) {
                for (const color of model.preview.accentColors) {
                    sources.add(this.sourceFor(model, part, color));
                }
            }

            if (part.kind === "text")
                fontNames.add(part.style.font);

            if (["text", "mana"].includes(part.kind)) {
                for (const token of this.tokens(Model.Content(part, model.preview)).filter(token => /^\{[^}]+\}$/.test(token))) {
                    symbolSources.add(this.symbolPath(token));
                }
            }
        }

        const loaded = new Map(), symbols = new Map();
        const total = sources.size + fontNames.size + symbolSources.size;
        let completed = 0;
        const advance = () => progress(++completed, total);
        await Promise.all([...sources].map(async source => { loaded.set(source, await this.loadImage(source)); advance(); }));
        await Promise.all([...fontNames].map(async font => { await this.loadFont(font); advance(); }));
        await Promise.all([...symbolSources].map(async source => {
            const image = await this.loadImage(source).catch(error => { warnings.push(error.message); return null; });
            symbols.set(source, image);
            advance();
        }));
        if (cancelled())
            return null;

        const context = canvas.getContext("2d");
        context.clearRect(0, 0, canvas.width, canvas.height);
        context.save(); context.scale(canvas.width / Model.Width, canvas.height / Model.Height);
        context.fillStyle = "#000000"; context.fillRect(0, 0, Model.Width, Model.Height);
        const layer = this.layerCanvas ||= this.makeCanvas(), mask = this.maskCanvas ||= this.makeCanvas();
        for (const scratch of [layer, mask]) {
            if (scratch.width !== canvas.width || scratch.height !== canvas.height) {
                scratch.width = canvas.width; scratch.height = canvas.height;
            }
        }

        const frameKey = JSON.stringify({ width: canvas.width, height: canvas.height, parts: visible.filter(part => !["text", "mana", "divider", "artwork"].includes(part.kind)), anchors: model.anchors, palette: model.palette, variant: model.preview.variant, accentColors: model.preview.accentColors, images: [...loaded].map(([source, image]) => this.imageIds.get(image)) });
        const cachedFrames = this.frameCache && this.frameCacheKey === frameKey;
        const frames = cachedFrames ? this.frameCache : this.makeCanvas(canvas.width, canvas.height);
        const lc = layer.getContext("2d"), mc = mask.getContext("2d"), fc = frames.getContext("2d");
        for (const scratch of [lc, mc, fc]) {
            scratch.setTransform(canvas.width / Model.Width, 0, 0, canvas.height / Model.Height, 0, 0);
        }
        const positions = new Map(visible.map(part => [part.id, Model.ResolvePart(model, part)]));
        const mana = visible.find(part => part.kind === "mana");
        if (mana) {
            const tokens = this.tokens(Model.Content(mana, model.preview)).filter(token => /^\{[^}]+\}$/.test(token));
            const bounds = positions.get(mana.id);
            const symbolSize = Math.min(mana.symbolSize, bounds.height, bounds.width / Math.max(1, tokens.length));
            positions.set(mana.id, { ...bounds, x: bounds.x + bounds.width - symbolSize * tokens.length, width: symbolSize * tokens.length, symbolSize, tokens });
        }

        for (const part of visible.filter(part => part.kind === "text")) {
            if (!part.reserveFor || !positions.has(part.reserveFor))
                continue;

            const box = positions.get(part.id), reserved = positions.get(part.reserveFor);
            positions.set(part.id, { ...box, width: Math.max(1, Math.min(box.width, reserved.x - box.x - 8)) });
        }

        const flowParts = visible.filter(part => part.kind === "text" && part.flow === "rules" && ["rules", "flavor"].includes(part.field));
        const flows = new Map();
        if (flowParts.length) {
            const rulesPart = flowParts.find(part => part.field === "rules") || flowParts[0];
            const area = { ...positions.get(rulesPart.id) };
            const pt = visible.find(part => part.id === "PT_Box");
            if (pt && positions.get(pt.id).y < area.y + area.height)
                area.height = Math.max(1, positions.get(pt.id).y - area.y - 8);

            const divider = visible.find(part => part.kind === "divider");
            let size = Math.min(...flowParts.map(part => part.style.size));
            const minimum = Math.max(...flowParts.map(part => part.style.minSize));
            const measure = () => flowParts.map(part => this.textLayout(lc, Model.Content(part, model.preview), part, area, size));
            let layouts = measure();
            const total = () => layouts.reduce((height, item) => height + item.height, 0) + (divider && flowParts.length > 1 ? 20 : 0);
            while (size > minimum && (total() > area.height || layouts.some(item => item.width > area.width))) {
                size = Math.max(minimum, size - 0.5); layouts = measure();
            }

            let y = area.y;
            flowParts.forEach((part, index) => {
                const layout = { ...layouts[index], size };
                const box = { ...area, y, height: layout.height };
                flows.set(part.id, { box, layout }); positions.set(part.id, box);
                y += layout.height;
                if (divider && index === 0 && flowParts.length > 1) {
                    positions.set(divider.id, Model.Rect(area.x + area.width * 0.125, y + 10, area.width * 0.75, 1));
                    y += 20;
                }
            });
            if (total() > area.height || layouts.some(item => item.width > area.width))
                warnings.push(`Rules/flavor text overflows its region at the minimum font size.`);
        }

        const imageParts = visible.filter(part => !["text", "mana", "divider"].includes(part.kind));
        const frameWarningStart = warnings.length;
        for (const part of imageParts) {
            if (cachedFrames && part.kind !== "artwork")
                continue;

            const target = positions.get(part.id);
            lc.clearRect(0, 0, Model.Width, Model.Height); lc.globalCompositeOperation = "source-over"; lc.globalAlpha = 1;
            if (part.kind === "fill") {
                lc.fillStyle = part.color; lc.fillRect(target.x, target.y, target.width, target.height);
            }
            else if (part.kind === "artwork") {
                const image = loaded.get(this.sourceFor(model, part));
                lc.save(); lc.beginPath(); lc.rect(target.x, target.y, target.width, target.height); lc.clip();
                if (image) {
                    const box = Model.Cover(Model.Rect(0, 0, image.width, image.height), target, part.scale, part.focus || { x: 0.5, y: 0.5 });
                    lc.drawImage(image, box.x, box.y, box.width, box.height);
                }
                else {
                    const gradient = lc.createLinearGradient(target.x, target.y, target.x + target.width, target.y + target.height);
                    gradient.addColorStop(0, "#1c374c"); gradient.addColorStop(0.5, "#ba7649"); gradient.addColorStop(1, "#182932");
                    lc.fillStyle = gradient; lc.fillRect(target.x, target.y, target.width, target.height);
                    lc.fillStyle = "#ffffff"; lc.font = "30px serif"; lc.textAlign = "center";
                    lc.fillText("Upload artwork to test placement", target.x + target.width / 2, target.y + target.height / 2);
                    lc.textAlign = "left";
                }

                lc.restore();
            }
            else if (part.treatment === "pinline" && model.preview.accentColors.length === 2) {
                lc.fillStyle = this.gradient(lc, target, model.preview.accentColors, model.palette);
                lc.fillRect(target.x, target.y, target.width, target.height);
            }
            else {
                const image = loaded.get(this.sourceFor(model, part));
                if (image)
                    this.drawImage(lc, image, part, target, warnings);
                else if (part.blend === "destination-out" && part.mask) {
                    lc.fillStyle = "#000000"; lc.fillRect(0, 0, Model.Width, Model.Height);
                }

                if (part.treatment === "crown" && model.preview.accentColors.length === 2 && part.map) {
                    lc.clearRect(0, 0, Model.Width, Model.Height);
                    this.drawImage(lc, loaded.get(this.sourceFor(model, part, model.preview.accentColors[0])), part, target, warnings);
                    mc.clearRect(0, 0, Model.Width, Model.Height); mc.globalCompositeOperation = "source-over";
                    this.drawImage(mc, loaded.get(this.sourceFor(model, part, model.preview.accentColors[1])), part, target, warnings);
                    const gradient = mc.createLinearGradient(target.x, 0, target.x + target.width, 0);
                    gradient.addColorStop(0.4, "transparent"); gradient.addColorStop(0.6, "#ffffff");
                    for (let index = 1; index < 20; index++) {
                        const t = index / 20;
                        gradient.addColorStop(0.4 + 0.2 * t, `rgba(255,255,255,${t * t * (3 - 2 * t)})`);
                    }
                    mc.globalCompositeOperation = "destination-in"; mc.fillStyle = gradient; mc.fillRect(0, 0, Model.Width, Model.Height);
                    mc.globalCompositeOperation = "source-over"; lc.drawImage(mask, 0, 0, Model.Width, Model.Height);
                }
            }

            if (part.mask) {
                mc.clearRect(0, 0, Model.Width, Model.Height); mc.globalCompositeOperation = "source-over";
                mc.drawImage(loaded.get(model.assets[part.mask]), 0, 0, Model.Width, Model.Height);
                lc.globalCompositeOperation = "destination-in"; lc.drawImage(mask, 0, 0, Model.Width, Model.Height); lc.globalCompositeOperation = "source-over";
            }

            if (part.kind === "artwork") {
                context.globalAlpha = part.opacity; context.drawImage(layer, 0, 0, Model.Width, Model.Height); context.globalAlpha = 1;
            }
            else {
                fc.globalAlpha = part.opacity; fc.globalCompositeOperation = part.blend; fc.drawImage(layer, 0, 0, Model.Width, Model.Height);
            }
        }

        if (cachedFrames)
            warnings.push(...this.frameWarnings);
        else {
            if (this.frameCache)
                this.frameCache.width = 1;

            this.frameCache = frames; this.frameCacheKey = frameKey;
            this.frameWarnings = warnings.slice(frameWarningStart);
        }

        context.drawImage(frames, 0, 0, Model.Width, Model.Height);
        for (const part of visible.filter(part => ["text", "mana", "divider"].includes(part.kind))) {
            const rect = positions.get(part.id); context.globalAlpha = part.opacity;
            if (part.kind === "text") {
                const content = Model.Content(part, model.preview);
                const layout = flows.get(part.id)?.layout || this.fitText(lc, content, part, rect);
                if (layout.overflow)
                    warnings.push(`${part.name}: text overflows at the minimum font size.`);

                this.drawText(context, content, part, rect, layout, symbols);
            }
            else if (part.kind === "mana") {
                rect.tokens.forEach((token, index) => {
                    const image = symbols.get(this.symbolPath(token));
                    if (image)
                        context.drawImage(image, rect.x + index * rect.symbolSize, rect.y, rect.symbolSize, rect.symbolSize);
                    else {
                        context.fillStyle = "#ffbbbb"; context.font = `${Math.max(8, rect.symbolSize / 3)}px sans-serif`;
                        context.fillText(token, rect.x + index * rect.symbolSize, rect.y + rect.symbolSize / 2);
                    }
                });
            }
            else if (part.kind === "divider") {
                const image = loaded.get(this.sourceFor(model, part));
                if (image)
                    context.drawImage(image, rect.x, rect.y, rect.width, Math.max(1, rect.height));
                else {
                    context.fillStyle = part.color; context.fillRect(rect.x, rect.y, rect.width, Math.max(1, rect.height));
                }
            }
        }

        context.globalAlpha = 1;
        if (showGuides) {
            context.lineWidth = 2;
            for (const part of visible) {
                const rect = positions.get(part.id);
                if (part.alignment === "full-card" && part.id !== selection)
                    continue;

                context.strokeStyle = part.id === selection ? "#ff9b36" : "#29b9e4";
                context.strokeRect(rect.x, rect.y, rect.width, rect.height);
            }
        }

        context.restore();
        return { warnings: [...new Set(warnings)], positions, milliseconds: performance.now() - started };
    };
}