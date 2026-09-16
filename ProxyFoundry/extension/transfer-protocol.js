/* Shared validation for the MV3 worker and merchant content script. */
(() => {
  const MAX_ZIP_BYTES = 1024 ** 3;
  const CHUNK_BYTES = 1024 ** 2;
  const positive = n => Number.isSafeInteger(n) && n > 0;
  function metadata(value) {
    if (!value || !positive(value.count) || value.count > 10000 ||
        !Number.isSafeInteger(value.zipBytes) || value.zipBytes < 22) {
      throw new Error('Invalid paired-order metadata.');
    }
    const legacy = value.protocol == null && value.batches == null;
    if (legacy && value.zipBytes > MAX_ZIP_BYTES) {
      throw new Error('Update and restart Bulk Proxy Forge to stream this large order in upload batches.');
    }
    const list = legacy ? [{index:0, count:value.count, firstCard:1, lastCard:value.count,
      zipBytes:value.zipBytes, filename:value.filename}] : value.batches;
    if ((!legacy && value.protocol !== 2) || !Array.isArray(list) || !list.length || list.length > value.count) {
      throw new Error('Invalid upload-batch manifest.');
    }
    let first = 1;
    const batches = list.map((b, index) => {
      if (!b || b.index !== index || !positive(b.count) || b.firstCard !== first ||
          b.lastCard !== first + b.count - 1 || !Number.isSafeInteger(b.zipBytes) ||
          b.zipBytes < 22 || b.zipBytes > MAX_ZIP_BYTES) {
        throw new Error('Invalid upload batch or batch exceeds 1 GB. Nothing was uploaded.');
      }
      first += b.count;
      return {index, count:b.count, firstCard:b.firstCard, lastCard:b.lastCard,
        zipBytes:b.zipBytes, filename:`BulkProxyForge_Batch_${String(index+1).padStart(4,'0')}.zip`};
    });
    if (first - 1 !== value.count) throw new Error('Upload-batch card counts do not match the saved order.');
    return {protocol:2, legacy, count:value.count, zipBytes:value.zipBytes, batches};
  }
  function batchAt(meta, index) {
    if (!Number.isSafeInteger(index) || index < 0 || index >= meta.batches.length) {
      throw new Error('Requested batch is outside the saved order.');
    }
    return meta.batches[index];
  }
  globalThis.ProxyFoundryTransfer = Object.freeze({MAX_ZIP_BYTES, CHUNK_BYTES, metadata, batchAt});
})();
