import {cancelMetadata} from './metadata.js';
import {$,state,api,toast,modal,closeModal,nav,confirmAction,work} from './ui.js';
import {recordDiagnostic} from './diagnostics.js';

let key=null;
let pending={};
const running=new Set();
let cleanupWarning=null;
window.addEventListener('pf-cleanup-warning',event=>{
  if(cleanupWarning?.isConnected)return;
  cleanupWarning=document.createElement('div');cleanupWarning.className='toast error';cleanupWarning.setAttribute('role','alert');
  const text=document.createElement('span');text.textContent='A deck or print order was removed, but some saved files could not be cleaned up: '+event.detail+' ';
  const retry=document.createElement('button');retry.className='button small';retry.textContent='Retry cleanup';
  retry.onclick=async()=>{
    retry.disabled=true;
    try{await api('/api/cleanup/retry',{});cleanupWarning.remove();cleanupWarning=null;}
    catch(error){retry.disabled=false;toast(error.message,true);}
  };
  cleanupWarning.append(text,retry);$('#toast-host').append(cleanupWarning);
});
export function visibleDecks(decks){return decks.filter(deck=>!pending[deck.id]);}
function persist(){localStorage.setItem(key,JSON.stringify(pending));}
export function blockedDeletion(id){
  recordDiagnostic('deck deletion blocked','A print order uses deck '+id);
  const host=modal('Deck cannot be deleted','');
  const body=$('.modal-body',host);
  const text=document.createElement('p');
  text.textContent='A print order uses this deck. Delete the print order before deleting this deck.';
  const button=document.createElement('button');button.className='button primary';button.textContent='Show print orders';
  button.onclick=()=>{closeModal();nav('orders/'+id);};body.append(text,button);
}
async function finish(id,cancellation=Promise.resolve()){
  if(running.has(id))return;
  running.add(id);
  try{
    await cancellation;
    const current=await api('/api/decks/'+id+'/deletion-state');
    recordDiagnostic('deck deletion','Deleting '+id+' at revision '+current.revision);
    if(!current.deleted)await api('/api/decks/'+id+'/delete',{revision:current.revision});
    delete pending[id];persist();toast('Deck deleted.');
  }
  catch(error){
    delete pending[id];persist();state.immediateLibrary=false;
    toast('Deck could not be deleted: '+error.message,true);
    if(error.message.startsWith('A print order uses'))blockedDeletion(id);
    window.dispatchEvent(new Event('pf-deletion-failed'));
  }
  finally{running.delete(id);}
}
export function resumeDeletions(){
  key='pf-pending-deck-deletions:'+state.bootstrap.workspaceId;
  try{pending=JSON.parse(localStorage.getItem(key)||'{}');}
  catch(error){console.error('Could not read pending deletions',error);toast('Could not recover pending deck deletions.',true);}
  for(const id of Object.keys(pending)){void finish(id);}
}
export async function deleteDeck(deck){
  recordDiagnostic('deck deletion requested',deck.id+' '+deck.name);
  work.requireDeletable('deck:'+deck.id);
  const button=$('#trash-deck');
  if(button){button.disabled=true;button.textContent='Checking print orders…';}
  let orders;
  try{orders=await api('/api/decks/'+deck.id+'/orders');}
  finally{if(button){button.disabled=false;button.textContent='Delete deck';}}
  closeModal();
  if(orders.length){blockedDeletion(deck.id);return;}
  if(!await confirmAction('Delete this deck permanently?',deck.name+' will be deleted and cannot be restored.','Delete permanently',true))return;
  const cancellation=Promise.all([work.cancelGeneration('deck:'+deck.id),cancelMetadata(deck.id)]);
  recordDiagnostic('deck deletion','Confirmed '+deck.id+'; cancelling any generation before deletion');
  pending[deck.id]={revision:deck.revision};persist();
  state.decks=visibleDecks(state.decks);state.selected.delete(deck.id);state.immediateLibrary=true;
  state.dirty=false;
  if(location.hash==='#decks')window.dispatchEvent(new Event('pf-library-deletion'));
  else nav('decks');
  toast('Deck removed. Cleaning up saved files in the background.');
  void finish(deck.id,cancellation);
}