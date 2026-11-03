"""Disposable content-addressed build cache; never a source of game assets.

ZipFile has no public API for copying compressed members. CachedZipFile isolates
the small raw-copy adapter here; ZipFile still owns ZIP64 and central-directory
serialization. Cached members are verified against source SHA-256 before reuse.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
import zipfile
import zlib


CACHE_VERSION = 1
IGNORED_DIRS = {"__pycache__", ".git", ".pytest_cache"}


_active_scan = ContextVar("t3_build_scan", default=None)


class ScanCache:
    """Memoize a read-only phase, never trust timestamps or persist source hashes.

    Writers and final validation are explicit phase boundaries. A new build gets
    a fresh cache even when the same manager instance is reused by the GUI.
    """
    def __init__(self):
        self.clear()

    def clear(self):
        self.hashes = {}
        self.snapshots = {}


@contextmanager
def scan_session():
    existing = _active_scan.get()
    if existing is not None:
        yield existing
        return
    scan = ScanCache()
    token = _active_scan.set(scan)
    try:
        yield scan
    finally:
        _active_scan.reset(token)


def scan_operation(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with scan_session():
            return function(*args, **kwargs)
    return wrapped


def invalidate_scan():
    scan = _active_scan.get()
    if scan is not None:
        scan.clear()


def _scan_key(path):
    return os.path.normcase(os.path.abspath(path))


def file_hash(path, *, fresh=False):
    scan = _active_scan.get()
    key = _scan_key(path)
    if not fresh and scan is not None and key in scan.hashes:
        return scan.hashes[key]
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    result = digest.hexdigest()
    if scan is not None:
        scan.hashes[key] = result
    return result


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def snapshot(path):
    """Hash bytes, not timestamps; include additions, deletions and spelling."""
    scan = _active_scan.get()
    key = _scan_key(path)
    if scan is not None and key in scan.snapshots:
        return scan.snapshots[key]
    result = _snapshot(path)
    if scan is not None:
        scan.snapshots[key] = result
    return result


def _snapshot(path):
    path = Path(path)
    if path.is_file():
        return file_hash(path)
    if not path.exists():
        return None
    entries = {}
    for current, directories, files in os.walk(path, followlinks=False):
        relative = Path(current).relative_to(path)
        # Everything under files/ is an asset, even names resembling Python caches.
        asset_tree = bool(relative.parts and relative.parts[0] == "files")
        directories[:] = sorted(d for d in directories if asset_tree or d not in IGNORED_DIRS)
        for directory in directories:
            candidate = Path(current) / directory
            if candidate.is_symlink() or getattr(candidate, "is_junction", lambda: False)():
                raise ValueError(f"Cannot cache a linked directory: {candidate}")
        for name in sorted(files):
            if not asset_tree and name.endswith((".pyc", ".pyo")):
                continue
            source = Path(current) / name
            entries[source.relative_to(path).as_posix()] = file_hash(source)
    return entries


def read_record(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) and value.get("version") == CACHE_VERSION else {}
    except (OSError, ValueError, TypeError):
        return {}


def write_record(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({**value, "version": CACHE_VERSION}, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class CachedZipFile(zipfile.ZipFile):
    def copy_compressed(self, source, member, name):
        info = copy.copy(member)
        info.filename = name
        info.orig_filename = name
        info.flag_bits = 0  # Cache entries are unencrypted and have no data descriptor.
        info.extra = b""  # Regenerate ZIP64 fields for the destination offsets.
        self._writecheck(info)
        self._didModify = True
        self.fp.seek(self.start_dir)
        info.header_offset = self.fp.tell()
        needs_zip64 = max(info.file_size, info.compress_size) > zipfile.ZIP64_LIMIT
        self.fp.write(info.FileHeader(needs_zip64))
        source.fp.seek(member.header_offset)
        header = source.fp.read(30)
        if len(header) != 30 or header[:4] != b"PK\x03\x04":
            raise zipfile.BadZipFile("Invalid cached local header")
        name_size, extra_size = struct.unpack_from("<HH", header, 26)
        source.fp.seek(name_size + extra_size, 1)
        remaining = info.compress_size
        while remaining:
            block = source.fp.read(min(remaining, 1024 * 1024))
            if not block:
                raise zipfile.BadZipFile("Truncated cached member")
            self.fp.write(block)
            remaining -= len(block)
        self.start_dir = self.fp.tell()
        self.filelist.append(info)
        self.NameToInfo[info.filename] = info


class AssetCache:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.reused = 0
        self.compressed = 0

    @staticmethod
    def _valid(path, digest):
        try:
            with zipfile.ZipFile(path) as archive:
                if archive.namelist() != ["asset"]:
                    return False
                item = archive.getinfo("asset")
                if item.compress_type != zipfile.ZIP_DEFLATED or item.flag_bits & 9:
                    return False
                result = hashlib.sha256()
                with archive.open(item) as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        result.update(block)
                return result.hexdigest() == digest
        except (OSError, ValueError, EOFError, zipfile.BadZipFile, RuntimeError, zlib.error):
            return False

    def add(self, archive, name, source=None, data=None):
        digest = hashlib.sha256(data).hexdigest() if data is not None else file_hash(source)
        cached = self.folder / (digest + ".zip")
        if self._valid(cached, digest):
            self.reused += 1
        else:
            fd, temporary = tempfile.mkstemp(dir=self.folder, suffix=".tmp")
            os.close(fd)
            try:
                with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as target:
                    info = zipfile.ZipInfo("asset")
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info._compresslevel = 9
                    info.file_size = len(data) if data is not None else Path(source).stat().st_size
                    # Fixed metadata makes a cold and warm build byte-identical.
                    with target.open(info, "w") as output:
                        if data is not None:
                            output.write(data)
                        else:
                            with Path(source).open("rb") as input_stream:
                                shutil.copyfileobj(input_stream, output, 1024 * 1024)
                if not self._valid(temporary, digest):
                    raise ValueError(f"Asset changed during compilation: {source}")
                os.replace(temporary, cached)
            finally:
                Path(temporary).unlink(missing_ok=True)
            self.compressed += 1
        with zipfile.ZipFile(cached) as previous:
            archive.copy_compressed(previous, previous.getinfo("asset"), name)
