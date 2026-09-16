"""Bounded, independently valid ZIP views over an immutable saved paired order.

Only ZIP headers are rebuilt. Image payloads are read directly from the original
archive by byte range: no decoding, resizing, recompression, or second disk copy.
ZIP record layout: PKWARE APPNOTE 4.3.7, 4.3.12 and 4.3.16. Each output is below
ZIP32 limits even when the *source* order needs ZIP64 offsets.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
import os
import struct
import zipfile

from .domain import ValidationError

# Same byte threshold as the former 1 GB *order* limit, now per upload ZIP.
HELPER_ZIP_LIMIT = 1024 ** 3
MAX_RANGE = 2 * 1024 ** 2
LOCAL = struct.Struct('<IHHHHHIIIHH')
CENTRAL = struct.Struct('<IHHHHHHIIIHHHHHII')
END = struct.Struct('<IHHHHIIH')


def signature(stat):
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)


@dataclass(frozen=True)
class Segment:
    start: int
    size: int
    source: int | bytes  # Original file offset, or a small generated ZIP header.


class ZipBatch:
    def __init__(self, path, stamp, index, first, last, segments, size):
        self.path = path
        self.stamp = stamp
        self.index = index
        self.segments = segments
        self.starts = [s.start for s in segments]
        self.size = size
        self.metadata = {'index': index, 'firstCard': first, 'lastCard': last,
                         'count': last - first + 1, 'zipBytes': size,
                         'filename': f'BulkProxyForge_Batch_{index + 1:04d}.zip'}

    def read_range(self, start, length):
        if (type(start) is not int or type(length) is not int or start < 0
                or not 1 <= length <= MAX_RANGE or start + length > self.size):
            raise ValidationError('Download range is outside the upload batch or is too large.')
        out = bytearray()
        with self.path.open('rb') as stream:
            if signature(os.fstat(stream.fileno())) != self.stamp:
                raise ValidationError('The saved order changed during transfer. Stop and reopen it.')
            i = bisect_right(self.starts, start) - 1
            while len(out) < length:
                segment = self.segments[i]
                within = start + len(out) - segment.start
                take = min(segment.size - within, length - len(out))
                if isinstance(segment.source, bytes):
                    raw = segment.source[within:within + take]
                else:
                    stream.seek(segment.source + within)
                    raw = stream.read(take)
                if len(raw) != take:
                    raise ValidationError('The saved order was truncated during transfer.')
                out.extend(raw)
                i += 1
        return bytes(out)


def _make_batch(path, stamp, index, first, last, entries):
    segments, directory = [], []
    offset = 0
    for info, source_offset in entries:
        name = info.filename.encode('ascii')
        year, month, day, hour, minute, second = info.date_time
        dos_time = (hour << 11) | (minute << 5) | (second // 2)
        dos_date = ((year - 1980) << 9) | (month << 5) | day
        common = (0, info.compress_type, dos_time, dos_date, info.CRC,
                  info.compress_size, info.file_size, len(name))
        header = LOCAL.pack(0x04034B50, 20, *common, 0) + name
        directory.append(CENTRAL.pack(0x02014B50, 20, 20, *common,
                                      0, 0, 0, 0, 0, offset) + name)
        segments.append(Segment(offset, len(header), header))
        offset += len(header)
        if info.compress_size:
            segments.append(Segment(offset, info.compress_size, source_offset))
            offset += info.compress_size
    central = b''.join(directory)
    tail = central + END.pack(0x06054B50, 0, 0, len(entries), len(entries),
                              len(central), offset, 0)
    segments.append(Segment(offset, len(tail), tail))
    return ZipBatch(path, stamp, index, first, last, segments, offset + len(tail))


def plan_batches(path, count, limit=None):
    """Plan at whole FRONT/BACK pairs, including all ZIP framing overhead.

    Existing small ZIPs pass through byte-for-byte. Larger saved orders work
    without regenerating cards or rebuilding the user's downloadable archive.
    """
    limit = HELPER_ZIP_LIMIT if limit is None else limit
    if type(limit) is not int or not END.size < limit <= HELPER_ZIP_LIMIT:
        raise ValidationError('Invalid upload batch size limit.')
    if type(count) is not int or not 1 <= count <= 10000:
        raise ValidationError('Invalid paired-order card count.')
    path = Path(path)
    stamp = signature(path.stat())
    batches, pending = [], []
    size, first = END.size, 1
    try:
        with path.open('rb') as stream, zipfile.ZipFile(stream) as archive:
            infos = archive.infolist()
            expected = {f'{side}/{i:06d}.png' for i in range(1, count + 1)
                        for side in ('FRONT', 'BACK')}
            if len(infos) != len(expected) or {i.filename for i in infos} != expected:
                raise ValidationError('The saved ZIP does not contain every explicit FRONT/BACK pair exactly once.')
            # Small orders keep their exact existing ZIP, including its headers.
            if stamp[2] <= limit:
                return [ZipBatch(path, stamp, 0, 1, count,
                                 [Segment(0, stamp[2], 0)], stamp[2])]
            for i in range(1, count + 1):
                pair, cost = [], 0
                for side in ('FRONT', 'BACK'):
                    info = archive.getinfo(f'{side}/{i:06d}.png')
                    if info.flag_bits & 1 or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                        raise ValidationError('The saved ZIP uses unsupported encryption or compression. Rebuild the order.')
                    if info.file_size >= 2 ** 32 or info.compress_size >= 2 ** 32:
                        raise ValidationError(f'Card {i} has an image too large for one upload ZIP. Images were not altered.')
                    stream.seek(info.header_offset)
                    header = stream.read(LOCAL.size)
                    if len(header) != LOCAL.size:
                        raise ValidationError('The saved ZIP has a truncated file header.')
                    fields = LOCAL.unpack(header)
                    if fields[0] != 0x04034B50 or fields[3] != info.compress_type or fields[2] & 1:
                        raise ValidationError('The saved ZIP has an invalid image header.')
                    name = stream.read(fields[-2])
                    if name != info.filename.encode('ascii'):
                        raise ValidationError('The saved ZIP has mismatched image filenames.')
                    source_offset = info.header_offset + LOCAL.size + fields[-2] + fields[-1]
                    # zipfile supplies absolute offsets, including for ZIP64 sources.
                    if source_offset + info.compress_size > archive.start_dir:
                        raise ValidationError('An image extends outside the saved ZIP data.')
                    pair.append((info, source_offset))
                    cost += LOCAL.size + CENTRAL.size + 2 * len(name) + info.compress_size
                if END.size + cost > limit:
                    raise ValidationError(f'Card {i} and its back exceed the 1 GB upload ZIP limit together. The pair cannot be split; no images were resized.')
                if pending and size + cost > limit:
                    batches.append(_make_batch(path, stamp, len(batches), first, i - 1, pending))
                    pending, size, first = [], END.size, i
                pending.extend(pair)
                size += cost
            if pending:
                batches.append(_make_batch(path, stamp, len(batches), first, count, pending))
    except (zipfile.BadZipFile, EOFError, struct.error) as exc:
        raise ValidationError('The saved order ZIP is invalid. Rebuild the order.') from exc
    if signature(path.stat()) != stamp:
        raise ValidationError('The saved order changed while planning its upload batches.')
    if any(batch.size > limit for batch in batches):
        raise ValidationError('An upload ZIP would exceed the batch limit. Nothing was sent.')
    return batches
