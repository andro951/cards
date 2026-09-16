"""Bounded, paired ZIP views over an immutable saved order.

Only ZIP headers are rebuilt. Image payloads are read directly from the original
archive, without decoding, resizing, recompressing or making a second disk copy.
Each view is a complete ZIP (not a split-volume ZIP) with global pair filenames.
"""
from __future__ import annotations

import bisect
import os
import struct
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .domain import ValidationError

BATCH_LIMIT_BYTES = 1024 ** 3  # The existing UI's 1 GB unit (1 GiB), now per ZIP.
MAX_RANGE_BYTES = 2 * 1024 ** 2
_LOCAL = struct.Struct('<4s5H3L2H')
_CENTRAL = struct.Struct('<4s6H3L5H2L')
_END = struct.Struct('<4s4H2LH')


def _signature(stat):
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


@dataclass(frozen=True)
class Entry:
    name: bytes
    method: int
    dos_time: int
    dos_date: int
    crc: int
    size: int
    compressed_size: int
    source_offset: int

    @property
    def footprint(self):
        return _LOCAL.size + _CENTRAL.size + 2 * len(self.name) + self.compressed_size

    def local_header(self):
        return _LOCAL.pack(b'PK\x03\x04', 20, 0, self.method, self.dos_time, self.dos_date,
                           self.crc, self.compressed_size, self.size, len(self.name), 0) + self.name

    def central_header(self, offset):
        return _CENTRAL.pack(b'PK\x01\x02', 20, 20, 0, self.method, self.dos_time, self.dos_date,
                             self.crc, self.compressed_size, self.size, len(self.name),
                             0, 0, 0, 0, 0, offset) + self.name


class ZipBatch:
    def __init__(self, index, start_card, count, entries=None, original_size=None):
        self.index, self.start_card, self.count = index, start_card, count
        self.spans = []  # (virtual start, virtual end, bytes OR source-file offset)
        self.ends = []
        self.size = 0
        if original_size is not None:
            self._append(0, original_size)
            return
        central = []
        for entry in entries:
            central.append(entry.central_header(self.size))
            header = entry.local_header()
            self._append(header, len(header))
            self._append(entry.source_offset, entry.compressed_size)
        central_offset = self.size
        directory = b''.join(central)
        self._append(directory, len(directory))
        trailer = _END.pack(b'PK\x05\x06', 0, 0, len(entries), len(entries),
                            len(directory), central_offset, 0)
        self._append(trailer, len(trailer))

    def _append(self, source, length):
        if length:
            self.spans.append((self.size, self.size + length, source))
            self.size += length
            self.ends.append(self.size)

    def metadata(self):
        return {'index': self.index, 'count': self.count, 'startCard': self.start_card,
                'endCard': self.start_card + self.count - 1, 'zipBytes': self.size,
                'filename': f'BulkProxyForge_Batch_{self.index + 1:04d}.zip'}

    def read(self, stream, start, end):
        """Read a small inclusive byte range, spanning generated headers/payloads."""
        parts = []
        pos = start
        i = bisect.bisect_right(self.ends, pos)
        while pos <= end:
            lo, hi, source = self.spans[i]
            length = min(hi - pos, end - pos + 1)
            if isinstance(source, bytes):
                raw = source[pos - lo:pos - lo + length]
            else:
                stream.seek(source + pos - lo)
                raw = stream.read(length)
            if len(raw) != length:
                raise ValidationError('The saved order was truncated. Reopen or rebuild the order.')
            parts.append(raw)
            pos += length
            i += 1
        return b''.join(parts)


