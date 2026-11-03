#!/usr/bin/env python3
"""Mod project management, Mods.Cod compilation, and T3 executable patching.

T3.exe is always treated as an immutable source. Every executable build starts from the
original T3.exe and writes a fresh T3_Modded.exe containing the common Mods.Cod loader plus
all compatible executable patch manifests supplied by enabled mods. Optional Ai.Dll patches
are written to A2.Dll and T3_Modded.exe is redirected to that generated copy; Ai.Dll also
remains immutable.
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
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable, Optional

from t3_log_i18n import log_tr, write_diagnostic
from t3_loader import build_loader_patch
from t3_anm_compat import analyze as analyze_anm_compatibility, CompatibilityPlan, effective_mod_files
import t3_anm_runtime
import t3_material_runtime
import t3_build_cache as build_cache

MOD_FORMAT_VERSION = 1
EXEC_PATCH_FORMAT_VERSION = 1
LOAD_ORDER_FILENAME = "load_order.json"
DATA_FOLDER_NAME = "modtools_data"
MOD_METADATA_FILENAME = "mod.json"
MOD_FILES_DIRNAME = "files"
MOD_PATCHES_DIRNAME = "patches"
EXEC_PATCH_FILENAME = "executable.json"
RUNTIME_PATCH_FILENAME = "runtime_patch.py"
RUNTIME_PATCH_TIMEOUT_SECONDS = 60
COMPILED_PACK_FILENAME = "Mods.Cod"
MODDED_EXE_FILENAME = "T3_Modded.exe"
AI_DLL_FILENAME = "Ai.Dll"
MODDED_AI_DLL_FILENAME = "A2.Dll"
AI_DLL_IMPORT_NAME = b"Ai.Dll\x00"
MODDED_AI_DLL_IMPORT_NAME = b"A2.Dll\x00"
LOADER_MARKER = b"T3MODLOADER_V2\x00"
LEGACY_LOADER_PACK_PATH = b"mods/Mods.Cod\x00"
LOADER_PACK_PATH = b"modtools_data/Mods.Cod\x00"


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
    return build_cache.file_hash(path)


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
    generates_assets: bool = False

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
class ModPackResult:
    project: ModProject
    sources: list[str]
    conflicts: list[BuildConflict]


@dataclass
class BuildResult:
    output: Path
    enabled_mods: list[str] = field(default_factory=list)
    files: int = 0
    conflicts: list[BuildConflict] = field(default_factory=list)
    sha256: str = ""
    compressed_files: int = 0
    reused_files: int = 0


@dataclass
class ExecutablePatchApplied:
    mod_id: str
    patch_id: str
    description: str
    file_offset: int
    size: int
    target: str = "T3.exe"


@dataclass
class LoaderInstallResult:
    original: Path
    output: Path
    original_sha256: str
    patched_sha256: str
    code_cave_file_offset: int
    data_cave_file_offset: int
    patches_applied: list[ExecutablePatchApplied] = field(default_factory=list)
    ai_original: Optional[Path] = None
    ai_output: Optional[Path] = None
    ai_original_sha256: str = ""
    ai_patched_sha256: str = ""


@dataclass
class FullBuildResult:
    package: BuildResult
    executable: LoaderInstallResult


@dataclass
class _PatchWriteOwner:
    value: int
    owner: str


class ModManager:
    def __init__(
        self, game_folder: Path, mods_folder: Optional[Path] = None,
        log: Callable[[str], None] = print, *, language: str = "en",
    ):
        self.game_folder = Path(game_folder).expanduser().resolve()
        self.mods_folder = Path(mods_folder).expanduser().resolve() if mods_folder else self.game_folder / "mods"
        self.log = log
        self.language = language
        self.data_folder = self.game_folder / DATA_FOLDER_NAME
        # A custom project folder has its own selection/order, but all builds for a
        # given game share the one archive path embedded in that game's loader.
        self.state_folder = self.data_folder
        if self.mods_folder != (self.game_folder / "mods").resolve():
            identity = os.path.normcase(str(self.mods_folder)).encode("utf-8")
            self.state_folder = self.data_folder / "load_orders" / hashlib.sha256(identity).hexdigest()[:16]
        self.mods_folder.mkdir(parents=True, exist_ok=True)
        self.state_folder.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_data()
        self.compiled_dir.mkdir(parents=True, exist_ok=True)

    def _say(self, key: str, **values: object) -> None:
        self.log(log_tr(getattr(self, "language", "en"), key, **values))

    @property
    def compiled_dir(self) -> Path:
        return self.data_folder / ".compiled"

    @property
    def load_order_path(self) -> Path:
        return self.state_folder / LOAD_ORDER_FILENAME

    @property
    def compiled_pack_path(self) -> Path:
        return self.data_folder / COMPILED_PACK_FILENAME

    @property
    def cache_folder(self) -> Path:
        # Kept outside .compiled so transactional staging never discards reusable assets.
        return self.data_folder / ".build_cache"

    def _shared_build_inputs(self) -> dict:
        return {
            "version": build_cache.CACHE_VERSION,
            "python": [sys.executable, sys.version],
            "tools": {p.name: sha256_file(p) for p in sorted(Path(__file__).parent.glob("*.py"))},
            "game": {name: build_cache.snapshot(self.game_folder / name) for name in
                     ("T3.exe", AI_DLL_FILENAME, "Game.cod", "Language.cod", "Patch116.Cod")},
        }

    def _runtime_cache_inputs(self, project, projects, shared):
        """Only declared deterministic generators may skip execution.

        Unknown third-party scripts keep the conservative behavior. The declaration
        covers external files/directories; the entire project is always hashed.
        """
        if not project.metadata_path.is_file():
            return None
        metadata = json.loads(project.metadata_path.read_text(encoding="utf-8-sig"))
        policy = metadata.get("runtime_cache")
        if not isinstance(policy, dict):
            return None
        dependencies = policy.get("dependencies", [])
        config_paths = policy.get("config_paths", {})
        if not isinstance(dependencies, list) or not all(isinstance(p, str) for p in dependencies):
            raise ValueError(f"{project.id}: runtime_cache.dependencies must be a list of paths")
        if not isinstance(config_paths, dict):
            raise ValueError(f"{project.id}: runtime_cache.config_paths must be an object")
        paths = [project.folder / p for p in dependencies]
        for config_name, keys in config_paths.items():
            config = json.loads((project.folder / config_name).read_text(encoding="utf-8-sig"))
            if not isinstance(keys, list) or not all(isinstance(key, str) for key in keys):
                raise ValueError(f"{project.id}: runtime_cache config keys must be a list")
            for key in keys:
                paths.append(project.folder / config[key])
        inputs = {
            "shared": shared,
            "project": str(project.folder.resolve()),
            "files": build_cache.snapshot(project.folder),
            "dependencies": {str(p.resolve()): build_cache.snapshot(p) for p in paths},
        }
        if policy.get("enabled_mods"):
            inputs["mods"] = [(p.id, str(p.folder.resolve()), build_cache.snapshot(p.folder))
                              for p in projects if p.enabled and p is not project]
            inputs["selection"] = [(p.id, p.enabled) for p in projects]
            # Generators currently read the on-disk selection too. Never reuse a
            # generator result across a change to either representation.
            inputs["load_order"] = build_cache.snapshot(self.game_folder / DATA_FOLDER_NAME / LOAD_ORDER_FILENAME)
        return inputs

    def _build_input_fingerprint(self, projects):
        if not any(p.enabled for p in projects):
            return None
        shared = self._shared_build_inputs()
        inputs = []
        for project in projects:
            if not project.enabled:
                inputs.append((project.id, False))
                continue
            runtime = self._runtime_cache_inputs(project, projects, shared) if self._runtime_patch_script(project) else {}
            if runtime is None:
                # Undeclared generators have just executed unconditionally. Their
                # current outputs may still match the last complete build.
                runtime = {}
            runtime.pop("load_order", None)  # The requested selection is already fingerprinted.
            inputs.append((project.id, str(project.folder.resolve()), build_cache.snapshot(project.folder), runtime))
        return build_cache.fingerprint({"shared": shared, "projects": inputs})

    def _full_build_output_paths(self):
        return (self.compiled_pack_path, self.game_folder / MODDED_EXE_FILENAME,
                self.game_folder / MODDED_AI_DLL_FILENAME, self.compiled_dir)

    def _cached_full_build(self, signature):
        if signature is None or (self.data_folder / "normal_maps").exists():
            return None
        record = build_cache.read_record(self.cache_folder / "build.json")
        if record.get("inputs") != signature:
            return None
        outputs = {str(p): build_cache.snapshot(p) for p in self._full_build_output_paths()}
        if outputs != record.get("outputs"):
            return None
        try:
            package = dict(record["package"])
            package["output"] = Path(package["output"])
            package["conflicts"] = [BuildConflict(**item) for item in package["conflicts"]]
            package["compressed_files"] = 0
            package["reused_files"] = package["files"]
            executable = dict(record["executable"])
            for key in ("original", "output", "ai_original", "ai_output"):
                executable[key] = Path(executable[key]) if executable[key] is not None else None
            executable["patches_applied"] = [ExecutablePatchApplied(**p) for p in executable["patches_applied"]]
            return FullBuildResult(BuildResult(**package), LoaderInstallResult(**executable))
        except (KeyError, ValueError, TypeError):
            return None

    def _remember_full_build(self, signature, result):
        if signature is None:
            return
        from dataclasses import asdict
        # Convert nested Path values without changing the public result types.
        payload = json.loads(json.dumps(asdict(result), default=str))
        build_cache.write_record(self.cache_folder / "build.json", {
            "inputs": signature, **payload,
            "outputs": {str(p): build_cache.snapshot(p) for p in self._full_build_output_paths()},
        })

    @staticmethod
    def _check_migration_source(source: Path, root: Path) -> None:
        entries = [source]
        if source.is_dir():
            for current, directories, files in os.walk(source, followlinks=False):
                entries.extend(Path(current) / name for name in directories + files)
        for entry in entries:
            if (entry.is_symlink() or getattr(entry, "is_junction", lambda: False)()
                    or not entry.resolve().is_relative_to(root)):
                raise ValueError(f"Unsafe legacy mod data path: {entry}")

    @staticmethod
    def _copy_migration_source(source: Path, destination: Path) -> None:
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)

    def _legacy_loader_update(self, metadata_folder: Path, pack_path: Path) -> Optional[tuple[bytes, dict]]:
        """Upgrade a fingerprinted legacy loader, retaining the compiled mod patches.

        A legacy executable may describe mods no longer enabled or installed. Rebuilding
        from today's selection would lose that build. Restore the recognized old
        loader's bytes, then put its replacement in a dedicated PE section. Zero-filled
        game data is NOT free space: the old allocator overwrote live menu constants.
        """
        executable = self.game_folder / MODDED_EXE_FILENAME
        if not executable.is_file():
            return None
        data = executable.read_bytes()
        old_payload = LEGACY_LOADER_PACK_PATH + LOADER_MARKER
        if old_payload not in data:
            if LEGACY_LOADER_PACK_PATH in data:
                raise ValueError("The existing executable has an unrecognized legacy loader.")
            return None
        manifest = json.loads((metadata_folder / "loader_manifest.json").read_text(encoding="utf-8"))
        if hashlib.sha256(data).hexdigest() != str(manifest["patched_sha256"]).lower():
            raise ValueError("The legacy modded executable does not match its build manifest.")
        build = json.loads((metadata_folder / "build_manifest.json").read_text(encoding="utf-8"))
        if sha256_file(pack_path) != str(build["sha256"]).lower():
            raise ValueError("The legacy archive does not match its build manifest.")
        original = (self.game_folder / "T3.exe").read_bytes()
        if hashlib.sha256(original).hexdigest() != str(manifest["original_sha256"]).lower():
            raise ValueError("The original executable does not match the legacy build.")
        if len(data) != len(original) or data.count(old_payload) != 1:
            raise ValueError("The legacy loader layout is not recognized.")
        legacy_writes = _legacy_loader_writes(original, LEGACY_LOADER_PACK_PATH)
        for offset, payload in legacy_writes:
            if data[offset:offset + len(payload)] != payload:
                raise ValueError("The legacy loader code or payload is not recognized.")
        plan = build_loader_patch(original, LOADER_PACK_PATH, LOADER_MARKER)
        protected = [(offset, offset + len(payload)) for offset, payload in legacy_writes]
        protected.extend((offset, offset + len(payload)) for offset, payload, _ in plan.writes)
        for entry in manifest.get("executable_patches", []):
            if str(entry.get("target", "T3.exe")).lower() != "t3.exe":
                continue
            start = int(entry["file_offset"])
            if any(start < end and start + int(entry["size"]) > offset for offset, end in protected):
                raise ValueError("The loader upgrade overlaps an executable patch.")
        updated = bytearray(data)
        for offset, payload in legacy_writes:
            updated[offset:offset + len(payload)] = original[offset:offset + len(payload)]
        updated.extend(b"\0" * (plan.final_size - len(updated)))
        for offset, payload, owner in plan.writes:
            _apply_owned_bytes(updated, {}, offset, payload, owner)
        manifest.update({
            "pack": LOADER_PACK_PATH.rstrip(b"\0").decode("ascii"),
            "patched_sha256": hashlib.sha256(updated).hexdigest(),
            "loader_section": ".t3ldr",
        })
        return bytes(updated), manifest

    def _migrate_legacy_data(self) -> None:
        legacy = [
            (self.mods_folder / LOAD_ORDER_FILENAME, self.load_order_path),
            (self.mods_folder / ".compiled", self.compiled_dir),
            (self.mods_folder / COMPILED_PACK_FILENAME, self.compiled_pack_path),
        ]
        legacy = [(source, target) for source, target in legacy if source.exists() and source != target]
        if not legacy:
            return
        for source, _ in legacy:
            self._check_migration_source(source, self.mods_folder)

        # Verify the old loader before moving its archive. If it cannot be recognized,
        # leave that archive available until an ordinary successful build replaces it.
        loader_update = None
        hold_archive = False
        old_pack = self.mods_folder / COMPILED_PACK_FILENAME
        if old_pack.is_file():
            try:
                metadata = self.compiled_dir if (self.compiled_dir / "loader_manifest.json").is_file() else self.mods_folder / ".compiled"
                effective_pack = self.compiled_pack_path if self.compiled_pack_path.is_file() else old_pack
                loader_update = self._legacy_loader_update(metadata, effective_pack)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                hold_archive = True
                path = write_diagnostic(self.data_folder / "logs", str(exc))
                self._say("loader_rebuild_required")
                self._say("generator_details", project="migration", path=path)

        if hold_archive and len(legacy) == 1 and self.compiled_pack_path.is_file():
            # A previous attempt already copied the pack. Keep its legacy counterpart
            # available without duplicating a large recovery snapshot on every refresh.
            return

        recovery = self.data_folder / "legacy_backup" / uuid.uuid4().hex
        recovery.mkdir(parents=True)
        published: list[Path] = []
        replaced: list[tuple[Path, Path]] = []
        empty_directories: list[Path] = []
        with tempfile.TemporaryDirectory(prefix=".migration-", dir=self.data_folder) as temporary:
            stage = Path(temporary)
            try:
                for source, target in legacy:
                    # Recovery snapshots also work when the old mods folder is on a
                    # different volume. Never overwrite an established new destination.
                    self._copy_migration_source(source, recovery / source.name)
                    empty_reports = (
                        target == self.compiled_dir and source.is_dir()
                        and target.is_dir() and not any(target.iterdir())
                    )
                    if not target.exists() or empty_reports:
                        prepared = stage / source.name
                        self._copy_migration_source(source, prepared)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        # Opening the default mods folder creates this placeholder;
                        # it must not suppress a later custom-folder migration.
                        if empty_reports:
                            target.rmdir()
                            empty_directories.append(target)
                        os.replace(prepared, target)
                        published.append(target)

                replacements: list[tuple[Path, bytes]] = []
                if loader_update is not None:
                    updated, loader_manifest = loader_update
                    replacements.extend([
                        (self.game_folder / MODDED_EXE_FILENAME, updated),
                        (self.compiled_dir / "loader_manifest.json", (json.dumps(loader_manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")),
                    ])
                build_path = self.compiled_dir / "build_manifest.json"
                if build_path.is_file():
                    try:
                        build = json.loads(build_path.read_text(encoding="utf-8"))
                        if sha256_file(self.compiled_pack_path) == str(build["sha256"]).lower():
                            build["output"] = str(self.compiled_pack_path)
                            replacements.append((build_path, (json.dumps(build, indent=2, ensure_ascii=False) + "\n").encode("utf-8")))
                    except (OSError, ValueError, KeyError, TypeError):
                        pass
                for index, (target, data) in enumerate(replacements):
                    backup = recovery / f"replaced-{index}-{target.name}"
                    if target.exists():
                        shutil.copy2(target, backup)
                    prepared = stage / f"updated-{index}"
                    prepared.write_bytes(data)
                    os.replace(prepared, target)
                    if backup.exists():
                        replaced.append((target, backup))
                    else:
                        published.append(target)
            except Exception:
                for target, backup in reversed(replaced):
                    shutil.copy2(backup, target)
                for target in reversed(published):
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
                for target in empty_directories:
                    target.mkdir(parents=True, exist_ok=True)
                raise

        for source, target in legacy:
            if hold_archive and source == old_pack:
                continue
            try:
                # Exact validated legacy paths only; the recovery snapshot is retained.
                if source.is_dir():
                    shutil.rmtree(source)
                else:
                    source.unlink()
                self._say(
                    "migration_moved", source=source,
                    destination=target if target in published else recovery / source.name,
                )
            except OSError as exc:
                self._say("migration_failed", error_type=type(exc).__name__)
        self._say("migration_complete", path=self.data_folder)

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
                generates_assets=metadata.get("generates_assets") is True,
            )
        ordered: list[ModProject] = []
        for mod_id in state_order:
            project = found.pop(mod_id, None)
            if project:
                ordered.append(project)
        ordered.extend(sorted(found.values(), key=lambda project: project.name.lower()))
        self.save_projects(ordered)
        return ordered

    def save_projects(self, projects: list[ModProject]) -> None:
        self._disable_unavailable_dependents(projects)
        self._save_state(projects)

    @staticmethod
    def _metadata_names(project: ModProject, key: str) -> list[str]:
        if not project.metadata_path.is_file():
            return []
        metadata = json.loads(project.metadata_path.read_text(encoding="utf-8-sig"))
        names = metadata.get(key, [])
        pattern = r"[a-z0-9][a-z0-9_.-]{0,63}" if key == "requires" else r"[A-Za-z0-9_]+"
        if not isinstance(names, list) or any(not isinstance(n, str) or not re.fullmatch(pattern, n) for n in names):
            raise ValueError(f"{project.id}: {key} must be a list of valid names")
        return names

    def _disable_unavailable_dependents(self, projects: list[ModProject]) -> bool:
        requirements = {p.id: self._metadata_names(p, "requires") for p in projects}
        enabled = {p.id for p in projects if p.enabled}
        changed = False
        while True:
            removed = False
            for project in projects:
                missing = [name for name in requirements[project.id] if name not in enabled]
                if project.enabled and missing:
                    project.enabled = False
                    enabled.discard(project.id)
                    self._say("dependency_disabled", project=project.name, dependencies=", ".join(missing))
                    changed = removed = True
            if not removed:
                return changed

    def set_enabled(self, projects: list[ModProject], project_id: str, enabled: bool) -> None:
        """Enable prerequisites or disable dependents, without changing priority.

        Resolve the entire enable operation before mutating anything, so missing
        requirements and dependency cycles cannot leave a partial selection.
        """
        by_id = {p.id: p for p in projects}
        if project_id not in by_id:
            raise ValueError(f"Unknown mod: {project_id}")
        if enabled:
            requirements = {p.id: self._metadata_names(p, "requires") for p in projects}
            ready, visiting = [], set()
            def visit(name):
                if name not in by_id:
                    raise ValueError(f"Required mod is not installed: {name}")
                if name in visiting:
                    raise ValueError(f"Required mod dependency cycle: {name}")
                if name in ready:
                    return
                visiting.add(name)
                for dependency in requirements[name]:
                    visit(dependency)
                visiting.remove(name)
                ready.append(name)
            visit(project_id)
            for name in ready:
                if not by_id[name].enabled and name != project_id:
                    self._say("dependency_enabled", project=by_id[name].name, dependent=by_id[project_id].name)
                by_id[name].enabled = True
        else:
            # Validate metadata before changing the selected project.
            for project in projects:
                self._metadata_names(project, "requires")
            by_id[project_id].enabled = False
            self._disable_unavailable_dependents(projects)

    def _filter_unavailable_weapon_menu(self, projects, merged):
        """Prune disabled custom weapon entries in the package, never source files."""
        declared = {name.lower() for p in projects for name in self._metadata_names(p, "provides_weapons")}
        unavailable = {name for name in declared if f"weapons/{name}/weapon1.option" not in merged}
        key = "menudatas/weapons.dat"
        if not unavailable or key not in merged:
            return None, []
        data = merged[key][1].read_bytes()
        output, removed = [], set()
        for line in data.splitlines(keepends=True):
            if re.match(rb'^\s*#DefaultWeapons\b', line, re.I):
                def omit_default(match):
                    name = match[1].decode('ascii').lower()
                    if name in unavailable:
                        removed.add(name)
                        return b'""'
                    return match[0]
                line = re.sub(rb'"([A-Za-z0-9_]+)"', omit_default, line)
            match = re.match(rb'^\s*(?:"([A-Za-z0-9_]+)"|([A-Za-z0-9_]+))(?=\s|$)', line)
            name = (match[1] or match[2]).decode('ascii').lower() if match else None
            if name in unavailable:
                removed.add(name)
            else:
                output.append(line)
        return (b''.join(output), sorted(removed)) if removed else (None, [])

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

    def create_mod_pack(
        self,
        name: str,
        projects: Optional[list[ModProject]] = None,
        author: str = "",
    ) -> ModPackResult:
        """Freeze enabled projects into one standalone, editable mod project.

        Runtime generators are synchronized before taking the snapshot. Their output is
        included as a static manifest, not as scripts that could overwrite the merged
        patches later. Validate in an isolated game folder before publishing the pack.
        """
        if not name.strip():
            raise ValueError("Enter a name for the mod pack.")
        projects = list(projects if projects is not None else self.discover())
        enabled = [project for project in projects if project.enabled]
        if not enabled:
            raise ValueError("No enabled mods were found.")

        # Include IDs of on-disk projects even if the caller's visible list is stale.
        existing_ids = {project.id for project in projects}
        for path in self.mods_folder.glob("*/mod.json"):
            try:
                metadata = json.loads(path.read_text(encoding="utf-8"))
                existing_ids.add(safe_id(str(metadata.get("id") or path.parent.name)))
            except (OSError, ValueError, AttributeError):
                continue
        base = safe_id(name, "mod_pack")
        if base.split(".")[0].upper() in {
            "CON", "PRN", "AUX", "NUL",
            *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10)),
        }:
            base = ("mod_" + base)[:64]
        mod_id = base
        suffix = 2
        while mod_id in existing_ids or (self.mods_folder / mod_id).exists():
            ending = f"_{suffix}"
            mod_id = base[:64 - len(ending)] + ending
            suffix += 1
        destination = self.mods_folder / mod_id

        self.sync_runtime_patches(enabled)
        merged, conflicts = self._collect_pack_files(enabled)
        patches: list[dict] = []
        patch_sources: list[dict] = []
        for source in enabled:
            for patch in self._read_patch_manifest(source):
                original_id = str(patch.get("id") or "patch")
                # The numeric prefix keeps IDs unique even after the 64-character limit.
                pack_id = safe_id(f"p{len(patches) + 1}_{source.id}_{original_id}")
                patches.append({**patch, "id": pack_id})
                patch_sources.append({
                    "id": pack_id, "source_mod": source.id,
                    "source_patch": original_id, "target": patch["target"],
                })
        if not merged and not patches:
            raise ValueError("The enabled mods do not contain files/ content or executable patches.")

        source_ids = [project.id for project in enabled]
        authors = list(dict.fromkeys(project.author for project in enabled if project.author))
        metadata = {
            "format_version": MOD_FORMAT_VERSION,
            "id": mod_id, "name": name.strip(),
            "author": author.strip() or ", ".join(authors), "version": "1.0.0",
            "description": "Mod pack combining: " + ", ".join(project.name for project in enabled),
        }
        self._say("pack_creating", count=len(enabled))
        with tempfile.TemporaryDirectory(prefix=".modpack-", dir=self.data_folder) as staging:
            stage = Path(staging)
            folder = stage / "project"
            (folder / MOD_FILES_DIRNAME).mkdir(parents=True)
            (folder / MOD_PATCHES_DIRNAME).mkdir()
            file_records = []
            for relative, source_path, source_id in sorted(merged.values(), key=lambda item: item[0].lower()):
                output = folder / MOD_FILES_DIRNAME / relative
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, output)
                file_records.append({
                    "path": relative, "source_mod": source_id, "sha256": sha256_file(output),
                })
            (folder / MOD_METADATA_FILENAME).write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
            )
            pack = ModProject(
                mod_id, metadata["name"], folder, metadata["author"], "1.0.0",
                metadata["description"], True, len(merged), len(patches),
            )
            if patches:
                pack.executable_patch_path.write_text(json.dumps({
                    "format_version": EXEC_PATCH_FORMAT_VERSION,
                    "target": "T3.exe", "patches": patches,
                }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                self._validate_pack_patches(pack, stage / "validation")

            report = {
                "format_version": 1, "name": pack.name,
                "priority_rule": "Highest listed source wins case-insensitive duplicate internal paths.",
                "sources": [
                    {"priority": index, "id": source.id, "name": source.name,
                     "version": source.version, "author": source.author}
                    for index, source in enumerate(enabled, start=1)
                ],
                "asset_files": len(merged),
                "asset_overlaps": [conflict.__dict__ for conflict in conflicts],
                "executable_patches": len(patches), "patch_sources": patch_sources,
                "files": file_records,
            }
            (folder / "MERGE_REPORT.json").write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
            )
            source_lines = "\n".join(
                f"{index}. {source.name} ({source.id}), version {source.version}"
                for index, source in enumerate(enabled, start=1)
            )
            (folder / "README.md").write_text(
                f"# {pack.name}\n\nCreated with T3-ModTools Generate mod pack.\n\n"
                f"## Included mods (highest priority first)\n\n{source_lines}\n\n"
                f"Contains {len(merged)} asset files and {len(patches)} executable patches. "
                "The highest enabled source owns duplicate internal paths. "
                "MERGE_REPORT.json records sources, file hashes, resolved overlaps, "
                "and the original IDs of executable patches.\n\n"
                "## Using this pack\n\n"
                "This is a standalone snapshot. Its source mods are disabled after creation "
                "and their folders are retained. Use Build Mods + Modded EXE to compile it. "
                "Creating a pack does not rebuild the currently installed game outputs.\n\n"
                "Executable patches are validated together against the original binaries; "
                "incompatible writes abort creation. Runtime generators are synchronized "
                "before the snapshot; the pack includes their static patch output. "
                "Create a new pack to include future source updates. Development scripts "
                "and other files outside files/ are not bundled, except the patch manifest.\n",
                encoding="utf-8",
            )
            # Publish only after all copies and patch validation have succeeded. The
            # state writer uses an atomic replace, so a failure can remove this new pack
            # without changing the previous selection or compiled game outputs.
            folder.rename(destination)
            pack.folder = destination
            new_state = [pack] + [
                replace(project, enabled=False) if project.enabled else project
                for project in projects
            ]
            try:
                self._save_state(new_state)
            except Exception:
                shutil.rmtree(destination)
                raise
        for project in enabled:
            project.enabled = False
        return ModPackResult(pack, source_ids, conflicts)

    @staticmethod
    def _collect_pack_files(
        enabled: list[ModProject],
    ) -> tuple[dict[str, tuple[str, Path, str]], list[BuildConflict]]:
        merged: dict[str, tuple[str, Path, str]] = {}
        directories: dict[str, str] = {}
        conflicts: list[BuildConflict] = []
        for project in enabled:
            root = project.folder.resolve()
            if not project.files_path.is_dir():
                continue
            for current, subdirs, filenames in os.walk(project.files_path, followlinks=False):
                # Do not silently omit directory links or follow junctions out of the mod.
                for entry in [Path(current), *(Path(current) / name for name in subdirs)]:
                    if entry.is_symlink() or not entry.resolve().is_relative_to(root):
                        raise ValueError(f"{project.id}: unsafe asset directory: {entry}")
                    if getattr(entry, "is_junction", lambda: False)():
                        raise ValueError(f"{project.id}: asset directory junctions are not supported: {entry}")
                for filename in sorted(filenames):
                    source = Path(current) / filename
                    if not source.resolve().is_relative_to(root):
                        raise ValueError(f"{project.id}: asset resolves outside the mod folder: {source}")
                    relative = norm_internal_path(source.relative_to(project.files_path).as_posix())
                    key = relative.lower()
                    if key in merged:
                        conflicts.append(BuildConflict(merged[key][0], project.id, merged[key][2]))
                        continue
                    # A shared directory can have different casing across source mods.
                    # Choose one spelling, from the highest source, before copying so
                    # the report matches the actual paths on Windows and on Linux.
                    parts = relative.split("/")
                    for depth in range(1, len(parts)):
                        prefix = "/".join(parts[:depth])
                        canonical = directories.setdefault(prefix.lower(), prefix)
                        parts[:depth] = canonical.split("/")
                    merged[key] = ("/".join(parts), source, project.id)
        collision = next((key for key in merged if key in directories), None)
        if collision is not None:
            raise ValueError(f"An asset is both a file and a directory: {collision}")
        return merged, conflicts

    def _validate_pack_patches(self, pack: ModProject, game_folder: Path) -> None:
        """Reuse full loader conflict/signature checks, writing only temporary outputs."""
        game_folder.mkdir()
        targets = {"T3.exe"} | {patch["target"] for patch in self._read_patch_manifest(pack)}
        for target in targets:
            original = self.game_folder / target
            if not original.is_file():
                raise FileNotFoundError(f"{target} was not found in {self.game_folder}")
            shutil.copy2(original, game_folder / target)
        validator = ModManager(game_folder, log=self.log, language=self.language)
        validator.install_loader([pack], synchronize_runtime=False)

    @build_cache.scan_operation
    def build(self, projects: Optional[list[ModProject]] = None, *, generated_files=None) -> BuildResult:
        # Snapshot the current selection before removing generated state. load_order.json
        # is then recreated from this snapshot so its old contents cannot survive a build.
        projects = projects if projects is not None else self.discover()
        self._disable_unavailable_dependents(projects)
        if generated_files is None:
            generated_files=(analyze_anm_compatibility(self.game_folder,projects).generated_files
                if any(p.enabled and (p.folder/'anm_variants.json').is_file() for p in projects) else {})
        compiled_dir = self.compiled_dir
        self._say("compiled_cleaning")
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
        # The UI and load_order.json list the highest-priority mod first. Merge from
        # lowest to highest priority so an earlier project replaces a later project's
        # copy of the same internal path.
        for project in reversed(enabled):
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
        menu_data, omitted_weapons = self._filter_unavailable_weapon_menu(projects, merged)
        generated_files = dict(generated_files)
        if menu_data is not None:
            generated_files['menudatas/weapons.dat'] = menu_data
        for key in generated_files:
            if key not in merged:merged[key]=(key,self.data_folder/key,'t3_modtools_variants')
        if not merged and not has_exec_patches:
            raise ValueError("The enabled mods do not contain files/ content or executable patches.")

        # An empty ZIP is intentional for executable-only mods; the common loader still has
        # a valid Mods.Cod to open while the executable changes are applied to T3_Modded.exe.
        self.compiled_pack_path.parent.mkdir(parents=True, exist_ok=True)
        assets = build_cache.AssetCache(self.cache_folder / "assets")
        with build_cache.CachedZipFile(pack_temporary, "w") as archive:
            for _, (relative, source, _) in sorted(merged.items(), key=lambda item: item[1][0].lower()):
                if relative.lower() in generated_files:
                    assets.add(archive, relative, data=generated_files[relative.lower()])
                else:
                    assets.add(archive, relative, source=source)
        os.replace(pack_temporary, self.compiled_pack_path)
        self._say("cache_assets", compressed=assets.compressed, reused=assets.reused)

        result = BuildResult(
            output=self.compiled_pack_path,
            enabled_mods=[project.id for project in enabled],
            files=len(merged),
            conflicts=conflicts,
            sha256=sha256_file(self.compiled_pack_path),
            compressed_files=assets.compressed,
            reused_files=assets.reused,
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
            "generated_libraries": sorted(key for key in generated_files if key != 'menudatas/weapons.dat'),
            "omitted_menu_weapons": omitted_weapons,
            "incremental": {"compressed_files": assets.compressed, "reused_files": assets.reused},
        }
        manifest_path = self.compiled_dir / "build_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        return result

    @build_cache.scan_operation
    def build_all(self, projects: Optional[list[ModProject]] = None) -> FullBuildResult:
        """Build Mods.Cod, T3_Modded.exe, and its optional patched AI DLL atomically.

        Enabled root-level runtime_patch.py generators are synchronized before any
        existing output is staged, so a generator failure leaves the last valid set
        untouched.

        If any part fails, the previous generated set is restored so Launch never mixes
        a new package with older executable components. T3.exe and Ai.Dll are never involved
        in the rollback because they are read-only inputs.
        """
        projects = projects if projects is not None else self.discover()
        self.sync_runtime_patches(projects)
        signature = self._build_input_fingerprint(projects)
        cached = self._cached_full_build(signature)
        if cached is not None:
            build_cache.invalidate_scan()
            current_signature = self._build_input_fingerprint(projects)
            if current_signature != signature:
                raise ValueError("Build inputs changed during compilation; rebuild")
        if cached is not None:
            self._save_state(projects)
            self._say("cache_build")
            return cached
        # Cache validation may have read damaged/stale outputs. The writer phase
        # must calculate hashes of its replacements, never reuse those old reads.
        build_cache.invalidate_scan()
        # Analyze the winning files before staging the previous complete build.
        anm_plan = analyze_anm_compatibility(self.game_folder, projects)
        executable_path = self.game_folder / MODDED_EXE_FILENAME
        ai_output_path = self.game_folder / MODDED_AI_DLL_FILENAME
        outputs = (
            self.compiled_pack_path, executable_path, ai_output_path,
            self.compiled_dir, self.load_order_path,
            self.data_folder / 'normal_maps',  # Retired runtime: remove only after a successful build.
        )
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

            package = (self.build(projects,generated_files=anm_plan.generated_files)
                       if anm_plan.generated_files else self.build(projects))
            sources=effective_mod_files(projects) if anm_plan.generated_files else {}
            # An export during compilation must not pair new ANMs with stale rules.
            if anm_plan.report.get('inputs'):
                with zipfile.ZipFile(package.output) as archive:
                    names = {name.lower():name for name in archive.namelist()}
                    for item in anm_plan.report['inputs']:
                        name = names.get(item['path'])
                        expected=item['sha256']
                        if item['path'] in anm_plan.generated_files:
                            if build_cache.file_hash(sources[item['path']][0], fresh=True)!=expected:
                                raise ValueError('ANM variant source library changed during compilation')
                            expected=hashlib.sha256(anm_plan.generated_files[item['path']]).hexdigest()
                        if name is None or hashlib.sha256(archive.read(name)).hexdigest()!=expected:
                            raise ValueError(f"ANM input changed during compilation: {item['path']}; rebuild")
                    for path,data in anm_plan.generated_files.items():
                        if path not in names or archive.read(names[path])!=data:
                            raise ValueError('Generated NPC variant library changed during compilation')
            for item in anm_plan.report.get('variant_configuration_inputs',[]):
                if build_cache.file_hash(Path(item['file']), fresh=True)!=item['sha256']:
                    raise ValueError('NPC variant configuration changed during compilation')
            executable = self.install_loader(projects, synchronize_runtime=False,
                anm_plan=anm_plan)
            build_cache.invalidate_scan()
            if signature is not None and self._build_input_fingerprint(projects) != signature:
                raise ValueError("Build inputs changed during compilation; rebuild")
        except Exception as build_error:
            rollback_errors: list[str] = []

            # Restore staged outputs directly over any partially generated replacements.
            # Outputs that did not exist before the build are simply removed.
            for output, backup in reversed(staged):
                try:
                    if backup.exists():
                        # Windows cannot replace a non-empty directory. Only discard
                        # the new partial reports after the old report backup exists.
                        if backup.is_dir() and output.is_dir():
                            shutil.rmtree(output)
                        os.replace(backup, output)
                except OSError as exc:
                    rollback_errors.append(f"{backup} -> {output}: {exc}")
            for output in outputs:
                if existed_before[output]:
                    continue
                try:
                    if output.exists():
                        if output.is_dir():
                            shutil.rmtree(output)
                        else:
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
            # Cleanup is deliberately best-effort. The newly built set is valid even if
            # Windows temporarily keeps an old backup open after a successful replacement.
            for _, backup in staged:
                try:
                    if backup.exists():
                        if backup.is_dir():
                            shutil.rmtree(backup)
                        else:
                            backup.unlink()
                except OSError as exc:
                    self._say("backup_cleanup_failed", path=backup, error_type=type(exc).__name__)
            # An unrecognized older loader may have kept its legacy package available
            # during migration. The successful new build can now retire that copy.
            if (self.mods_folder / COMPILED_PACK_FILENAME).exists():
                try:
                    self._migrate_legacy_data()
                except OSError as exc:
                    self._say("migration_failed", error_type=type(exc).__name__)
            result = FullBuildResult(package=package, executable=executable)
            try:
                self._remember_full_build(signature, result)
            except OSError:
                # Cache storage is optional; the validated build is already committed.
                self._say("cache_record_failed")
            return result

    @staticmethod
    def _runtime_python_executable() -> Path:
        """Prefer the console interpreter beside pythonw when the GUI launched us."""
        executable = Path(sys.executable).resolve()
        if executable.name.lower() == "pythonw.exe":
            console = executable.with_name("python.exe")
            if console.is_file():
                return console
        return executable

    def _runtime_patch_script(self, project: ModProject) -> Optional[Path]:
        """Return a safe root-level runtime_patch.py, rejecting escaping symlinks."""
        project_root = project.folder.expanduser().resolve()
        candidate = project_root / RUNTIME_PATCH_FILENAME
        if not candidate.is_file():
            return None
        resolved = candidate.resolve()
        try:
            resolved.relative_to(project_root)
        except ValueError as exc:
            raise ValueError(
                f"{project.id}: {RUNTIME_PATCH_FILENAME} resolves outside the mod folder."
            ) from exc
        return resolved

    @staticmethod
    def _decode_runtime_output(payload: Optional[bytes]) -> str:
        return (payload or b"").decode("utf-8", errors="replace").strip()

    def _ordered_runtime_generators(self, projects: list[ModProject]) -> list[tuple[ModProject, Path]]:
        """Order generators by declared project dependencies, preserving load priority.

        Only a dependency resolving to an enabled generator's exact folder adds
        an ordering edge. Individual files, other directories and config_paths
        remain cache inputs. Validate the entire graph before executing scripts.
        """
        generators = []
        for project in projects:
            if project.enabled:
                script = self._runtime_patch_script(project)
                if script is not None:
                    generators.append((project, script))
        folders = {project.folder.resolve(): index
                   for index, (project, _) in enumerate(generators)}
        dependencies = []
        for project, _ in generators:
            metadata = (json.loads(project.metadata_path.read_text(encoding="utf-8-sig"))
                        if project.metadata_path.is_file() else {})
            policy = metadata.get("runtime_cache")
            paths = policy.get("dependencies", []) if isinstance(policy, dict) else []
            if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
                raise ValueError(f"{project.id}: runtime_cache.dependencies must be a list of paths")
            dependencies.append({folders[path] for relative in paths
                                 if (path := (project.folder / relative).resolve()) in folders})
        pending = list(range(len(generators)))
        ordered, complete = [], set()
        while pending:
            # Stable Kahn order: among currently ready scripts use the original
            # project priority. The projects list still governs file winners and
            # cache fingerprints; only execution uses this separate sequence.
            ready = next((index for index in pending if dependencies[index] <= complete), None)
            if ready is None:
                names = ", ".join(generators[index][0].id for index in pending)
                raise ValueError(f"Runtime generator dependency cycle: {names}")
            pending.remove(ready)
            complete.add(ready)
            ordered.append(generators[ready])
        return ordered

    @build_cache.scan_operation
    def sync_runtime_patches(self, projects: Iterable[ModProject]) -> int:
        """Run enabled runtime patch generators with --write before compiling.

        Scripts execute directly with this tool's Python interpreter and never through a
        command shell. Only the exact root-level runtime_patch.py convention is recognized.
        """
        synchronized = 0
        projects = list(projects)
        if self._disable_unavailable_dependents(projects):
            self._save_state(projects)
        shared = None
        for project, script in self._ordered_runtime_generators(projects):
            if shared is None:
                shared = self._shared_build_inputs()
            inputs = self._runtime_cache_inputs(project, projects, shared)
            cache_path = self.cache_folder / "generators" / (build_cache.fingerprint(str(project.folder.resolve())) + ".json")
            signature = build_cache.fingerprint(inputs) if inputs is not None else None
            if signature is not None and build_cache.read_record(cache_path).get("inputs") == signature:
                if project.executable_patch_path.is_file():
                    self._read_patch_manifest(project)
                    self._say("cache_generator", project=project.id)
                    continue

            self._say("generator_sync", project=project.id, script=script.name)
            try:
                completed = subprocess.run(
                    [str(self._runtime_python_executable()), str(script), "--write"],
                    cwd=str(project.folder.resolve()),
                    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=RUNTIME_PATCH_TIMEOUT_SECONDS,
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    f"{project.id}/{script.name} exceeded the "
                    f"{RUNTIME_PATCH_TIMEOUT_SECONDS}-second synchronization limit."
                ) from exc
            except OSError as exc:
                raise RuntimeError(
                    f"Could not execute {project.id}/{script.name}: {exc}"
                ) from exc

            stdout = self._decode_runtime_output(completed.stdout)
            stderr = self._decode_runtime_output(completed.stderr)
            if completed.returncode != 0:
                details = "\n".join(part for part in (stdout, stderr) if part)
                suffix = f"\n{details}" if details else ""
                raise RuntimeError(
                    f"{project.id}/{script.name} failed with exit code "
                    f"{completed.returncode}.{suffix}"
                )

            if stdout or stderr:
                path = write_diagnostic(
                    self.data_folder / "logs",
                    f"{project.id}/{script.name}\n\nstdout:\n{stdout}\n\nstderr:\n{stderr}\n",
                )
                self._say("generator_details", project=project.id, path=path)

            if not project.executable_patch_path.is_file():
                raise RuntimeError(
                    f"{project.id}/{script.name} completed but did not create executable.json."
                )
            # A generator may rewrite its assets and inputs consumed by later
            # generators. Never carry a read-only scan across this writer.
            build_cache.invalidate_scan()
            self._read_patch_manifest(project)
            if inputs is not None:
                # Generated files are part of the post-run snapshot, so missing or
                # edited outputs invalidate reuse just like edited source files.
                inputs["files"] = build_cache.snapshot(project.folder)
                try:
                    build_cache.write_record(cache_path, {"inputs": build_cache.fingerprint(inputs)})
                except OSError:
                    self._say("cache_record_failed")
            self._say("generator_done", project=project.id)
            synchronized += 1
        return synchronized

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
        target_names = {"t3.exe": "T3.exe", "ai.dll": AI_DLL_FILENAME}
        default_target = str(data.get("target", "T3.exe"))
        if default_target.lower() not in target_names:
            raise ValueError(
                f"{project.id}: unsupported executable patch target '{default_target}'."
            )
        patches = data.get("patches", [])
        if not isinstance(patches, list):
            raise ValueError(f"{project.id}: 'patches' must be a list.")
        normalized: list[dict] = []
        for index, patch in enumerate(patches, start=1):
            if not isinstance(patch, dict):
                continue
            patch_target = str(patch.get("target", default_target))
            canonical_target = target_names.get(patch_target.lower())
            if canonical_target is None:
                patch_id = str(patch.get("id") or f"patch_{index}")
                raise ValueError(
                    f"{project.id}/{patch_id}: unsupported executable patch target "
                    f"'{patch_target}'."
                )
            normalized_patch = dict(patch)
            normalized_patch["target"] = canonical_target
            normalized.append(normalized_patch)
        return normalized

    def install_loader(
        self,
        projects: Optional[list[ModProject]] = None,
        *,
        synchronize_runtime: bool = True,
        anm_plan: Optional[CompatibilityPlan] = None,
    ) -> LoaderInstallResult:
        projects = projects if projects is not None else self.discover()
        if synchronize_runtime and any(p.enabled and p.generates_assets for p in projects):
            # An asset generator can change model locators/textures as well as
            # executable patches. Keep Mods.Cod and the EXE in the same build.
            self._say("generated_assets_rebuild")
            return self.build_all(projects).executable
        if synchronize_runtime:
            self.sync_runtime_patches(projects)
        original = self.game_folder / "T3.exe"
        if not original.is_file():
            raise FileNotFoundError(f"T3.exe was not found in {self.game_folder}")
        if anm_plan is None:
            anm_plan = analyze_anm_compatibility(self.game_folder, projects)
            if anm_plan.variants and synchronize_runtime:
                return self.build_all(projects).executable
        output = self.game_folder / MODDED_EXE_FILENAME
        original_bytes = original.read_bytes()
        data = bytearray(original_bytes)
        original_hash = hashlib.sha256(original_bytes).hexdigest()
        enabled = [project for project in projects if project.enabled]
        queued_patches: list[tuple[ModProject, int, dict]] = []
        migrated = []
        for project in enabled:
            for index, patch in enumerate(self._read_patch_manifest(project), start=1):
                if t3_anm_runtime.is_legacy_patch(patch):
                    migrated.append({'mod':project.id,'patch':patch['id']})
                else:
                    queued_patches.append((project,index,patch))
        anm_plan.report['replaced_legacy_patches'] = migrated
        ai_source = self.game_folder / AI_DLL_FILENAME
        t3_anm_runtime.validate_targets(anm_plan, original_bytes,
            ai_source.read_bytes() if (anm_plan.navigation or anm_plan.variants) and ai_source.is_file() else None)

        extensions = []
        ordinary_patches = []
        for project, index, patch in queued_patches:
            if patch.get('type') != 'loader_extension':
                ordinary_patches.append((project, index, patch))
                continue
            if patch['target'] != 'T3.exe':
                raise ValueError(f'{project.id}: loader extensions support T3.exe only')
            if patch.get('expected_original_sha256') != original_hash:
                raise ValueError(f'{project.id}: loader extension target fingerprint mismatch')
            try:
                address = int(str(patch['virtual_address']), 0)
                if not isinstance(patch['replacement'], str):
                    raise TypeError('replacement must be a hexadecimal string')
                payload = bytes.fromhex(patch['replacement'])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f'{project.id}/{patch.get("id", index)}: invalid loader extension fields: {exc}') from exc
            if not payload or len(payload) > 0x10000:
                raise ValueError(f'{project.id}: invalid loader extension size')
            extensions.append((address, payload, project, index, patch))
        extensions.sort(key=lambda item: item[0])
        for left, right in zip(extensions, extensions[1:]):
            if left[0] + len(left[1]) > right[0]:
                raise ValueError('Overlapping owned loader extensions')
        queued_patches = ordinary_patches
        pe = _PEImage(original_bytes)
        write_map: dict[int, _PatchWriteOwner] = {}

        # The loader owns newly allocated PE storage. Existing zero-filled game
        # sections contain live constants/globals and must never be used as padding.
        has_anm_extension = bool(anm_plan.rules or anm_plan.variants)
        has_transparency = t3_material_runtime.required(effective_mod_files(projects))
        material_offset = ((len(t3_anm_runtime.build_extension(anm_plan,0x2000000))+15)//16*16
                           if has_anm_extension else 0)
        def extension(va):
            payload=t3_anm_runtime.build_extension(anm_plan,va) if has_anm_extension else b''
            if has_transparency:
                payload+=b'\x90'*(material_offset-len(payload))+t3_material_runtime.build(va+material_offset)
            for address, content, project, _, _ in extensions:
                gap = address - (va + len(payload))
                if not 0 <= gap <= 0x10000:
                    raise ValueError(f'{project.id}: loader extension address overlaps generated code or exceeds reservation')
                payload += b'\xCC' * gap + content
            return payload
        loader_plan = build_loader_patch(original_bytes, LOADER_PACK_PATH, LOADER_MARKER,
            extension=extension if (has_anm_extension or has_transparency or extensions) else None)
        data.extend(b"\0" * (loader_plan.final_size - len(data)))
        for offset, payload, owner in loader_plan.writes:
            _apply_owned_bytes(data, write_map, offset, payload, owner)
        applied: list[ExecutablePatchApplied] = []
        for address, content, project, index, patch in extensions:
            applied.append(ExecutablePatchApplied(project.id, str(patch.get('id') or f'patch_{index}'),
                str(patch.get('description', 'Read/execute code in owned loader section')),
                loader_plan.extension_offset + address - loader_plan.extension_va, len(content), 'T3.exe'))
        automatic_project = ModProject('t3_modtools_anm','Automatic ANM compatibility',self.data_folder)
        for index, patch in enumerate(t3_anm_runtime.patches(anm_plan,loader_plan.extension_va),start=1):
            queued_patches.append((automatic_project,index,patch))
        if has_anm_extension:
            payload = t3_anm_runtime.build_extension(anm_plan,loader_plan.extension_va)
            applied.append(ExecutablePatchApplied(automatic_project.id,'anm_automatic_aim_compositor',
                'Generated ANM aim rules and NPC variant selector in owned loader section',loader_plan.extension_offset,len(payload),'T3.exe'))
        if has_transparency:
            material_project=ModProject('t3_modtools_materials','T3CleverTools material support',self.data_folder)
            for index,patch in enumerate(t3_material_runtime.patches(original_bytes,loader_plan.extension_va+material_offset),start=1):
                queued_patches.append((material_project,index,patch))
            applied.append(ExecutablePatchApplied(material_project.id,'material_transparency_runtime',
                'Opt-in material transparency with preserved D3D state',loader_plan.extension_offset+material_offset,
                len(t3_material_runtime.build(loader_plan.extension_va+material_offset)),'T3.exe'))
        for project, index, patch in queued_patches:
            if patch["target"] != "T3.exe":
                continue
            applied.append(
                self._apply_manifest_patch(
                    original_bytes,
                    data,
                    pe,
                    write_map,
                    project,
                    patch,
                    index,
                    target_name="T3.exe",
                )
            )

        ai_original: Optional[Path] = None
        ai_output: Optional[Path] = None
        ai_original_hash = ""
        ai_patched_hash = ""
        ai_patches = [item for item in queued_patches if item[2]["target"] == AI_DLL_FILENAME]
        ai_data: Optional[bytearray] = None
        if ai_patches:
            ai_original = self.game_folder / AI_DLL_FILENAME
            if not ai_original.is_file():
                raise FileNotFoundError(f"{AI_DLL_FILENAME} was not found in {self.game_folder}")
            ai_output = self.game_folder / MODDED_AI_DLL_FILENAME
            ai_original_bytes = ai_original.read_bytes()
            ai_original_hash = hashlib.sha256(ai_original_bytes).hexdigest()
            ai_data = bytearray(ai_original_bytes)
            ai_pe = _PEImage(ai_original_bytes)
            ai_write_map: dict[int, _PatchWriteOwner] = {}

            redirect_offsets: list[int] = []
            redirect_search_offset = 0
            while True:
                redirect_offset = original_bytes.find(
                    AI_DLL_IMPORT_NAME,
                    redirect_search_offset,
                )
                if redirect_offset < 0:
                    break
                redirect_offsets.append(redirect_offset)
                redirect_search_offset = redirect_offset + 1
            if len(redirect_offsets) != 1:
                raise ValueError(
                    "Unsupported T3.exe: expected one Ai.Dll loader string, found "
                    f"{len(redirect_offsets)}."
                )
            _apply_owned_bytes(
                data,
                write_map,
                redirect_offsets[0],
                MODDED_AI_DLL_IMPORT_NAME,
                "T3-ModTools loader:Ai.Dll redirect",
            )

            for project, index, patch in ai_patches:
                applied.append(
                    self._apply_manifest_patch(
                        ai_original_bytes,
                        ai_data,
                        ai_pe,
                        ai_write_map,
                        project,
                        patch,
                        index,
                        target_name=AI_DLL_FILENAME,
                    )
                )

        temporary = output.with_suffix(".tmp")
        temporary.write_bytes(data)
        ai_temporary: Optional[Path] = None
        if ai_output is not None and ai_data is not None:
            ai_temporary = ai_output.with_suffix(".tmp")
            ai_temporary.write_bytes(ai_data)
        os.replace(temporary, output)
        if ai_output is not None and ai_temporary is not None:
            os.replace(ai_temporary, ai_output)
            ai_patched_hash = sha256_file(ai_output)
        else:
            stale_ai_output = self.game_folder / MODDED_AI_DLL_FILENAME
            if stale_ai_output.exists():
                stale_ai_output.unlink()
        result = LoaderInstallResult(
            original=original,
            output=output,
            original_sha256=original_hash,
            patched_sha256=sha256_file(output),
            code_cave_file_offset=loader_plan.code_offset,
            data_cave_file_offset=loader_plan.data_offset,
            patches_applied=applied,
            ai_original=ai_original,
            ai_output=ai_output,
            ai_original_sha256=ai_original_hash,
            ai_patched_sha256=ai_patched_hash,
        )
        loader_manifest = {
            "format_version": 2,
            "original": str(result.original),
            "output": str(result.output),
            "original_sha256": result.original_sha256,
            "patched_sha256": result.patched_sha256,
            "pack": LOADER_PACK_PATH.rstrip(b"\0").decode("ascii"),
            "loader_section": ".t3ldr",
            "priority": "loaded before Language.cod, Patch116.Cod, and Game.Cod",
            "original_modified": False,
            "ai_original": str(result.ai_original) if result.ai_original else None,
            "ai_output": str(result.ai_output) if result.ai_output else None,
            "ai_original_sha256": result.ai_original_sha256 or None,
            "ai_patched_sha256": result.ai_patched_sha256 or None,
            "ai_original_modified": False,
            "executable_patches": [patch.__dict__ for patch in result.patches_applied],
        }
        self.compiled_dir.mkdir(parents=True, exist_ok=True)
        anm_report_path = self.compiled_dir / 'anm_compatibility.json'
        anm_report_path.write_text(json.dumps(anm_plan.report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        outside = sum(row['status'] in ('needs_reference','outside_profile') for row in anm_plan.report['animations'])
        self._say('anm_compatibility',count=len(anm_plan.rules),outside=outside,path=anm_report_path)
        (self.compiled_dir / "loader_manifest.json").write_text(
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
        *,
        target_name: str = "T3.exe",
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
                f"{target_name} may be incompatible or the patch signature is ambiguous."
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
                    f"0x{offset + first:X}. {target_name} may be incompatible."
                )

        replacement_bytes = bytes(
            original_bytes[offset + i] if token is None else token
            for i, token in enumerate(replacement)
        )
        owner = f"{project.id}/{patch_id}"
        _apply_owned_bytes(data, write_map, offset, replacement_bytes, owner)
        return ExecutablePatchApplied(
            project.id,
            patch_id,
            description,
            offset,
            len(replacement_bytes),
            target_name,
        )

    def launch_modded(self) -> subprocess.Popen:
        executable = self.game_folder / MODDED_EXE_FILENAME
        if not executable.is_file():
            raise FileNotFoundError("T3_Modded.exe does not exist. Build the enabled mods first.")
        if not self.compiled_pack_path.is_file():
            raise FileNotFoundError("modtools_data/Mods.Cod does not exist. Build the enabled mods first.")
        image = executable.read_bytes()
        try:
            pe = _PEImage(image)
            sections = [section for section in pe.sections if section.name == ".t3ldr"]
            safe_loader = len(sections) == 1 and LOADER_PACK_PATH + LOADER_MARKER in image[
                sections[0].raw_offset:sections[0].raw_offset + sections[0].raw_size
            ]
        except (ValueError, struct.error):
            safe_loader = False
        if not safe_loader:
            raise RuntimeError(log_tr(self.language, "loader_rebuild_required"))
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

    # Anchor the wildcard-aware comparison to the longest concrete byte run. The old
    # byte-by-byte scan was correct but made a second target DLL unnecessarily expensive:
    # each patch traversed the complete section in Python. bytes.find performs the broad
    # search in native code and only the few candidates need full wildcard validation.
    concrete_runs: list[tuple[int, bytes]] = []
    run_start = 0
    run = bytearray()
    for index, token in enumerate(pattern + [None]):
        if token is not None:
            if not run:
                run_start = index
            run.append(token)
            continue
        if run:
            concrete_runs.append((run_start, bytes(run)))
            run.clear()
    if not concrete_runs:
        return list(range(start, end - width + 1))
    anchor_offset, anchor = max(concrete_runs, key=lambda item: len(item[1]))

    matches: list[int] = []
    limit = end - width
    search_position = start + anchor_offset
    search_end = end - (width - anchor_offset) + len(anchor)
    while True:
        anchor_match = data.find(anchor, search_position, search_end)
        if anchor_match < 0:
            break
        offset = anchor_match - anchor_offset
        if start <= offset <= limit and all(
            token is None or data[offset + i] == token
            for i, token in enumerate(pattern)
        ):
            matches.append(offset)
        search_position = anchor_match + 1
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


def _legacy_loader_writes(original: bytes, pack_path: bytes) -> list[tuple[int, bytes]]:
    """Recognize old loader bytes for removal only; never allocate a new loader here."""
    pe = _PEImage(original)
    language_offset = original.find(b"Language.cod\0")
    if language_offset < 0:
        raise ValueError("The legacy Language.cod string is missing.")
    language_va = pe.file_offset_to_va(language_offset)
    signature = b"\x53\x68" + struct.pack("<I", language_va)
    entry = original.find(signature, pe.text.raw_offset, pe.text.raw_offset + pe.text.raw_size)
    if entry < 0 or original[entry + len(signature)] != 0xE8:
        raise ValueError("The legacy package-loading call is not recognized.")
    call = entry + len(signature)
    call_va = pe.file_offset_to_va(call)
    add_pack_va = call_va + 5 + struct.unpack_from("<i", original, call + 1)[0]
    payload = pack_path + LOADER_MARKER
    old_data = _find_zero_cave(original, pe.data.raw_offset, pe.data.raw_offset + pe.data.raw_size, len(payload) + 16)
    old_code = _find_zero_cave(original, pe.text.raw_offset, pe.text.raw_offset + pe.text.raw_size, 64, prefer_last=True)
    if old_data is None or old_code is None:
        raise ValueError("The legacy loader locations are not recognized.")
    code_va = pe.file_offset_to_va(old_code)
    code = bytearray(b"\x68\0\0\0\0\x68" + struct.pack("<I", pe.file_offset_to_va(old_data)))
    code += b"\xE8" + struct.pack("<i", add_pack_va - (code_va + len(code) + 5))
    code += b"\x83\xC4\x08\x53\x68" + struct.pack("<I", language_va)
    code += b"\xE9" + struct.pack("<i", call_va - (code_va + len(code) + 5))
    code += b"\x90" * (64 - len(code))
    hook = b"\xE9" + struct.pack("<i", code_va - (pe.file_offset_to_va(entry) + 5)) + b"\x90"
    return [(entry, hook), (old_code, bytes(code)), (old_data, payload)]


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
