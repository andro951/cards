export function createBatchReviewFlow(dependencies) {
    let active=false;
    const run=async({downloadAll=false}={})=>{
        if(active)
            throw new Error(`A review batch is already running.`);

        active=true;
        let sessionId=null;
        try {
            const candidates=await dependencies.getCandidates({downloadAll});
            const decks=candidates.decks;
            if(!decks.length)
                return {decks:[],skipped:candidates.skipped||[],result:null};

            const session=await dependencies.start(decks.map(deck=>deck.id),{downloadAll});
            sessionId=session.id;
            const rendered=await dependencies.render(decks.filter(deck=>deck.status!==`ready`).map(deck=>deck.id));
            if(rendered===false)
                throw new Error(`Generation was cancelled. No review ZIPs were copied.`);

            const exports=[];
            for(const deck of decks) {
                const output=await dependencies.exportAndStage(sessionId,deck);
                exports.push(output.filename);
            }

            const result=await dependencies.commit(sessionId);
            sessionId=null;
            return {decks,skipped:candidates.skipped||[],result,exports};
        }
        catch(error) {
            if(sessionId) {
                await dependencies.abort(sessionId).catch(abortError=>dependencies.onAbortError?.(abortError));
            }

            throw error;
        }
        finally {
            active=false;
        }
    };
    return {run,get busy(){return active;}};
}