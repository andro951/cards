const icon=document.createElement(`link`);
icon.rel=`icon`;
icon.type=`image/png`;
icon.setAttribute(`sizes`,`64x64`);
icon.href=new URL(`./favicon.png`,import.meta.url).href;
document.head.append(icon);