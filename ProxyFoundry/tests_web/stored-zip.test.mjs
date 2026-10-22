import test from 'node:test';
import assert from 'node:assert/strict';
import {StoredZip,crc32} from '../site/stored-zip.js';

test(`CRC matches the standard check value and handles empty files`,async()=>{
    assert.equal(await crc32(new Blob([`123456789`])),0xcbf43926);
    assert.equal(await crc32(new Blob()),0);
    await assert.rejects(crc32(new Blob([`data`]),()=>true),/cancelled/);
});

test(`stored entries preserve binary bytes, UTF-8 names and source Blob references`,async()=>{
    const source=new Blob([new Uint8Array([0,1,255,128])]),zip=new StoredZip();
    const crc=await crc32(source),name=`FRONT/é.png`,encoded=new TextEncoder().encode(name);
    zip.add(name,source,crc);zip.add(`BACK/000001.png`,source,crc);
    assert.equal(zip.parts[1],source);assert.equal(zip.parts[3],source);
    const bytes=new Uint8Array(await zip.finish().arrayBuffer()),view=new DataView(bytes.buffer);
    assert.equal(view.getUint32(0,true),0x04034b50);
    assert.equal(view.getUint16(6,true),0x800);assert.equal(view.getUint16(8,true),0);
    assert.equal(view.getUint32(14,true),crc);assert.equal(view.getUint32(18,true),source.size);
    assert.deepEqual(bytes.slice(30,30+encoded.length),encoded);
    assert.deepEqual(bytes.slice(30+encoded.length,34+encoded.length),new Uint8Array([0,1,255,128]));
    const end=bytes.length-22;
    assert.equal(view.getUint32(end,true),0x06054b50);assert.equal(view.getUint16(end+10,true),2);
    assert.equal(view.getUint32(end+16,true),Number(zip.offset));
    assert.equal(view.getUint32(Number(zip.offset),true),0x02014b50);
});

test(`ZIP64 stores large sizes and offsets without truncation`,()=>{
    const zip=new StoredZip(),size=0x100000010n,offset=0x200000020n;
    zip.offset=offset;zip.add(`FRONT/000001.png`,{size:Number(size)},123);
    const header=zip.parts[0],local=new DataView(header.buffer),entry=zip.entries[0],central=new DataView(entry.buffer);
    const nameLength=local.getUint16(26,true),extra=30+nameLength,centralExtra=46+nameLength;
    assert.equal(local.getUint16(4,true),45);assert.equal(local.getUint32(18,true),0xffffffff);
    assert.equal(local.getBigUint64(extra+4,true),size);assert.equal(local.getBigUint64(extra+12,true),size);
    assert.equal(central.getUint32(42,true),0xffffffff);
    assert.equal(central.getBigUint64(centralExtra+4,true),size);
    assert.equal(central.getBigUint64(centralExtra+20,true),offset);
});

test(`ZIP64 end records retain offsets beyond four GiB`,async()=>{
    const zip=new StoredZip();zip.offset=0x100000010n;zip.add(`BACK/000001.png`,new Blob(),0);
    const bytes=await zip.finish().arrayBuffer(),view=new DataView(bytes),end=bytes.byteLength-22,record=end-76,locator=end-20;
    assert.equal(view.getUint32(record,true),0x06064b50);
    assert.equal(view.getBigUint64(record+48,true),zip.offset);
    assert.equal(view.getUint32(locator,true),0x07064b50);
    assert.equal(view.getBigUint64(locator+8,true),zip.offset+BigInt(zip.entries[0].length));
    assert.equal(view.getUint32(end+16,true),0xffffffff);
});