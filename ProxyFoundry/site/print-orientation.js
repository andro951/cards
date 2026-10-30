//Keep the working canvas horizontal; only persisted/printed PNGs are portrait.
export async function portraitPrintOutput(output,enabled) {
    if(!enabled||output.width<=output.height)return output;
    const image=await createImageBitmap(output.blob);
    try {
        const canvas=new OffscreenCanvas(output.height,output.width),context=canvas.getContext('2d');
        context.translate(0,output.width);context.rotate(-Math.PI/2);context.drawImage(image,0,0);
        const blob=await canvas.convertToBlob({type:'image/png'});
        return {...output,blob,width:output.height,height:output.width};
    }finally{image.close();}
}
