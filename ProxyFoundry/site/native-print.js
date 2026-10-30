//Pass the existing disk-backed File between tabs using structured cloning.
//Extension messages carry authorization/metadata only, never ZIP payload bytes.
export async function openNativePrint({createTransfer,register,getFile,targetOrigin='https://www.tcgplaytest.com'}) {
  const printer=window.open('about:blank','_blank');
  if(!printer)throw new Error('Allow this site to open the printer tab, then click Print Cards again.');
  let cleanup=()=>{};
  try {
    const transfer=await createTransfer();
    let serving=false;
    const listener=async event=>{
      const data=event.data,port=event.ports[0];
      if(event.origin!==targetOrigin||event.source!==printer||data?.type!=='PF_NATIVE_FILE_REQUEST'||
         data.id!==transfer.id||data.secret!==transfer.secret||!port||serving)return;
      serving=true;
      try {
        const received=await getFile(transfer.id,transfer.secret),files=Array.isArray(received)?received:[received];
        if(!files.length||files.some(file=>!(file instanceof File)))throw new Error('The saved ZIP parts are not available as native files.');
        //A newly named File references the existing Blob data without reading it.
        //It also drops the source tab's native file path, which another renderer
        //cannot attach to an input under Chromium's file-access policy.
        const uploads=files.map(file=>new File([file],file.name,{type:'application/zip',lastModified:file.lastModified}));
        port.postMessage({ok:true,files:uploads});
      }catch(error){port.postMessage({ok:false,error:error.message||String(error)});}
      finally{port.close();cleanup();}
    };
    const timer=setTimeout(()=>cleanup(),60*60*1000);
    cleanup=()=>{clearTimeout(timer);window.removeEventListener('message',listener);};
    window.addEventListener('message',listener);
    const reply=await register({...transfer,browser:true,wholeFile:true});
    const url=new URL(reply.url);
    if(url.origin!==targetOrigin||url.searchParams.get('proxyFoundryOrder')!==transfer.id)
      throw new Error('The helper returned an invalid printer destination.');
    printer.location.href=url.href;
  }catch(error){cleanup();printer.close();throw error;}
}
