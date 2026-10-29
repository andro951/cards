import test from 'node:test';
import assert from 'node:assert/strict';
import {chooseFolder} from '../web/storage-choice.js';

test('choosing the existing BulkProxyForge folder does not create a nested workspace',async()=>{
  const folder={name:'BulkProxyForge',getDirectoryHandle(){throw new Error('Must not create a child');}};
  globalThis.window={showDirectoryPicker:async()=>folder};
  assert.equal(await chooseFolder(),folder);
});

test('an existing database identifies a workspace with a different folder name',async()=>{
  const folder={name:'My decks',async getFileHandle(name){assert.equal(name,'workspace.sqlite3');return {};},
    getDirectoryHandle(){throw new Error('Must not create a child');}};
  globalThis.window={showDirectoryPicker:async()=>folder};
  assert.equal(await chooseFolder(),folder);
});

test('choosing a parent directory still opens its BulkProxyForge child',async()=>{
  const child={name:'BulkProxyForge'};
  globalThis.window={showDirectoryPicker:async()=>({name:'Documents',
    async getFileHandle(){throw new DOMException('Missing','NotFoundError');},
    async getDirectoryHandle(name,options){assert.equal(name,'BulkProxyForge');assert.equal(options.create,true);return child;}})};
  assert.equal(await chooseFolder(),child);
});

test('an unreadable workspace fails without creating a separate empty child',async()=>{
  globalThis.window={showDirectoryPicker:async()=>({name:'My decks',
    async getFileHandle(){throw new DOMException('Unavailable','NotAllowedError');},
    getDirectoryHandle(){throw new Error('Must not create a child');}})};
  await assert.rejects(chooseFolder(),{name:'NotAllowedError'});
});
