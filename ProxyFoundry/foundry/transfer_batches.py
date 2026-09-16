"""Bounded ZIP views of an immutable paired-order archive; image bytes never change.

Only ZIP metadata is held in memory. Large batches are served as range reads of
small generated headers and the original archive's file data, with no duplicate
multi-gigabyte archives on disk. Each front/back pair stays in one batch.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from pathlib import Path
import re
import struct
import zipfile

from .domain import ValidationError

MAX_BATCH_BYTES = 1024 ** 3  # Same 1 GiB boundary as the old whole-order guard.
MAX_CHUNK_BYTES = 1024 ** 2


@dataclass(frozen=True)
class Span:
    offset: int
    size: int


class ZipView:
    def __init__(self, segments, count, first, last):
        self.segments = segments
        self.ends = []
        size = 0
        for segment in segments:
            size += len(segment) if isinstance(segment, bytes) else segment.size
            self.ends.append(size)
        self.size, self.count, self.first, self.last = size, count, first, last

    def read(self, stream, offset, length):
        result = bytearray()
        i = bisect.bisect_right(self.ends, offset)
        while length > 0 and i < len(self.segments):
            start = self.ends[i - 1] if i else 0
            within = offset - start
            n = min(length, self.ends[i] - offset)
            segment = self.segments[i]
            if isinstance(segment, bytes):
                chunk = segment[within:within + n]
            else:
                stream.seek(segment.offset + within)
                chunk = stream.read(n)
            if len(chunk) != n:
                raise ValidationError('The saved order was truncated. Stop and reopen it.')
            result.extend(chunk)
            length -= n
            offset += n
            i += 1
        return bytes(result)


def _signature(stat):
    return stat.st_size, stat.st_mtime_ns, stat.st_ino


def _zip_view(entries):
    segments, central = [], []
    offset = 0
    for info, span in entries:
        name = info.filename.encode('ascii')
        year, month, day, hour, minute, second = info.date_time
        dos_time = (hour << 11) | (minute << 5) | (second // 2)
        dos_date = ((year - 1980) << 9) | (month << 5) | day
        local = struct.pack('<4s5H3I2H', b'PK\x03\x04', 20, 0, 0, dos_time, dos_date,
                            info.CRC, info.file_size, info.file_size, len(name), 0) + name
        central.append(struct.pack('<4s6H3I5H2I', b'PK\x01\x02', 20, 20, 0, 0,
                                   dos_time, dos_date, info.CRC, info.file_size, info.file_size,
                                   len(name), 0, 0, 0, 0, info.external_attr, offset) + name)
        segments.extend([local, span])
        offset += len(local) + span.size
    directory = b''.join(central)
    end = struct.pack('<4s4H2IH', b'PK\x05\x06', 0, 0, len(entries), len(entries),
                      len(directory), offset, 0)
    segments.extend([directory, end])
    return ZipView(segments, len(entries) // 2,
                   int(entries[0][0].filename.split('/')[1][:-4]),
                   int(entries[-1][0].filename.split('/')[1][:-4]))


class TransferBatches:
    def __init__(self, path, count, limit=None):
        self.path = Path(path)
        self.signature = _signature(self.path.stat())
        self.limit = MAX_BATCH_BYTES if limit is None else limit
        if not isinstance(self.limit, int) or not 22 < self.limit <= MAX_BATCH_BYTES:
            raise ValidationError('Invalid helper batch size.')
        if not isinstance(count, int) or not 1 <= count <= 10000:
            raise ValidationError('Invalid saved order card count.')
        self.count = count
        self.views = []
        try:
            with self.path.open('rb') as source, zipfile.ZipFile(source) as archive:
                infos = archive.infolist()
                expected = [f'{side}/{i:06d}.png' for i in range(1, count + 1) for side in ('FRONT', 'BACK')]
                if len(infos) != len(expected) or {i.filename for i in infos} != set(expected):
                    raise ValidationError('The saved ZIP does not contain exactly the expected front/back pairs.')
                # Keep the historical, byte-identical transfer for small orders.
                if self.signature[0] <= self.limit:
                    self.views = [ZipView([Span(0, self.signature[0])], count, 1, count)]
                else:
                    lookup = {i.filename: i for i in infos}
                    pending, size = [], 22  # End-of-central-directory overhead.
                    for number in range(1, count + 1):
                        pair = []
                        for side in ('FRONT', 'BACK'):
                            info = lookup[f'{side}/{number:06d}.png']
                            if info.compress_type != zipfile.ZIP_STORED or info.flag_bits & 9 or info.compress_size != info.file_size:
                                raise ValidationError('Rebuild this order: batching requires the app’s uncompressed paired ZIP format.')
                            source.seek(info.header_offset)
                            header = source.read(30)
                            if len(header) != 30 or header[:4] != b'PK\x03\x04':
                                raise ValidationError('Invalid saved ZIP entry header.')
                            name_len, extra_len = struct.unpack_from('<HH', header, 26)
                            if source.read(name_len) != info.filename.encode('ascii'):
                                raise ValidationError('The saved ZIP entry name does not match its directory.')
                            offset = info.header_offset + 30 + name_len + extra_len
                            if offset + info.file_size > archive.start_dir:
                                raise ValidationError('The saved ZIP entry is outside its data section.')
                            pair.append((info, Span(offset, info.file_size)))
                        pair_size = sum(span.size + 30 + 46 + 2 * len(info.filename) for info, span in pair)
                        if pair_size + 22 > self.limit:
                            raise ValidationError(f'Card {number} and its back cannot fit in one 1 GB ZIP. Image quality was not changed.')
                        if pending and size + pair_size > self.limit:
                            self.views.append(_zip_view(pending))
                            pending, size = [], 22
                        pending.extend(pair)
                        size += pair_size
                    if pending:
                        self.views.append(_zip_view(pending))
        except (zipfile.BadZipFile, struct.error) as exc:
            raise ValidationError('The saved order ZIP is invalid. Rebuild it before transferring.') from exc
        self._check_source()

    def _check_source(self):
        if _signature(self.path.stat()) != self.signature:
            raise ValidationError('The saved order changed during transfer. Stop and reopen it.')

    def metadata(self):
        self._check_source()
        return [{'index': i, 'count': view.count, 'zipBytes': view.size,
                 'firstCard': view.first, 'lastCard': view.last,
                 'filename': f'BulkProxyForge_{self.path.stem[:8]}_batch_{i + 1:04d}.zip'}
                for i, view in enumerate(self.views)]

    def read(self, batch, offset, length):
        if type(batch) is not int or not 0 <= batch < len(self.views):
            raise ValidationError('Invalid ZIP batch index.')
        view = self.views[batch]
        if type(offset) is not int or type(length) is not int or offset < 0 or offset >= view.size or not 1 <= length <= MAX_CHUNK_BYTES:
            raise ValidationError('Invalid or oversized ZIP batch range.')
        self._check_source()
        with self.path.open('rb') as stream:
            data = view.read(stream, offset, min(length, view.size - offset))
        self._check_source()
        return data
