"""Publish a generator's validated assets without renaming Windows directories.

Use after all conversion/validation succeeds. Unchanged files are left alone;
changed files and metadata are replaced individually, with rollback on failure.
Only files recorded by this helper can become obsolete; user additions survive.
"""
from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import time
import warnings
from typing import Mapping

OWNERSHIP_FILE = ".generated-assets.json"


def _path(root: Path, relative: str) -> Path:
    relative = relative.replace("\\", "/")
    parts = PurePosixPath(relative).parts
    if not parts or relative.startswith("/") or any(p in ("..", ".") or ":" in p for p in parts):
        raise ValueError(f"Unsafe generated path: {relative}")
    target = root.joinpath(*parts)
    for entry in (target, *target.parents):
        if entry == root:
            break
        if entry.is_symlink() or (entry.exists() and getattr(entry.lstat(), "st_file_attributes", 0) & 0x400):
            raise ValueError(f"Generated paths cannot traverse links: {entry}")
    target.resolve().relative_to(root)
    return target


def _replace(source: Path, target: Path) -> None:
    # Antivirus/indexers may briefly hold a file. Permanent locks still fail and
    # trigger rollback; no chmod, elevation or fallback to in-place truncation.
    for attempt in range(5):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(.05 * 2 ** attempt)


def publish_generated_assets(
    project_root: Path,
    staged_files: Path,
    metadata: Mapping[str, bytes],
) -> int:
    """Publish files/ plus root-relative metadata as one recoverable operation.

    The caller owns staged_files. All content must already be validated. The
    project/files directory and its subdirectories retain their identities.
    Returns the number of changed/removed files, including metadata.
    """
    root = Path(project_root).resolve()
    stage = Path(staged_files).resolve()
    if not stage.is_dir():
        raise ValueError(f"Missing generated asset staging directory: {stage}")
    desired = {}
    owned = []
    for source in sorted(stage.rglob("*")):
        relative = source.relative_to(stage).as_posix()
        _path(stage, relative)
        if source.is_file():
            key = "files/" + relative
            desired[key] = source
            owned.append(key)
    for key, value in metadata.items():
        if key == OWNERSHIP_FILE or key.replace("\\", "/").lower().startswith("files/"):
            raise ValueError(f"Metadata overlaps managed assets: {key}")
        if not isinstance(value, bytes):
            raise TypeError(f"Metadata must be bytes: {key}")
        desired[key] = value
    if len({k.replace("\\", "/").lower() for k in desired}) != len(desired):
        raise ValueError("Case-insensitive duplicate generated paths")
    ownership = _path(root, OWNERSHIP_FILE)
    previous = []
    if ownership.exists():
        record = json.loads(ownership.read_text(encoding="utf-8"))
        if record.get("format_version") != 1:
            raise ValueError("Unsupported generated asset ownership manifest")
        previous = record["files"]
        if not isinstance(previous, list) or any(not isinstance(k, str) or not k.startswith("files/") for k in previous):
            raise ValueError("Invalid generated asset ownership manifest")
    desired[OWNERSHIP_FILE] = (json.dumps({"format_version": 1, "files": owned}, indent=2) + "\n").encode()
    owned_keys = {key.lower() for key in owned}
    obsolete = {key for key in previous if key.lower() not in owned_keys}
    changes = []
    # Preflight every destination before touching any existing content.
    for key in sorted(set(desired) | obsolete):
        target = _path(root, key)
        if target.exists() and not target.is_file():
            raise ValueError(f"Generated destination is not a file: {target}")
        source = desired.get(key)
        payload = source.read_bytes() if isinstance(source, Path) else source
        if target.exists() and payload == target.read_bytes():
            continue
        if payload is not None or target.exists():
            changes.append((key, target, payload))
    if not changes:
        return 0
    backup = Path(tempfile.mkdtemp(prefix=".generated_backup_", dir=root))
    backups = {}
    applied = []
    keep_backup = False
    try:
        # Copy all previous bytes before the first publication. No open handles
        # survive this phase; directory locks do not prevent per-file replace.
        for index, (key, target, _) in enumerate(changes):
            if target.exists():
                saved = backup / str(index)
                shutil.copy2(target, saved)
                backups[key] = saved
        (backup / "paths.json").write_text(json.dumps({k: v.name for k, v in backups.items()}), encoding="utf-8")
        for key, target, payload in changes:
            target.parent.mkdir(parents=True, exist_ok=True)
            if payload is None:
                target.unlink()
            else:
                fd, temporary = tempfile.mkstemp(prefix=".generated_", suffix=".tmp", dir=target.parent)
                temporary = Path(temporary)
                try:
                    with os.fdopen(fd, "wb") as handle:
                        handle.write(payload)
                    _replace(temporary, target)
                finally:
                    temporary.unlink(missing_ok=True)
            applied.append((key, target))
    except BaseException as failure:
        errors = []
        for key, target in reversed(applied):
            try:
                if key in backups:
                    _replace(backups[key], target)
                else:
                    target.unlink(missing_ok=True)
            except OSError as exc:
                errors.append(f"{key}: {exc}")
        if errors:
            keep_backup = True
            raise RuntimeError(f"Generated asset rollback needs recovery from {backup}: {'; '.join(errors)}") from failure
        raise
    finally:
        if not keep_backup:
            # Resolve the cleanup target and keep it within this project.
            resolved = backup.resolve()
            resolved.relative_to(root)
            if resolved == root:
                raise ValueError("Invalid generated backup cleanup path")
            try:
                shutil.rmtree(resolved)
            except OSError as exc:
                warnings.warn(f"Generated backup cleanup deferred: {resolved}: {exc}")
    return len(changes)