class PairedZipTransfer:
    def __init__(self, path, count, *, limit=None):
        self.path = Path(path)
        self.limit = BATCH_LIMIT_BYTES if limit is None else limit
        if (isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 10000
                or isinstance(self.limit, bool) or not isinstance(self.limit, int)
                or not _END.size < self.limit <= BATCH_LIMIT_BYTES):
            raise ValidationError('Invalid paired-order batch limits.')
        self.count = count
        self.signature = _signature(self.path.stat())
        self.original_size = self.signature[2]
        entries = []
        try:
            with self.path.open('rb') as stream, zipfile.ZipFile(stream) as archive:
                self._verify_stat(os.fstat(stream.fileno()))
                infos = archive.infolist()
                expected = [f'{side}/{i:06d}.png' for i in range(1, count + 1) for side in ('FRONT', 'BACK')]
                if len(infos) != 2 * count or {i.filename for i in infos} != set(expected):
                    raise ValidationError('The saved ZIP does not contain exactly one front and back for each card. Rebuild it.')
                for name in expected:
                    info = archive.getinfo(name)
                    if info.flag_bits & (1 | 64) or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                        raise ValidationError('Unsupported saved ZIP encoding. Rebuild the order in Bulk Proxy Forge.')
                    if not 0 <= info.file_size < 2 ** 32 or not 0 <= info.compress_size < 2 ** 32:
                        raise ValidationError('One image is too large for a 1 GB helper batch. No image was changed.')
                    stream.seek(info.header_offset)
                    header = stream.read(_LOCAL.size)
                    if len(header) != _LOCAL.size or header[:4] != b'PK\x03\x04':
                        raise ValidationError('The saved order has an invalid ZIP header. Rebuild it.')
                    fields = _LOCAL.unpack(header)
                    raw_name = stream.read(fields[-2])
                    if raw_name != name.encode('ascii') or fields[3] != info.compress_type:
                        raise ValidationError('The saved ZIP entry does not match its paired filename. Rebuild it.')
                    offset = info.header_offset + _LOCAL.size + fields[-2] + fields[-1]
                    if offset + info.compress_size > archive.start_dir:
                        raise ValidationError('The saved order has an invalid image range. Rebuild it.')
                    year, month, day, hour, minute, second = info.date_time
                    entries.append(Entry(name.encode('ascii'), info.compress_type,
                                         hour << 11 | minute << 5 | second // 2,
                                         (year - 1980) << 9 | month << 5 | day,
                                         info.CRC, info.file_size, info.compress_size, offset))
                self._verify_stat(os.fstat(stream.fileno()))
        except (zipfile.BadZipFile, struct.error) as exc:
            raise ValidationError('The saved paired ZIP is invalid. Rebuild the order.') from exc
        # Small orders keep their exact historical ZIP bytes and work with v1 helpers.
        if self.original_size <= self.limit:
            self.batches = [ZipBatch(0, 1, count, original_size=self.original_size)]
            return
        self.batches = []
        pending, size, start = [], _END.size, 1
        for i in range(count):
            pair = entries[2 * i:2 * i + 2]
            pair_size = sum(e.footprint for e in pair)
            if _END.size + pair_size > self.limit:
                raise ValidationError(f'Card {i + 1} and its back exceed the helper ZIP batch limit. They cannot be split; no image was changed.')
            if pending and size + pair_size > self.limit:
                self.batches.append(ZipBatch(len(self.batches), start, len(pending) // 2, pending))
                pending, size, start = [], _END.size, i + 1
            pending.extend(pair)
            size += pair_size
        if pending:
            self.batches.append(ZipBatch(len(self.batches), start, len(pending) // 2, pending))
        if any(b.size > self.limit for b in self.batches):
            raise ValidationError('A helper batch exceeds its ZIP size budget. No transfer was started.')

    def _verify_stat(self, stat):
        if _signature(stat) != self.signature:
            raise ValidationError('The saved order changed during transfer. Stop and reopen it.')

    def metadata(self):
        self._verify_stat(self.path.stat())
        return {'protocol': 2, 'count': self.count, 'zipBytes': self.original_size,
                'filename': 'BulkProxyForge_Order.zip', 'batchLimitBytes': self.limit,
                'batches': [b.metadata() for b in self.batches]}

    def batch(self, index):
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(self.batches):
            raise ValidationError('Requested batch is outside this saved order.')
        return self.batches[index]

    def read_range(self, index, start, end):
        batch = self.batch(index)
        if (any(isinstance(n, bool) or not isinstance(n, int) for n in (start, end))
                or start < 0 or start >= batch.size or end < start or end - start + 1 > MAX_RANGE_BYTES):
            raise ValidationError('Download range is outside the saved batch or is too large.')
        end = min(end, batch.size - 1)
        with self.path.open('rb') as stream:
            self._verify_stat(os.fstat(stream.fileno()))
            raw = batch.read(stream, start, end)
            self._verify_stat(os.fstat(stream.fileno()))
        return raw
