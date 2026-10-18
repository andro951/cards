//Review exports resize saved images; they never invoke the card renderer.
self.onmessage=async event=>{
    let reference=null,rendered=null;
    try {
        const {item,root,assetUrl}=event.data;
        const response=await fetch(item.reference,{signal:AbortSignal.timeout(60000)});
        if(!response.ok)
            throw new Error(`Could not download ${item.name}: HTTP ${response.status}.`);

        reference=await createImageBitmap(await response.blob());
        let image;
        if(root) {
            const assets=await root.getDirectoryHandle(`assets`);
            const folder=await assets.getDirectoryHandle(item.assetId.slice(0,2));
            image=await(await folder.getFileHandle(item.assetId)).getFile();
        }
        else {
            const saved=await fetch(assetUrl,{signal:AbortSignal.timeout(60000)});
            if(!saved.ok)
                throw new Error(`The saved image for ${item.name} is unavailable.`);

            image=await saved.blob();
        }

        rendered=await createImageBitmap(image);
        const width=Math.max(1,Math.floor(rendered.width/2)),height=Math.max(1,Math.floor(rendered.height/2));
        const canvas=new OffscreenCanvas(width*2+1,height),context=canvas.getContext(`2d`,{alpha:false});
        context.fillStyle=`#000000`;context.fillRect(0,0,canvas.width,canvas.height);
        context.imageSmoothingEnabled=true;context.imageSmoothingQuality=`high`;
        //Battle scans may be sideways portrait files. Rotate before fitting,
        //and retain proportions even when a reference has different margins.
        const rotate=(reference.width-reference.height)*(rendered.width-rendered.height)<0;
        const referenceWidth=rotate?reference.height:reference.width,referenceHeight=rotate?reference.width:reference.height;
        const scale=Math.min(width/referenceWidth,height/referenceHeight);
        const fittedWidth=referenceWidth*scale,fittedHeight=referenceHeight*scale;
        context.save();context.translate((width-fittedWidth)/2,(height-fittedHeight)/2);
        if(rotate) {
            if(rendered.width>rendered.height) {
                context.translate(fittedWidth,0);context.rotate(Math.PI/2);
            }
            else {
                context.translate(0,fittedHeight);context.rotate(-Math.PI/2);
            }

            context.drawImage(reference,0,0,fittedHeight,fittedWidth);
        }
        else
            context.drawImage(reference,0,0,fittedWidth,fittedHeight);

        context.restore();context.drawImage(rendered,width+1,0,width,height);
        const blob=await canvas.convertToBlob({type:`image/png`});
        canvas.width=1;canvas.height=1;
        if(blob.type!==`image/png`)
            throw new Error(`This browser could not encode a PNG review image.`);

        self.postMessage({blob});
    }
    catch(error) {self.postMessage({error:error.message||String(error)});}
    finally {reference?.close();rendered?.close();}
};
