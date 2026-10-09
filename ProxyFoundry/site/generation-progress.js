//#region Continuous estimate
export class GenerationEstimate {
    constructor(cards=1,now=()=>performance.now()) {
        this.now=now;this.started=now();this.phaseStarted=this.started;this.phase=`metadata`;
        this.expected={metadata:0,prepare:Math.max(2,cards*.3),render:Math.max(2,cards*1.1),finish:1};
        this.finished=0;this.highest=0;this.done=0;this.total=0;
    }
    update=(phase,done=0,total=0)=>{
        if(phase!==this.phase) {
            this.finished+=Math.max(.001,(this.now()-this.phaseStarted)/1000);this.expected[this.phase]=0;
            this.phase=phase;this.phaseStarted=this.now();this.done=0;this.total=0;
        }

        this.done=Math.max(this.done,done);this.total=total;
        return this.read();
    };
    read=()=>{
        const elapsed=(this.now()-this.phaseStarted)/1000;
        const ratio=this.total?Math.min(1,this.done/this.total):0;
        const duration=this.done>0&&elapsed>1?Math.max(elapsed,elapsed/Math.max(ratio,.001)):this.expected[this.phase];
        const later=Object.entries(this.expected).reduce((sum,[phase,value])=>sum+(phase===this.phase?0:value),0);
        const remaining=Math.max(0,duration-elapsed)+later;
        const percent=(this.finished+duration*ratio)/Math.max(.001,this.finished+duration+later)*100;
        this.highest=Math.max(this.highest,Math.min(99,percent));
        return {percent:Math.floor(this.highest),seconds:remaining,elapsed:(this.now()-this.started)/1000};
    };
}
//#endregion

//#region Full-screen generation
export const generationScreen={active:null};
export class GenerationScreen {
    constructor(name,cards=1) {
        this.estimate=new GenerationEstimate(cards);
        this.dialog=document.createElement(`dialog`);this.dialog.id=`generation-screen`;
        this.dialog.setAttribute(`aria-label`,`Generating ${name}`);
        Object.assign(this.dialog.style,{position:`fixed`,inset:`0`,width:`100vw`,height:`100dvh`,maxWidth:`none`,maxHeight:`none`,margin:`0`,border:`0`,borderRadius:`0`,boxSizing:`border-box`,background:`#100c08`,color:`#f0d7aa`,padding:`max(24px, 8vw)`,alignContent:`center`,textAlign:`center`});
        const title=document.createElement(`h1`);title.textContent=`Generating your cards`;title.style.marginBottom=`12px`;
        const deck=document.createElement(`p`);deck.textContent=name;deck.style.marginBottom=`24px`;
        this.bar=document.createElement(`progress`);this.bar.max=100;this.bar.value=0;this.bar.setAttribute(`aria-label`,`Overall generation progress`);
        Object.assign(this.bar.style,{width:`min(100%, 720px)`,height:`24px`,accentColor:`#ed861e`});
        this.percent=document.createElement(`p`);this.percent.textContent=`0%`;Object.assign(this.percent.style,{fontSize:`32px`,margin:`24px 0 12px`});
        this.time=document.createElement(`p`);this.time.textContent=`Estimating time remaining…`;this.time.setAttribute(`role`,`status`);this.time.style.marginBottom=`24px`;
        this.cancel=document.createElement(`button`);this.cancel.type=`button`;this.cancel.className=`button`;this.cancel.textContent=`Cancel`;
        this.cancel.onclick=()=>{this.owner?.controller.abort();this.cancel.disabled=true;this.time.textContent=`Stopping… Completed cards will be kept.`;};
        this.dialog.addEventListener(`cancel`,event=>event.preventDefault());
        this.dialog.append(title,deck,this.bar,this.percent,this.time,this.cancel);
        document.body.append(this.dialog);this.dialog.showModal();this.cancel.disabled=true;
        this.timer=setInterval(this.draw,1000);generationScreen.active=this;
        document.querySelector(`#activity`)?.classList.add(`hidden`);
    }
    attach=owner=>{this.owner=owner;this.cancel.disabled=false;};
    update=(phase,done=0,total=0)=>{this.estimate.update(phase,done,total);this.draw();};
    draw=()=>{
        if(this.owner?.controller.signal.aborted)
            return;

        const value=this.estimate.read();this.bar.value=value.percent;this.percent.textContent=`${value.percent}%`;
        const seconds=Math.max(5,Math.ceil(value.seconds/5)*5);
        this.time.textContent=value.elapsed<2?`Estimating time remaining…`:seconds<60?`About ${seconds} seconds remaining`:`About ${Math.ceil(seconds/60)} minutes remaining`;
    };
    close=()=>{
        clearInterval(this.timer);this.dialog.close();this.dialog.remove();
        if(generationScreen.active===this)
            generationScreen.active=null;
    };
}
export async function withGenerationScreen(name,cards,operation) {
    const screen=generationScreen.active||new GenerationScreen(name,cards);
    screen.users=(screen.users||0)+1;
    try {
        const result=await operation(screen);
        if(screen.users===1) {
            screen.bar.value=100;screen.percent.textContent=`100%`;screen.time.textContent=`Complete`;screen.cancel.disabled=true;
            clearInterval(screen.timer);
            await new Promise(resolve=>setTimeout(resolve,200));
        }

        return result;
    }
    finally {if(--screen.users===0)screen.close();}
}
//#endregion