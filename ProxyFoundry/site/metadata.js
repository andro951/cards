import {api,job,state,toast} from './ui.js';

const pending=new Map();
export function startMetadata(deck){
  if(!deck.pendingImport)return Promise.resolve(deck);
  if(pending.has(deck.id))return pending.get(deck.id).promise;
  const controller=new AbortController();
  const promise=job('/api/decks/'+deck.id+'/metadata',{}, {label:'Reading card details',resources:['metadata:'+deck.id],background:true,signal:controller.signal,
    onProgress:progress=>state.setupActions?.deckId===deck.id&&state.setupActions.metadataProgress?.(progress)
  }).then(async()=>{
    const updated=await api('/api/decks/'+deck.id);
    if(state.setupActions?.deckId===deck.id&&state.setupActions.root.isConnected)state.setupActions.refreshMetadata(updated);
    window.dispatchEvent(new CustomEvent('pf-deck-metadata',{detail:updated}));
    return updated;
  }).catch(error=>{
    if(!controller.signal.aborted){
      if(state.setupActions?.deckId===deck.id&&state.setupActions.root.isConnected)state.setupActions.metadataError?.(error);
      else toast('Card details could not finish: '+error.message+' Generate Images will retry.',true);
    }
    throw error;
  }).finally(()=>pending.delete(deck.id));
  pending.set(deck.id,{controller,promise});
  return promise;
}
export async function ensureMetadata(id){
  const deck=await api('/api/decks/'+id);
  if(deck.pendingImport)await startMetadata(deck);
  return api('/api/decks/'+id);
}
export async function cancelMetadata(id){
  const task=pending.get(id);
  if(!task)return;
  task.controller.abort();
  await task.promise.catch(error=>console.info('Card details task stopped',error.message));
}