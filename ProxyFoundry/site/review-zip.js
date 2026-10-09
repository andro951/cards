//JPEG is already compressed. Store entries without running another compressor.
const crcTable=new Uint32Array(256);
for(let index=0;index<256;index++) {
    let value=index;
    for(let bit=0;bit<8;bit++) {value=value&1?0xedb88320^(value>>>1):value>>>1;}
    crcTable[index]=value;
}

export class ReviewZip {
    parts=[];
    entries=[];
    offset=0;
    add=async(filename,blob)=>{
        const name=new TextEncoder().encode(filename),bytes=new Uint8Array(await blob.arrayBuffer());
        if(this.entries.length>=65535||this.offset+bytes.length+name.length+30>0xffffffff)
            throw new Error(`This review ZIP is too large. Download smaller decks separately.`);

        let crc=0xffffffff;
        for(const byte of bytes) {crc=crcTable[(crc^byte)&255]^(crc>>>8);}
        crc=(crc^0xffffffff)>>>0;
        const header=new Uint8Array(30+name.length),local=new DataView(header.buffer);
        local.setUint32(0,0x04034b50,true);local.setUint16(4,20,true);local.setUint16(6,0x800,true);
        local.setUint16(12,33,true);local.setUint32(14,crc,true);local.setUint32(18,bytes.length,true);
        local.setUint32(22,bytes.length,true);local.setUint16(26,name.length,true);header.set(name,30);
        const entry=new Uint8Array(46+name.length),central=new DataView(entry.buffer);
        central.setUint32(0,0x02014b50,true);central.setUint16(4,20,true);central.setUint16(6,20,true);
        central.setUint16(8,0x800,true);central.setUint16(14,33,true);central.setUint32(16,crc,true);
        central.setUint32(20,bytes.length,true);central.setUint32(24,bytes.length,true);
        central.setUint16(28,name.length,true);central.setUint32(42,this.offset,true);entry.set(name,46);
        this.parts.push(header,blob);this.entries.push(entry);this.offset+=header.length+bytes.length;
    };
    finish=()=>{
        const size=this.entries.reduce((sum,entry)=>sum+entry.length,0);
        if(this.offset+size+22>0xffffffff)
            throw new Error(`This review ZIP is too large. Download smaller decks separately.`);

        const end=new Uint8Array(22),view=new DataView(end.buffer);
        view.setUint32(0,0x06054b50,true);view.setUint16(8,this.entries.length,true);
        view.setUint16(10,this.entries.length,true);view.setUint32(12,size,true);view.setUint32(16,this.offset,true);
        return new Blob([...this.parts,...this.entries,end],{type:`application/zip`});
    };
}