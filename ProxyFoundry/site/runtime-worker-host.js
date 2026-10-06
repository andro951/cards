//The iframe supplies native control defaults and the runtime's security origin.
//All drawing and PNG encoding happen in its dedicated worker.
(() => {
    const parameters=new URLSearchParams(location.search);
    const parentOrigin=document.querySelector('meta[name="pf-parent-origin"]')?.content||location.origin;
    const snapshot=element=>({
        tag:element.tagName.toLowerCase(),
        attributes:Object.fromEntries([...element.attributes].map(attribute=>[attribute.name,attribute.value])),
        value:element.value??``,checked:!!element.checked,
        children:[...element.children].map(snapshot)
    });
    const worker=new Worker('/site/native-render-worker.js'+location.search);
    worker.onmessage=async event=>{
        if(event.data?.type!==`decode-svg`){parent.postMessage(event.data,parentOrigin);return;}
        const {id,blob,geometry}=event.data;const url=URL.createObjectURL(blob);
        try{
            const image=new Image();image.src=url;await image.decode();
            const [x,y,width,height]=geometry||[0,0,image.naturalWidth,image.naturalHeight];
            const offsetX=x-Math.floor(x),offsetY=y-Math.floor(y);
            const canvas=new OffscreenCanvas(Math.ceil(width+offsetX),Math.ceil(height+offsetY));
            canvas.getContext(`2d`).drawImage(image,offsetX,offsetY,width,height);
            const bitmap=await createImageBitmap(canvas);worker.postMessage({type:`decoded-svg`,id,bitmap},[bitmap]);
        }catch(error){worker.postMessage({type:`decoded-svg`,id,error:error.message});}
        finally{URL.revokeObjectURL(url);}
    };
    worker.onerror=event=>parent.postMessage({source:`pf-native-runtime`,type:`failed`,error:event.message||`Native worker failed.`},parentOrigin);
    window.addEventListener(`message`,event=>{
        if(event.source!==parent||event.origin!==parentOrigin||event.data?.source!==`pf-app`)return;
        if(event.data.type===`dispose`)worker.terminate();
        else worker.postMessage(event.data);
    });
    window.addEventListener(`pagehide`,()=>worker.terminate(),{once:true});
    worker.postMessage({source:`pf-app`,type:`initialize`,controls:snapshot(document.body),owner:parameters.get(`owner`)||``,parentOrigin});
})();