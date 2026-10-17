"use strict";

//Only frame layers are reusable; artwork, text and special-card canvases stay live.
export class FrameCompositionCache {
    constructor(limit=48*1024*1024) {
        this.limit=limit;this.entries=new Map();this.bytes=0;this.hits=0;
    }
    key = runtime => {
        if(runtime.drawTextBetweenFrames||!runtime.card?.frames?.length)
            return null;

        //SVG antialiasing can round differently after an extra canvas copy.
        if(runtime.card.frames.some(frame=>[frame,...(frame.masks||[])].some(layer=>/^image\/svg\+xml(?:;|$)/i.test(layer.image?.blob?.type||``))))
            return null;

        return JSON.stringify([runtime.frameCanvas.width,runtime.frameCanvas.height,runtime.card.width,runtime.card.height,runtime.card.marginX,runtime.card.marginY,runtime.card.version,runtime.card.frames],(key,value)=>key===`image`?value?.src:value);
    };
    draw = (runtime,nativeDraw,mayStore) => {
        const key=this.key(runtime),entry=key&&this.entries.get(key);
        if(entry) {
            this.entries.delete(key);this.entries.set(key,entry);this.hits++;
            const context=runtime.frameContext;
            context.save();context.setTransform(1,0,0,1,0,0);context.globalCompositeOperation=`copy`;context.globalAlpha=1;
            context.drawImage(entry.canvas,0,0);context.restore();runtime.drawCard();
            return;
        }

        nativeDraw();
        if(!key||!mayStore)
            return;

        const bytes=runtime.frameCanvas.width*runtime.frameCanvas.height*4;
        if(bytes>this.limit)
            return;

        const canvas=new OffscreenCanvas(runtime.frameCanvas.width,runtime.frameCanvas.height);
        canvas.getContext(`2d`).drawImage(runtime.frameCanvas,0,0);
        this.entries.set(key,{canvas,bytes});this.bytes+=bytes;
        while(this.bytes>this.limit) {
            const oldest=this.entries.keys().next().value,removed=this.entries.get(oldest);
            this.entries.delete(oldest);this.bytes-=removed.bytes;removed.canvas.width=1;removed.canvas.height=1;
        }
    };
}