"""A lost IndexedDB folder handle must stop startup before opening a separate empty workspace."""
import base64,os
import pytest
from test_browser_storage import static_browser
from foundry.storage import Store
from foundry.workspace import DEFAULT_SETTINGS

pytestmark=pytest.mark.skipif(os.environ.get('PF_BROWSER')!='1',reason='Actual browser workspace reconnect')

@pytest.mark.parametrize('static_browser',['msedge'] if os.name=='nt' else [None],indirect=True)
def test_missing_folder_handle_reconnects_existing_decks_and_survives_reload(static_browser,tmp_path):
    directory,context,origin=static_browser
    store=Store(tmp_path/'seed')
    for name in ['Recovered Cats','Recovered Supernatural','Recovered Wrath']:
        store.put('decks',{'name':name,'cards':[],'settings':dict(DEFAULT_SETTINGS),'status':'draft'})
    seed=base64.b64encode(store.db_path.read_bytes()).decode()
    page=context.new_page()
    page.add_init_script("""(()=>{
        if(!sessionStorage.getItem('reconnect-test-seeded')){
            localStorage.setItem('bulk-proxy-forge-workspace-location',JSON.stringify({kind:'folder',name:'SavedWorkspace'}));
            sessionStorage.setItem('reconnect-test-seeded','yes');
        }
        window.__seedReady=navigator.storage.getDirectory().then(async root=>{
            const folder=await root.getDirectoryHandle('SavedWorkspace',{create:true});
            if(!await folder.getFileHandle('workspace.sqlite3').catch(()=>null)){
                const writer=await (await folder.getFileHandle('workspace.sqlite3',{create:true})).createWritable();
                await writer.write(Uint8Array.from(atob('"""+seed+"""'),c=>c.charCodeAt(0)));await writer.close();
            }
            return folder;
        });
        window.showDirectoryPicker=()=>window.__seedReady;
    })();""")
    page.goto(origin,wait_until='domcontentloaded')
    page.get_by_role('button',name='Reconnect workspace folder',exact=True).wait_for(timeout=90000)
    assert page.locator('#import-deck').count()==0
    assert page.evaluate("navigator.storage.getDirectory().then(root=>root.getFileHandle('workspace.sqlite3').then(()=>false,()=>true))")
    page.get_by_role('button',name='Reconnect workspace folder',exact=True).click()
    page.locator('#import-deck').wait_for(timeout=90000)
    for name in ['Recovered Cats','Recovered Supernatural','Recovered Wrath']:assert page.get_by_text(name,exact=True).count()==1
    page.reload(wait_until='domcontentloaded');page.locator('#import-deck').wait_for(timeout=90000)
    assert page.get_by_text('Recovered Cats',exact=True).count()==1
    #Simulate eviction of only the IndexedDB connection. The folder data stays intact.
    page.evaluate("""()=>new Promise((resolve,reject)=>{
        const request=indexedDB.open('bulk-proxy-forge-browser',1);
        request.onsuccess=()=>{const db=request.result,tx=db.transaction('preferences','readwrite');
            tx.objectStore('preferences').delete('workspaceFolder');tx.oncomplete=()=>{db.close();resolve();};tx.onabort=()=>reject(tx.error);};
    })""")
    page.reload(wait_until='domcontentloaded')
    page.get_by_role('button',name='Reconnect workspace folder',exact=True).wait_for(timeout=90000)
    assert page.locator('#import-deck').count()==0
    assert page.evaluate("navigator.storage.getDirectory().then(root=>root.getFileHandle('workspace.sqlite3').then(()=>false,()=>true))")
