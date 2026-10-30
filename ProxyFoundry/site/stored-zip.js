//Stored ZIP entries reference source Blobs; image bytes never accumulate in JavaScript arrays.
const table=new Uint32Array(256);
for(let index=0;index<256;index++) {
    let value=index;
    for(let bit=0;bit<8;bit++) {value=value&1?0xedb88320^(value>>>1):value>>>1;}
    table[index]=value;
}

export const crc32=async(blob,cancelled=()=>false)=>{
    const reader=blob.stream().getReader();let crc=0xffffffff;
    try {
        while(true) {
            if(cancelled())throw new Error(`Order packaging cancelled.`);
            const {done,value}=await reader.read();
            if(done)break;
            for(let index=0;index<value.length;index++) {crc=table[(crc^value[index])&255]^(crc>>>8);}
        }

        return (crc^0xffffffff)>>>0;
    }
    finally {reader.releaseLock();}
};

const extra64=values=>{
    if(!values.length)return new Uint8Array();
    const bytes=new Uint8Array(4+values.length*8),view=new DataView(bytes.buffer);
    view.setUint16(0,1,true);view.setUint16(2,values.length*8,true);
    for(let index=0;index<values.length;index++) {view.setBigUint64(4+index*8,values[index],true);}
    return bytes;
};
const maximum=0xffffffffn;
//Stay below decimal 2 GB, verified with Edge FileReader and the printer's reader.
export const PRINTER_ZIP_LIMIT=1_999_999_999;
export const storedEntryBytes=(name,size)=>size+76+2*new TextEncoder().encode(name).length;
export class StoredZip {
    parts=[];
    entries=[];
    offset=0n;
    add=(filename,blob,crc)=>{
        const name=new TextEncoder().encode(filename),size=BigInt(blob.size),large=size>=maximum,far=this.offset>=maximum;
        const localExtra=extra64(large?[size,size]:[]),centralExtra=extra64([...(large?[size,size]:[]),...(far?[this.offset]:[])]);
        const header=new Uint8Array(30+name.length+localExtra.length),local=new DataView(header.buffer);
        local.setUint32(0,0x04034b50,true);local.setUint16(4,large?45:20,true);local.setUint16(6,0x800,true);
        local.setUint16(12,33,true);local.setUint32(14,crc,true);
        local.setUint32(18,large?0xffffffff:blob.size,true);local.setUint32(22,large?0xffffffff:blob.size,true);
        local.setUint16(26,name.length,true);local.setUint16(28,localExtra.length,true);header.set(name,30);header.set(localExtra,30+name.length);
        const entry=new Uint8Array(46+name.length+centralExtra.length),central=new DataView(entry.buffer);
        central.setUint32(0,0x02014b50,true);central.setUint16(4,45,true);central.setUint16(6,large||far?45:20,true);
        central.setUint16(8,0x800,true);central.setUint16(14,33,true);central.setUint32(16,crc,true);
        central.setUint32(20,large?0xffffffff:blob.size,true);central.setUint32(24,large?0xffffffff:blob.size,true);
        central.setUint16(28,name.length,true);central.setUint16(30,centralExtra.length,true);
        central.setUint32(42,far?0xffffffff:Number(this.offset),true);entry.set(name,46);entry.set(centralExtra,46+name.length);
        this.parts.push(header,blob);this.entries.push(entry);this.offset+=BigInt(header.length)+size;
    };
    finish=()=>{
        const size=BigInt(this.entries.reduce((sum,entry)=>sum+entry.length,0)),count=BigInt(this.entries.length),tails=[];
        if(this.offset>=maximum||size>=maximum||count>=0xffffn) {
            const end64=new Uint8Array(56),record=new DataView(end64.buffer);
            record.setUint32(0,0x06064b50,true);record.setBigUint64(4,44n,true);record.setUint16(12,45,true);record.setUint16(14,45,true);
            record.setBigUint64(24,count,true);record.setBigUint64(32,count,true);record.setBigUint64(40,size,true);record.setBigUint64(48,this.offset,true);
            const locator=new Uint8Array(20),location=new DataView(locator.buffer);
            location.setUint32(0,0x07064b50,true);location.setBigUint64(8,this.offset+size,true);location.setUint32(16,1,true);tails.push(end64,locator);
        }

        const end=new Uint8Array(22),view=new DataView(end.buffer);
        view.setUint32(0,0x06054b50,true);view.setUint16(8,Number(count<0xffffn?count:0xffffn),true);view.setUint16(10,Number(count<0xffffn?count:0xffffn),true);
        view.setUint32(12,Number(size<maximum?size:maximum),true);view.setUint32(16,Number(this.offset<maximum?this.offset:maximum),true);
        return new Blob([...this.parts,...this.entries,...tails,end],{type:`application/zip`});
    };
}
