"""Concurrent task ownership, renderer queue priority and cancellation lifetimes."""
import base64
import shutil
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def run(source):
    module='data:text/javascript;base64,'+base64.b64encode((ROOT/'site/work.js').read_bytes()).decode()
    script="import assert from 'node:assert/strict';const {WorkCoordinator}=await import(process.argv[1]);\n"+source
    subprocess.run([shutil.which('node') or 'D:/nvm4w/nodejs/node.exe',
        '--input-type=module','-e',script,module],capture_output=True,text=True,check=True)


def test_scoped_locks_and_foreground_progress_restore():
    run('''
const work=new WorkCoordinator();
const generation=work.begin({label:`Generate images for A`,resources:[`deck:A`],background:true});
work.update(generation,{title:`Rendering A`});
assert.equal(work.visible(),generation);
assert.throws(()=>work.requireAvailable([`deck:A`]),/Generate images for A.*using this deck/);
work.requireAvailable([`deck:A`],generation);
const foreground=work.begin({label:`Import B`,resources:[`deck:B`]});
work.update(foreground,{title:`Importing B`});
work.update(generation,{title:`Rendering next card`});
assert.equal(work.visible(),foreground);
foreground.controller.abort();
assert.equal(generation.controller.signal.aborted,false);
work.finish(foreground);
assert.equal(work.busy,true);assert.equal(work.visible(),generation);
assert.equal(work.visible().progress.title,`Rendering next card`);
work.requireAvailable([`deck:B`]);work.finish(generation);
assert.equal(work.busy,false);assert.equal(work.resources.size,0);
''')


def test_deletion_cancels_only_generation_and_waits_for_settlement():
    run('''
const work=new WorkCoordinator();
const target=work.begin({kind:`generation`,label:`Generate A`,resources:[`deck:A`]});
const other=work.begin({kind:`generation`,label:`Generate B`,resources:[`deck:B`]});
let settled=false;const cancellation=work.cancelGeneration(`deck:A`).then(()=>settled=true);
assert.equal(target.controller.signal.aborted,true);assert.equal(other.controller.signal.aborted,false);
await Promise.resolve();assert.equal(settled,false);
assert.throws(()=>work.requireAvailable([`deck:A`]),/using this deck/);
work.finish(target);await cancellation;work.requireAvailable([`deck:A`]);
const mutation=work.begin({label:`Save A`,resources:[`deck:A`]});
assert.throws(()=>work.cancelGeneration(`deck:A`),/Save A/);assert.equal(mutation.controller.signal.aborted,false);
work.finish(mutation);work.finish(other);
const workspace=work.begin({label:`Restore`,resources:[`workspace`]});
assert.throws(()=>work.cancelGeneration(`deck:A`),/changing the workspace/);work.finish(workspace);
''')


def test_renderer_priority_queue_duplicate_guard_and_cancel():
    run('''
const work=new WorkCoordinator();const ran=[];let finishFirst;
const first=work.render(async task=>{ran.push(`first`);await new Promise(resolve=>finishFirst=resolve);return `saved`;},
    {label:`Generate A`,resources:[`deck:A`]});
await Promise.resolve();
const second=work.render(()=>ran.push(`second`),{label:`Generate B`,resources:[`deck:B`]});
assert.throws(()=>work.render(()=>{}, {label:`Duplicate`,resources:[`deck:A`]}),/using this deck/);
const preview=work.render(()=>ran.push(`preview`),{label:`Validate template`,background:false});
const canceled=work.render(()=>ran.push(`must not run`),{label:`Generate C`,resources:[`deck:C`]});
const rejected=assert.rejects(canceled,/Queued task cancelled/);
work.queue.find(entry=>entry.task.label===`Generate C`).task.controller.abort();
await rejected;work.requireAvailable([`deck:C`]);
assert.deepEqual(ran,[`first`]);finishFirst();
assert.equal(await first,`saved`);work.requireAvailable([`deck:A`]);
await Promise.all([second,preview]);
assert.deepEqual(ran,[`first`,`preview`,`second`]);
assert.equal(work.busy,false);assert.equal(work.renderer,null);assert.equal(work.queue.length,0);
''')


def test_renderer_failure_and_external_abort_release_resources():
    run('''
const work=new WorkCoordinator();const controller=new AbortController();let finish;
const running=work.render(async task=>{await new Promise(resolve=>finish=resolve);throw new Error(`Save failure`);},
    {label:`Generate A`,resources:[`deck:A`],signal:controller.signal});
const rejected=assert.rejects(running,/Save failure/);
await Promise.resolve();controller.abort();
assert.equal(work.renderer.controller.signal.aborted,true);
let secondRan=false;
const next=work.render(()=>secondRan=true,{label:`Generate B`,resources:[`deck:B`]});
finish();await rejected;await next;
assert.equal(secondRan,true);assert.equal(work.busy,false);assert.equal(work.resources.size,0);
assert.throws(()=>work.begin({signal:controller.signal}),/cancelled/);
''')


def test_workspace_replacement_is_exclusive_but_deck_changes_are_scoped():
    run('''
const work=new WorkCoordinator();
const deck=work.begin({label:`Generate A`,resources:[`deck:A`]});
assert.throws(()=>work.begin({label:`Restore backup`,resources:[`workspace`]}),/Generate A.*whole workspace/);
const other=work.begin({label:`Save B`,resources:[`deck:B`]});
work.finish(deck);work.finish(other);
const restore=work.begin({label:`Restore backup`,resources:[`workspace`]});
assert.throws(()=>work.begin({label:`Import deck`}),/Restore backup.*changing the workspace/);
work.requireAvailable([`workspace`],restore);
work.finish(restore);assert.equal(work.busy,false);
''')
