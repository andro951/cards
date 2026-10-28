"use strict";

//Use the same engine dispatcher as service-worker requests, without an HTTP hop.
export function createWorkspaceFetch(dispatch,discard,basePath) {
    return async (path,options)=>{
        const request=new Request(new URL(path,location.href),options);
        const address=new URL(request.url);
        const route=basePath&&address.pathname.startsWith(basePath+`/`)?address.pathname.slice(basePath.length):address.pathname;
        if(address.origin!==location.origin||!route.startsWith(`/api/`))
            return fetch(request);

        request.signal.throwIfAborted();
        const body=[`GET`,`HEAD`].includes(request.method)?null:await request.arrayBuffer();
        request.signal.throwIfAborted();
        const id=crypto.randomUUID();
        const channel=new MessageChannel();
        const result=await new Promise((resolve,reject)=>{
            const close=()=>{
                clearTimeout(timer);request.signal.removeEventListener(`abort`,abort);
                channel.port1.close();discard(id);
            };
            const abort=()=>{close();reject(request.signal.reason);};
            const timer=setTimeout(()=>{
                close();reject(new Error(`The workspace did not respond within two minutes. Download browser diagnostics before reloading.`));
            },120000);
            request.signal.addEventListener(`abort`,abort,{once:true});
            channel.port1.onmessage=event=>{close();resolve(event.data);};
            channel.port1.onmessageerror=()=>{close();reject(new Error(`The workspace response could not be read.`));};
            dispatch({type:`request`,id,method:request.method,url:route+address.search,
                headers:Object.fromEntries(request.headers),body},channel.port2);
        });
        if(result.type===`error`)
            throw new Error(result.message);

        const headers=new Headers(result.headers||{});
        headers.set(`Content-Type`,result.mime||`application/octet-stream`);
        if(result.filename)
            headers.set(`Content-Disposition`,`attachment; filename="${result.filename}"`);

        return new Response([204,205,304].includes(result.status)?null:result.body,{status:result.status,headers});
    };
}