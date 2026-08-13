#!/usr/bin/env python3
"""Mod project management, Mods.Cod compilation, and T3 executable patching.

T3.exe is always treated as an immutable source. Every executable build starts from the
original T3.exe and writes a fresh T3_Modded.exe containing the common Mods.Cod loader plus
all compatible executable patch manifests supplied by enabled mods.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable, Optional

MOD_FORMAT_VERSION = 1
EXEC_PATCH_FORMAT_VERSION = 1
LOAD_ORDER_FILENAME = "load_order.json"
MOD_METADATA_FILENAME = "mod.json"
MOD_FILES_DIRNAME = "files"
MOD_PATCHES_DIRNAME = "patches"
EXEC_PATCH_FILENAME = "executable.json"
COMPILED_PACK_FILENAME = "Mods.Cod"
MODDED_EXE_FILENAME = "T3_Modded.exe"
LOADER_MARKER = b"T3MODLOADER_V2\x00"
LOADER_PACK_PATH = b"mods/Mods.Cod\x00"


def safe_id(value: str, fallback: str = "mod") -> str:
    value = value.strip().lower().replace(" ", "_")
    value = re.sub(r"[^a-z0-9_.-]+", "_", value).strip("_.-")
    return value[:64] or fallback


def norm_internal_path(value: str) -> str:
    path = value.replace("\\", "/").lstrip("/")
    parts = [part for part in PurePosixPath(path).parts if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise ValueError(f"Unsafe internal path: {value}")
    return "/".join(parts)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class ModProject:
    id: str
    name: str
    folder: Path
    author: str = ""
    version: str = "1.0.0"
    description: str = ""
    enabled: bool = True
    file_count: int = 0
    patch_count: int = 0

    @property
    def metadata_path(self) -> Path:
        return self.folder / MOD_METADATA_FILENAME

    @property
    def files_path(self) -> Path:
        return self.folder / MOD_FILES_DIRNAME

    @property
    def patches_path(self) -> Path:
        return self.folder / MOD_PATCHES_DIRNAME

    @property
    def executable_patch_path(self) -> Path:
        preferred = self.patches_path / EXEC_PATCH_FILENAME
        fallback = self.folder / EXEC_PATCH_FILENAME
        return preferred if preferred.is_file() or not fallback.is_file() else fallback


@dataclass
class BuildConflict:
    path: str
    previous_mod: str
    winning_mod: str


@dataclass
class BuildResult:
    output: Path
    enabled_mods: list[str] = field(default_factory=list)
    files: int = 0
    conflicts: list[BuildConflict] = field(default_factory=list)
    sha256: str = ""


@dataclass
class ExecutablePatchApplied:
    mod_id: str
    patch_id: str
    description: str
    file_offset: int
    size: int


@dataclass
class LoaderInstallResult:
    original: Path
    output: Path
    original_sha256: str
    patched_sha256: str
    code_cave_file_offset: int
    data_cave_file_offset: int
    patches_applied: list[ExecutablePatchApplied] = field(default_factory=list)


@dataclass
class FullBuildResult:
    package: BuildResult
    executable: LoaderInstallResult


@dataclass
class _PatchWriteOwner:
    value: int
    owner: str


class ModManager:
    def __init__(self, game_folder: Path, mods_folder: Optional[Path] = None, log: Callable[[str], None] = print):
        self.game_folder = Path(game_folder).expanduser().resolve()
        self.mods_folder = Path(mods_folder).expanduser().resolve() if mods_folder else self.game_folder / "mods"
        self.log = log
        self.mods_folder.mkdir(parents=True, exist_ok=True)
        (self.mods_folder / ".compiled").mkdir(parents=True, exist_ok=True)

    @property
    def load_order_path(self) -> Path:
        return self.mods_folder / LOAD_ORDER_FILENAME

    @property
    def compiled_pack_path(self) -> Path:
        return self.mods_folder / COMPILED_PACK_FILENAME

    def _load_state(self) -> dict:
        try:
            data = json.loads(self.load_order_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("mods"), list):
                return data
        except (OSError, ValueError, TypeError):
            pass
        return {"format_version": MOD_FORMAT_VERSION, "mods": []}

    def _save_state(self, projects: Iterable[ModProject]) -> None:
        payload = {
            "format_version": MOD_FORMAT_VERSION,
            "mods": [{"id": project.id, "enabled": bool(project.enabled)} for project in projects],
        }
        temporary = self.load_order_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, self.load_order_path)

    @staticmethod
    def _count_executable_patches(path: Path) -> int:
        if not path.is_file():
            return 0
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            patches = data.get("patches", []) if isinstance(data, dict) else []
            return len(patches) if isinstance(patches, list) else 0
        except (OSError, ValueError, TypeError):
            return 0

    def discover(self) -> list[ModProject]:
        state = self._load_state()
        state_entries = {
            str(entry.get("id", "")): bool(entry.get("enabled", True))
            for entry in state.get("mods", []) if isinstance(entry, dict)
        }
        state_order = [str(entry.get("id", "")) for entry in state.get("mods", []) if isinstance(entry, dict)]
        found: dict[str, ModProject] = {}
        for folder in sorted(self.mods_folder.iterdir(), key=lambda item: item.name.lower()):
            if not folder.is_dir() or folder.name.startswith("."):
                continue
            metadata_path = folder / MOD_METADATA_FILENAME
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                continue
            mod_id = safe_id(str(metadata.get("id") or folder.name), folder.name)
            files_path = folder / MOD_FILES_DIRNAME
            preferred_patch_path = folder / MOD_PATCHES_DIRNAME / EXEC_PATCH_FILENAME
            fallback_patch_path = folder / EXEC_PATCH_FILENAME
            patch_path = (
                preferred_patch_path
                if preferred_patch_path.is_file() or not fallback_patch_path.is_file()
                else fallback_patch_path
            )
            file_count = sum(1 for item in files_path.rglob("*") if item.is_file()) if files_path.is_dir() else 0
            found[mod_id] = ModProject(
                id=mod_id,
                name=str(metadata.get("name") or mod_id),
                folder=folder,
                author=str(metadata.get("author") or ""),
                version=str(metadata.get("version") or "1.0.0"),
                description=str(metadata.get("description") or ""),
                enabled=state_entries.get(mod_id, bool(metadata.get("enabled", True))),
                file_count=file_count,
                patch_count=self._count_executable_patches(patch_path),
            )
        ordered: list[ModProject] = []
        for mod_id in state_order:
            project = found.pop(mod_id, None)
            if project:
                ordered.append(project)
        ordered.extend(sorted(found.values(), key=lambda project: project.name.lower()))
        self._save_state(ordered)
        return ordered

    def save_projects(self, projects: list[ModProject]) -> None:
        self._save_state(projects)

    def create_project(self, name: str, author: str = "", description: str = "") -> ModProject:
        mod_id = safe_id(name)
        existing_ids = {project.id for project in self.discover()}
        base = mod_id
        suffix = 2
        while mod_id in existing_ids or (self.mods_folder / mod_id).exists():
            mod_id = f"{base}_{suffix}"
            suffix += 1
        folder = self.mods_folder / mod_id
        files_path = folder / MOD_FILES_DIRNAME
        patches_path = folder / MOD_PATCHES_DIRNAME
        files_path.mkdir(parents=True, exist_ok=False)
        patches_path.mkdir(parents=True, exist_ok=True)
        metadata = {
            "format_version": MOD_FORMAT_VERSION,
            "id": mod_id,
            "name": name.strip() or mod_id,
            "author": author.strip(),
            "version": "1.0.0",
            "description": description.strip(),
        }
        (folder / MOD_METADATA_FILENAME).write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        project = ModProject(mod_id, metadata["name"], folder, metadata["author"], metadata["version"], metadata["description"], True, 0, 0)
        projects = self.discover()
        if not any(item.id == project.id for item in projects):
            projects.append(project)
        self._save_state(projects)
        return project

    def build(self, projects: Optional[list[ModProject]] = None) -> BuildResult:
        # Snapshot the current selection before removing generated state. load_order.json
        # is then recreated from this snapshot so its old contents cannot survive a build.
        projects = projects if projects is not None else self.discover()
        compiled_dir = self.mods_folder / ".compiled"
        self.log("Cleaning previous compiled mod artifacts...")
        if compiled_dir.exists():
            shutil.rmtree(compiled_dir)
        compiled_dir.mkdir(parents=True, exist_ok=True)

        pack_temporary = self.compiled_pack_path.with_suffix(".tmp")
        load_order_temporary = self.load_order_path.with_suffix(".tmp")
        for stale_path in (
            self.compiled_pack_path,
            pack_temporary,
            self.load_order_path,
            load_order_temporary,
        ):
            if stale_path.exists():
                stale_path.unlink()
        self._save_state(projects)

        enabled = [project for project in projects if project.enabled]
        if not enabled:
            raise ValueError("No enabled mods were found.")

        merged: dict[str, tuple[str, Path, str]] = {}
        conflicts: list[BuildConflict] = []
        for project in enabled:
            if not project.files_path.is_dir():
                continue
            for source in sorted(project.files_path.rglob("*")):
                if not source.is_file():
                    continue
                relative = norm_internal_path(source.relative_to(project.files_path).as_posix())
                key = relative.lower()
                if key in merged:
                    conflicts.append(BuildConflict(relative, merged[key][2], project.id))
                merged[key] = (relative, source, project.id)

        has_exec_patches = any(project.executable_patch_path.is_file() for project in enabled)
        if not merged and not has_exec_patches:
            raise ValueError("The enabled mods do not contain files/ content or executable patches.")

        # An empty ZIP is intentional for executable-only mods; the common loader still has
        # a valid Mods.Cod to open while the executable changes are applied to T3_Modded.exe.
        self.compiled_pack_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(pack_temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for _, (relative, source, _) in sorted(merged.items(), key=lambda item: item[1][0].lower()):
                archive.write(source, relative)
        os.replace(pack_temporary, self.compiled_pack_path)

        result = BuildResult(
            output=self.compiled_pack_path,
            enabled_mods=[project.id for project in enabled],
            files=len(merged),
            conflicts=conflicts,
            sha256=sha256_file(self.compiled_pack_path),
        )
        manifest = {
            "format_version": MOD_FORMAT_VERSION,
            "output": str(result.output),
            "sha256": result.sha256,
            "enabled_mods": result.enabled_mods,
            "files": result.files,
            "conflicts": [conflict.__dict__ for conflict in result.conflicts],
            "winning_files": [
                {"path": relative, "mod": mod_id}
                for relative, _, mod_id in sorted(merged.values(), key=lambda item: item[0].lower())
            ],
        }
        manifest_path = self.mods_folder / ".compiled" / "build_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        return result

    def build_all(self, projects: Optional[list[ModProject]] = None) -> FullBuildResult:
        """Build Mods.Cod and T3_Modded.exe as one recoverable operation.

        If either half fails, the previous generated pair is restored so Launch never mixes
        a new package with an older executable (or vice versa). T3.exe is never involved in
        the rollback because it is read-only input.
        """
        projects = projects if projects is not None else self.discover()
        executable_path = self.game_folder / MODDED_EXE_FILENAME
        outputs = (self.compiled_pack_path, executable_path)
        existed_before = {output: output.exists() for output in outputs}
        staged: list[tuple[Path, Path]] = []

        try:
            # A fixed backup name can be left behind by an interrupted build and may still
            # be held open briefly by antivirus/indexing software on Windows. A unique name
            # makes that stale file irrelevant to the next build.
            for output in outputs:
                if not existed_before[output]:
                    continue
                backup = output.with_name(
                    f"{output.name}.build_backup.{os.getpid()}.{uuid.uuid4().hex}"
                )
                os.replace(output, backup)
                staged.append((output, backup))

            package = self.build(projects)
            executable = self.install_loader(projects)
        except Exception as build_error:
            rollback_errors: list[str] = []

            # Restore staged outputs directly over any partially generated replacements.
            # Outputs that did not exist before the build are simply removed.
            for output, backup in reversed(staged):
                try:
                    if backup.exists():
                        os.replace(backup, output)
                except OSError as exc:
                    rollback_errors.append(f"{backup} -> {output}: {exc}")
            for output in outputs:
                if existed_before[output]:
                    continue
                try:
                    if output.exists():
                        output.unlink()
                except OSError as exc:
                    rollback_errors.append(f"remove {output}: {exc}")

            if rollback_errors:
                details = "; ".join(rollback_errors)
                raise RuntimeError(
                    f"Build failed ({build_error}) and rollback was incomplete: {details}"
                ) from build_error
            raise
        else:
            # Cleanup is deliberately best-effort. The newly built pair is valid even if
            # Windows temporarily keeps an old backup open after a successful replacement.
            for _, backup in staged:
                try:
                    if backup.exists():
                        backup.unlink()
                except OSError as exc:
                    self.log(f"Warning: could not remove old build backup {backup}: {exc}")
            return FullBuildResult(package=package, executable=executable)

    def _read_patch_manifest(self, project: ModProject) -> list[dict]:
        path = project.executable_patch_path
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise ValueError(f"{project.id}: invalid patches/executable.json: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"{project.id}: patches/executable.json must contain a JSON object.")
        version = int(data.get("format_version", EXEC_PATCH_FORMAT_VERSION))
        if version != EXEC_PATCH_FORMAT_VERSION:
            raise ValueError(f"{project.id}: unsupported executable patch format_version {version}.")
        target = str(data.get("target", "T3.exe"))
        if target.lower() != "t3.exe":
            raise ValueError(f"{project.id}: executable patches may only target T3.exe.")
        patches = data.get("patches", [])
        if not isinstance(patches, list):
            raise ValueError(f"{project.id}: 'patches' must be a list.")
        return [patch for patch in patches if isinstance(patch, dict)]

    def install_loader(self, projects: Optional[list[ModProject]] = None) -> LoaderInstallResult:
        original = self.game_folder / "T3.exe"
        if not original.is_file():
            raise FileNotFoundError(f"T3.exe was not found in {self.game_folder}")
        output = self.game_folder / MODDED_EXE_FILENAME
        original_bytes = original.read_bytes()
        data = bytearray(original_bytes)
        original_hash = hashlib.sha256(original_bytes).hexdigest()

        pe = _PEImage(original_bytes)
        write_map: dict[int, _PatchWriteOwner] = {}

        # Common loader patch. This is rebuilt from the pristine T3.exe every time.
        language_string_offset = original_bytes.find(b"Language.cod\x00")
        if language_string_offset < 0:
            raise ValueError("Unsupported T3.exe: Language.cod string was not found.")
        language_va = pe.file_offset_to_va(language_string_offset)
        signature = b"\x53\x68" + struct.pack("<I", language_va)
        package_sequence_offset = original_bytes.find(signature, pe.text.raw_offset, pe.text.raw_offset + pe.text.raw_size)
        if package_sequence_offset < 0:
            raise ValueError("Unsupported T3.exe: package-loading sequence was not found.")
        original_call_offset = package_sequence_offset + len(signature)
        if original_bytes[original_call_offset] != 0xE8:
            raise ValueError("Unsupported T3.exe: AddPack call is not in the expected location.")
        original_call_va = pe.file_offset_to_va(original_call_offset)
        rel = struct.unpack_from("<i", original_bytes, original_call_offset + 1)[0]
        add_pack_va = original_call_va + 5 + rel

        data_cave_offset = _find_zero_cave(original_bytes, pe.data.raw_offset, pe.data.raw_offset + pe.data.raw_size, len(LOADER_PACK_PATH) + len(LOADER_MARKER) + 16)
        if data_cave_offset is None:
            raise ValueError("Unsupported T3.exe: no safe data cave was found.")
        data_payload = LOADER_PACK_PATH + LOADER_MARKER
        _apply_owned_bytes(data, write_map, data_cave_offset, data_payload, "T3-ModTools loader:data")
        pack_path_va = pe.file_offset_to_va(data_cave_offset)

        code_cave_offset = _find_zero_cave(original_bytes, pe.text.raw_offset, pe.text.raw_offset + pe.text.raw_size, 64, prefer_last=True)
        if code_cave_offset is None:
            raise ValueError("Unsupported T3.exe: no safe executable code cave was found.")
        code_cave_va = pe.file_offset_to_va(code_cave_offset)

        code = bytearray()
        code += b"\x68" + struct.pack("<I", 0)
        code += b"\x68" + struct.pack("<I", pack_path_va)
        call_site_va = code_cave_va + len(code)
        code += b"\xE8" + struct.pack("<i", add_pack_va - (call_site_va + 5))
        code += b"\x83\xC4\x08"
        code += b"\x53"
        code += b"\x68" + struct.pack("<I", language_va)
        jump_site_va = code_cave_va + len(code)
        code += b"\xE9" + struct.pack("<i", original_call_va - (jump_site_va + 5))
        code += b"\x90" * (64 - len(code))
        _apply_owned_bytes(data, write_map, code_cave_offset, bytes(code), "T3-ModTools loader:code")

        patch_va = pe.file_offset_to_va(package_sequence_offset)
        jump_to_cave = b"\xE9" + struct.pack("<i", code_cave_va - (patch_va + 5)) + b"\x90"
        _apply_owned_bytes(data, write_map, package_sequence_offset, jump_to_cave, "T3-ModTools loader:entry")

        enabled = [project for project in (projects if projects is not None else self.discover()) if project.enabled]
        applied: list[ExecutablePatchApplied] = []
        for project in enabled:
            for index, patch in enumerate(self._read_patch_manifest(project), start=1):
                applied.append(self._apply_manifest_patch(original_bytes, data, pe, write_map, project, patch, index))

        temporary = output.with_suffix(".tmp")
        temporary.write_bytes(data)
        os.replace(temporary, output)
        result = LoaderInstallResult(
            original=original,
            output=output,
            original_sha256=original_hash,
            patched_sha256=sha256_file(output),
            code_cave_file_offset=code_cave_offset,
            data_cave_file_offset=data_cave_offset,
            patches_applied=applied,
        )
        loader_manifest = {
            "format_version": 2,
            "original": str(result.original),
            "output": str(result.output),
            "original_sha256": result.original_sha256,
            "patched_sha256": result.patched_sha256,
            "pack": "mods/Mods.Cod",
            "priority": "loaded before Language.cod, Patch116.Cod, and Game.Cod",
            "original_modified": False,
            "executable_patches": [patch.__dict__ for patch in result.patches_applied],
        }
        (self.mods_folder / ".compiled").mkdir(parents=True, exist_ok=True)
        (self.mods_folder / ".compiled" / "loader_manifest.json").write_text(
            json.dumps(loader_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return result

    def _apply_manifest_patch(
        self,
        original_bytes: bytes,
        data: bytearray,
        pe: "_PEImage",
        write_map: dict[int, _PatchWriteOwner],
        project: ModProject,
        patch: dict,
        index: int,
    ) -> ExecutablePatchApplied:
        patch_type = str(patch.get("type", "aob_replace"))
        if patch_type not in ("aob_replace", "aob_write"):
            raise ValueError(f"{project.id}: unsupported executable patch type '{patch_type}'.")
        patch_id = safe_id(str(patch.get("id") or f"patch_{index}"), f"patch_{index}")
        description = str(patch.get("description") or patch_id)
        pattern = _parse_hex_pattern(str(patch.get("pattern", "")), allow_wildcards=True, field="pattern")
        if not pattern:
            raise ValueError(f"{project.id}/{patch_id}: pattern cannot be empty.")
        if all(token is None for token in pattern):
            raise ValueError(f"{project.id}/{patch_id}: pattern cannot contain only wildcards.")
        expected_matches = int(patch.get("expected_matches", 1))
        if expected_matches < 1:
            raise ValueError(f"{project.id}/{patch_id}: expected_matches must be at least 1.")
        section_name = str(patch.get("section", ".text"))
        start, end = pe.section_range(section_name, len(original_bytes))
        matches = _find_pattern(original_bytes, pattern, start, end)
        if len(matches) != expected_matches:
            raise ValueError(
                f"{project.id}/{patch_id}: expected {expected_matches} match(es) in {section_name}, found {len(matches)}. "
                "T3.exe may be incompatible or the patch signature is ambiguous."
            )
        if expected_matches != 1:
            raise ValueError(f"{project.id}/{patch_id}: v1 currently requires expected_matches = 1 for safe patching.")

        match_offset = matches[0]
        replacement = _parse_hex_pattern(
            str(patch.get("replacement", "")), allow_wildcards=True, field="replacement"
        )
        if patch_type == "aob_replace":
            if len(pattern) != len(replacement):
                raise ValueError(f"{project.id}/{patch_id}: pattern and replacement must have the same byte length.")
            offset = match_offset
        else:
            expected_fill = str(patch.get("expected_fill", "")).strip()
            if expected_fill:
                fill = _parse_hex_pattern(expected_fill, allow_wildcards=False, field="expected_fill")
                if len(fill) != 1:
                    raise ValueError(f"{project.id}/{patch_id}: expected_fill must contain exactly one byte.")
                expected = fill * len(replacement)
            else:
                expected = _parse_hex_pattern(
                    str(patch.get("expected", "")), allow_wildcards=True, field="expected"
                )
            if not expected:
                raise ValueError(f"{project.id}/{patch_id}: expected cannot be empty for aob_write.")
            if all(token is None for token in expected):
                raise ValueError(f"{project.id}/{patch_id}: expected cannot contain only wildcards.")
            if len(expected) != len(replacement):
                raise ValueError(f"{project.id}/{patch_id}: expected and replacement must have the same byte length.")
            raw_write_offset = patch.get("write_offset", 0)
            try:
                write_offset = int(str(raw_write_offset), 0)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"{project.id}/{patch_id}: write_offset must be a decimal or 0x-prefixed integer."
                ) from exc
            offset = match_offset + write_offset
            if offset < start or offset + len(expected) > end:
                raise ValueError(
                    f"{project.id}/{patch_id}: aob_write target is outside section {section_name}."
                )
            mismatches = [
                position
                for position, token in enumerate(expected)
                if token is not None and original_bytes[offset + position] != token
            ]
            if mismatches:
                first = mismatches[0]
                raise ValueError(
                    f"{project.id}/{patch_id}: expected bytes do not match at file offset "
                    f"0x{offset + first:X}. T3.exe may be incompatible."
                )

        replacement_bytes = bytes(
            original_bytes[offset + i] if token is None else token
            for i, token in enumerate(replacement)
        )
        owner = f"{project.id}/{patch_id}"
        _apply_owned_bytes(data, write_map, offset, replacement_bytes, owner)
        return ExecutablePatchApplied(project.id, patch_id, description, offset, len(replacement_bytes))

    def launch_modded(self) -> subprocess.Popen:
        executable = self.game_folder / MODDED_EXE_FILENAME
        if not executable.is_file():
            raise FileNotFoundError("T3_Modded.exe does not exist. Build the enabled mods first.")
        if not self.compiled_pack_path.is_file():
            raise FileNotFoundError("mods/Mods.Cod does not exist. Build the enabled mods first.")
        return subprocess.Popen([str(executable)], cwd=str(self.game_folder))


@dataclass
class _PESection:
    name: str
    virtual_address: int
    virtual_size: int
    raw_offset: int
    raw_size: int


class _PEImage:
    def __init__(self, data: bytes):
        if data[:2] != b"MZ":
            raise ValueError("Unsupported executable: missing MZ header.")
        pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
        if data[pe_offset:pe_offset + 4] != b"PE\x00\x00":
            raise ValueError("Unsupported executable: missing PE header.")
        coff = pe_offset + 4
        machine, section_count, _, _, _, optional_size, _ = struct.unpack_from("<HHIIIHH", data, coff)
        if machine != 0x14C:
            raise ValueError("Unsupported executable: expected 32-bit x86 T3.exe.")
        optional = coff + 20
        magic = struct.unpack_from("<H", data, optional)[0]
        if magic != 0x10B:
            raise ValueError("Unsupported executable: expected PE32.")
        self.image_base = struct.unpack_from("<I", data, optional + 28)[0]
        section_table = optional + optional_size
        self.sections: list[_PESection] = []
        for index in range(section_count):
            offset = section_table + index * 40
            name = data[offset:offset + 8].split(b"\x00", 1)[0].decode("ascii", errors="replace")
            virtual_size, virtual_address, raw_size, raw_offset = struct.unpack_from("<IIII", data, offset + 8)
            self.sections.append(_PESection(name, virtual_address, virtual_size, raw_offset, raw_size))
        by_name = {section.name: section for section in self.sections}
        if ".text" not in by_name or ".data" not in by_name:
            raise ValueError("Unsupported executable: .text or .data section is missing.")
        self.text = by_name[".text"]
        self.data = by_name[".data"]

    def file_offset_to_va(self, offset: int) -> int:
        for section in self.sections:
            if section.raw_offset <= offset < section.raw_offset + section.raw_size:
                return self.image_base + section.virtual_address + (offset - section.raw_offset)
        raise ValueError(f"File offset 0x{offset:X} is not inside a loaded PE section.")

    def section_range(self, name: str, file_size: int) -> tuple[int, int]:
        if name.lower() in ("all", "*", "file"):
            return 0, file_size
        for section in self.sections:
            if section.name.lower() == name.lower():
                return section.raw_offset, min(file_size, section.raw_offset + section.raw_size)
        raise ValueError(f"Unknown PE section '{name}'.")


def _parse_hex_pattern(value: str, allow_wildcards: bool, field: str) -> list[Optional[int]]:
    compact = value.replace(",", " ").strip()
    if not compact:
        return []
    result: list[Optional[int]] = []
    for token in compact.split():
        token = token.strip()
        if token in ("?", "??"):
            if not allow_wildcards:
                raise ValueError(f"Wildcards are not allowed in {field}.")
            result.append(None)
            continue
        if not re.fullmatch(r"[0-9A-Fa-f]{2}", token):
            raise ValueError(f"Invalid byte '{token}' in {field}; use hexadecimal bytes or ??.")
        result.append(int(token, 16))
    return result


def _find_pattern(data: bytes, pattern: list[Optional[int]], start: int, end: int) -> list[int]:
    width = len(pattern)
    if width == 0 or end - start < width:
        return []
    matches: list[int] = []
    limit = end - width + 1
    for offset in range(start, limit):
        if all(token is None or data[offset + i] == token for i, token in enumerate(pattern)):
            matches.append(offset)
    return matches


def _apply_owned_bytes(
    data: bytearray,
    write_map: dict[int, _PatchWriteOwner],
    offset: int,
    payload: bytes,
    owner: str,
) -> None:
    if offset < 0 or offset + len(payload) > len(data):
        raise ValueError(f"{owner}: patch write is outside T3.exe.")
    for index, value in enumerate(payload):
        position = offset + index
        previous = write_map.get(position)
        if previous is not None and previous.value != value:
            raise ValueError(
                f"Executable patch conflict at file offset 0x{position:X}: "
                f"{previous.owner} writes {previous.value:02X}, but {owner} writes {value:02X}."
            )
    for index, value in enumerate(payload):
        position = offset + index
        data[position] = value
        write_map.setdefault(position, _PatchWriteOwner(value, owner))


def _find_zero_cave(data: bytes, start: int, end: int, minimum: int, prefer_last: bool = False) -> Optional[int]:
    runs: list[tuple[int, int]] = []
    index = start
    while index < end:
        if data[index] != 0:
            index += 1
            continue
        run_start = index
        while index < end and data[index] == 0:
            index += 1
        length = index - run_start
        if length >= minimum:
            runs.append((run_start, length))
    if not runs:
        return None
    if prefer_last:
        return max(runs, key=lambda item: item[0])[0]
    return max(runs, key=lambda item: item[1])[0]


def open_in_file_manager(path: Path) -> None:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True) if path.suffix == "" and not path.exists() else None
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
