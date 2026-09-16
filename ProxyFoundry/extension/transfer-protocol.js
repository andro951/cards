/* Shared by the service worker and merchant content script. No page globals. */
(() => {
  const VERSION = '1.1.0';
  const MAX_BATCH_BYTES = 1024 ** 3;
  function normalize(meta) {
    const integer = (n, min, max = Number.MAX_SAFE_INTEGER) => Number.isSafeInteger(n) && n >= min && n <= max;
    if (!meta || !integer(meta.count, 1, 10000) || !integer(meta.zipBytes, 22)) throw new Error('Invalid paired-order package.');
    if (meta.protocol != null && meta.protocol !== 2) throw new Error('Unsupported transfer protocol. Update Bulk Proxy Forge and the print helper.');
    const batched = meta.protocol === 2;
    if (!batched && meta.zipBytes > MAX_BATCH_BYTES) throw new Error('Update Bulk Proxy Forge to transfer this order in 1 GB ZIP batches. The full-resolution images do not need to change.');
    const batches = batched ? meta.batches : [{index:0,count:meta.count,startCard:1,endCard:meta.count,zipBytes:meta.zipBytes,filename:meta.filename || 'BulkProxyForge_Order.zip'}];
    if (!Array.isArray(batches) || !batches.length || batches.length > meta.count) throw new Error('Invalid paired-order batch list.');
    let next = 1;
    const checked = batches.map((b, i) => {
      if (!b || b.index !== i || !integer(b.count, 1, meta.count) || b.startCard !== next || b.endCard !== next + b.count - 1 || !integer(b.zipBytes, 22, MAX_BATCH_BYTES)) throw new Error('Invalid paired-order batch size or card sequence.');
      next += b.count;
      const filename = b.filename || `BulkProxyForge_Batch_${String(i + 1).padStart(4, '0')}.zip`;
      if (typeof filename !== 'string' || filename.length > 200 || !/^[A-Za-z0-9_.-]+\.zip$/.test(filename)) throw new Error('Invalid ZIP batch filename.');
      return {index:i,count:b.count,startCard:b.startCard,endCard:b.endCard,zipBytes:b.zipBytes,filename};
    });
    if (next !== meta.count + 1) throw new Error('ZIP batches do not match the saved card count.');
    return {protocol:batched ? 2 : undefined,count:meta.count,zipBytes:meta.zipBytes,batches:checked};
  }
  globalThis.PF_TRANSFER = Object.freeze({VERSION,MAX_BATCH_BYTES,normalize});
})();
