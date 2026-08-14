#!/usr/bin/env python3
"""
T3-ModTools
Extractor/converter for Terminator 3: War of the Machines (PC, 2003).

- Opens Game.cod / Patch*.cod directly (they are ZIP-compatible archives).
- Can also open the installed game directory or an outer backup ZIP containing COD files.
- Extracts raw assets with patch overlay semantics.
- Converts regular SCA/LOD/DET meshes to OBJ+MTL.
- Reconstructs static map geometry from scene/<level>/scene.sca binary-tree vertex buffers.

The converter intentionally does not bypass DRM, encryption, or anti-cheat. Use it only
with game data you own and respect the rights attached to the extracted assets.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import traceback
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable, Iterator, Optional

from t3_rig_export import RiggedExportResult, export_rigged_gltf, parse_animation_summary
from t3_texture_convert import TextureConversionError, convert_texture_file_to_png
from t3_modding import ModManager, ModProject, open_in_file_manager

APP_NAME = "T3-ModTools"
APP_VERSION = "0.6.1"

NUMBER_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
INT_RE = re.compile(r"[-+]?\d+")


I18N: dict[str, dict[str, str]] = {
    "en": {
        "no_archives": "No Game.cod/Patch*.cod files or valid COD archive were found.",
        "opening_archive": "Opening {name} ({entries} entries)",
        "combined_view": "Combined view: {files} files",
        "outer_zip": "The outer ZIP contains {count} COD files; preparing temporary access...",
        "no_binary_tree": "scene.sca does not contain cBinaryTree.",
        "map_shaders": "  Map: {count} shaders",
        "map_buffer": "  Buffer {buffer_id}: {count} vertices",
        "map_tree": "  Tree: {lists} lists, {triangles} unique triangles",
        "extract_progress": "{kind}: extracted {count} files...",
        "extract_done": "{kind}: {count} files extracted to {destination}",
        "effects": "Effects",
        "audio": "Audio",
        "animations": "Animations",
        "rigged_models": "Export Rigs (glTF 2.0)",
        "animation_summary": "Animations: {count} ANM files extracted to {destination}",
        "rigged_selected": "Rigged models selected: {count}",
        "rigged_converting": "[{index}/{total}] Exporting rigged model {path}",
        "rigged_ok": "  RIG OK: {vertices} vertices, {triangles} triangles, {bones} bones",
        "raw_progress": "Extracted {count} files...",
        "raw_done": "Raw extraction completed: {count} files",
        "geometry_selected": "Selected geometry files: {count}",
        "converting": "[{index}/{total}] Converting {path}",
        "no_submeshes": "No compatible triangulated submeshes were found.",
        "conversion_ok": "  OK: {vertices} vertices, {triangles} triangles, {materials} materials",
        "texture_missing": "Texture not found: {texture}",
        "texture_convert_failed": "Texture could not be converted for glTF: {texture} ({error})",
        "invalid_categories": "Invalid categories: {categories}",
        "done_cli": "Done: {output}",
        "tk_unavailable": "Tkinter is not available: {error}",
        "language": "Language",
        "input_label": "Locate and select Game.cod:",
        "output_label": "Output folder:",
        "browse": "Browse",
        "select_input_title": "Select Game.cod",
        "game_cod_files": "Game COD archive",
        "cod_files": "COD archives",
        "zip_files": "ZIP backups",
        "all_files": "All files",
        "select_output_title": "Select output folder",
        "categories": "Categories",
        "characters": "Characters",
        "vehicles": "Vehicles",
        "weapons": "Weapons",
        "maps": "Maps",
        "menu_models": "Menu Models",
        "options": "Options",
        "convert_geometry": "Convert SCA/LOD/DET to OBJ + MTL",
        "extract_raw": "Extract all raw files",
        "include_lod": "Convert LOD even when SCA exists",
        "all_lods": "Export all LOD levels",
        "z_up": "Z-up (only for weapons and effects)",
        "flip_v": "Flip UV V coordinate (Don't use with glTF 2.0 models)",
        "ready": "Ready",
        "start": "Extract / Convert",
        "select_category": "Select at least one category.",
        "finished_log": "FINISHED: {output}",
        "finished_message": "Export completed.\n\n{output}",
        "missing_paths": "Select Game.cod and an output folder.",
        "error_title": "Error",
        "warning_title": "Missing information",
    },
    "es": {
        "no_archives": "No se encontraron Game.cod/Patch*.cod ni un archivo COD válido.",
        "opening_archive": "Abriendo {name} ({entries} entradas)",
        "combined_view": "Vista combinada: {files} archivos",
        "outer_zip": "El ZIP exterior contiene {count} archivos COD; preparando acceso temporal...",
        "no_binary_tree": "scene.sca no contiene cBinaryTree.",
        "map_shaders": "  Mapa: {count} shaders",
        "map_buffer": "  Buffer {buffer_id}: {count} vértices",
        "map_tree": "  Árbol: {lists} listas, {triangles} triángulos únicos",
        "extract_progress": "{kind}: extraídos {count} archivos...",
        "extract_done": "{kind}: {count} archivos extraídos en {destination}",
        "effects": "Efectos",
        "audio": "Audio",
        "animations": "Animaciones",
        "rigged_models": "Exportar Rigs (glTF 2.0)",
        "animation_summary": "Animaciones: {count} archivos ANM extraídos en {destination}",
        "rigged_selected": "Rigs seleccionados: {count}",
        "rigged_converting": "[{index}/{total}] Exportando modelo riggeado {path}",
        "rigged_ok": "  RIG OK: {vertices} vértices, {triangles} triángulos, {bones} huesos",
        "raw_progress": "Extraídos {count} archivos...",
        "raw_done": "Extracción raw terminada: {count} archivos",
        "geometry_selected": "Archivos de geometría seleccionados: {count}",
        "converting": "[{index}/{total}] Convirtiendo {path}",
        "no_submeshes": "No se encontraron submeshes triangulados compatibles.",
        "conversion_ok": "  OK: {vertices} vértices, {triangles} triángulos, {materials} materiales",
        "texture_missing": "Textura no encontrada: {texture}",
        "texture_convert_failed": "No se pudo convertir la textura para glTF: {texture} ({error})",
        "invalid_categories": "Categorías inválidas: {categories}",
        "done_cli": "Listo: {output}",
        "tk_unavailable": "Tkinter no está disponible: {error}",
        "language": "Lenguaje",
        "input_label": "Localizar y seleccionar Game.cod:",
        "output_label": "Carpeta de salida:",
        "browse": "Examinar",
        "select_input_title": "Seleccionar Game.cod",
        "game_cod_files": "Archivo Game COD",
        "cod_files": "Archivos COD",
        "zip_files": "Copias ZIP",
        "all_files": "Todos los archivos",
        "select_output_title": "Seleccionar carpeta de salida",
        "categories": "Categorías",
        "characters": "Personajes",
        "vehicles": "Vehículos",
        "weapons": "Armas",
        "maps": "Mapas",
        "menu_models": "Modelos del menú",
        "options": "Opciones",
        "convert_geometry": "Convertir SCA/LOD/DET a OBJ + MTL",
        "extract_raw": "Extraer todos los archivos raw",
        "include_lod": "Convertir LOD aunque exista SCA",
        "all_lods": "Exportar todos los niveles LOD",
        "z_up": "Z-up (solo para armas y efectos)",
        "flip_v": "Invertir V de UV (No usar con modelos glTF 2.0)",
        "ready": "Listo",
        "start": "Extraer / Convertir",
        "select_category": "Seleccioná al menos una categoría.",
        "finished_log": "TERMINADO: {output}",
        "finished_message": "Exportación terminada.\n\n{output}",
        "missing_paths": "Seleccioná Game.cod y una carpeta de salida.",
        "error_title": "Error",
        "warning_title": "Faltan datos",
    },
}


I18N["en"].update({
    "mode_extraction": "Asset Extraction",
    "mode_modding": "Modding",
    "game_folder": "Game installation folder:",
    "mods_folder": "Mods folder:",
    "select_game_folder": "Select the T3 installation folder",
    "select_mods_folder": "Select the mods folder",
    "mod_projects": "Mod projects and load order (top has highest priority)",
    "create_mod": "Create mod",
    "open_mod_files": "Open mod folder",
    "toggle_mod": "Enable / Disable",
    "move_up": "Move up",
    "move_down": "Move down",
    "refresh": "Refresh",
    "build_mods": "Build Mods + Modded EXE",
    "install_loader": "Rebuild Modded EXE",
    "launch_modded": "Launch T3 Modded",
    "mod_ready": "Modding mode ready",
    "mod_missing_paths": "Select the game installation folder and mods folder.",
    "mod_name_prompt": "Mod name:",
    "mod_author_prompt": "Author (optional):",
    "mod_created": "Created mod project: {name}",
    "mod_building": "Building enabled mods and T3_Modded.exe...",
    "mod_build_done": "Built {files} files from {mods} enabled mods: {output}",
    "mod_conflicts": "Conflicts resolved by load order (top wins): {count}",
    "loader_installing": "Rebuilding T3_Modded.exe from the original T3.exe...",
    "loader_done": "Created {output}. The original T3.exe was not modified.",
    "mod_launched": "Started T3_Modded.exe",
    "no_mod_selected": "Select a mod project first.",
    "project_details": "{status} {name} | ID: {id} | Version: {version} | Files: {files} | EXE patches: {patches}",
    "enabled": "ENABLED",
    "disabled": "DISABLED",
    "modding_note": "Put native game files under files/ and optional executable patch manifests under patches/executable.json. Build combines every enabled mod into one Mods.Cod and one T3_Modded.exe. The top enabled mod has highest priority for duplicate files.",
    "loader_note": "Build Mods + Modded EXE always rebuilds T3_Modded.exe from the original T3.exe, loads mods/Mods.Cod, and applies patches/executable.json from all enabled mods. T3.exe remains untouched.",
})
I18N["es"].update({
    "mode_extraction": "Extracción de assets",
    "mode_modding": "Modding",
    "game_folder": "Carpeta de instalación del juego:",
    "mods_folder": "Carpeta de mods:",
    "select_game_folder": "Seleccionar la carpeta de instalación de T3",
    "select_mods_folder": "Seleccionar la carpeta de mods",
    "mod_projects": "Proyectos de mods y orden de carga (arriba tiene mayor prioridad)",
    "create_mod": "Crear mod",
    "open_mod_files": "Abrir carpeta del mod",
    "toggle_mod": "Activar / Desactivar",
    "move_up": "Subir",
    "move_down": "Bajar",
    "refresh": "Actualizar",
    "build_mods": "Compilar Mods + EXE modificado",
    "install_loader": "Reconstruir EXE modificado",
    "launch_modded": "Ejecutar T3 Modded",
    "mod_ready": "Modo Modding listo",
    "mod_missing_paths": "Seleccioná la carpeta de instalación del juego y la carpeta de mods.",
    "mod_name_prompt": "Nombre del mod:",
    "mod_author_prompt": "Autor (opcional):",
    "mod_created": "Proyecto de mod creado: {name}",
    "mod_building": "Compilando mods habilitados y T3_Modded.exe...",
    "mod_build_done": "Se compilaron {files} archivos de {mods} mods habilitados: {output}",
    "mod_conflicts": "Conflictos resueltos por orden de carga (gana el de arriba): {count}",
    "loader_installing": "Reconstruyendo T3_Modded.exe desde el T3.exe original...",
    "loader_done": "Se creó {output}. El T3.exe original no fue modificado.",
    "mod_launched": "Se inició T3_Modded.exe",
    "no_mod_selected": "Seleccioná primero un proyecto de mod.",
    "project_details": "{status} {name} | ID: {id} | Versión: {version} | Archivos: {files} | Parches EXE: {patches}",
    "enabled": "ACTIVADO",
    "disabled": "DESACTIVADO",
    "modding_note": "Colocá archivos nativos dentro de files/ y parches opcionales del ejecutable en patches/executable.json. La compilación combina todos los mods habilitados en un único Mods.Cod y T3_Modded.exe. El mod habilitado que está más arriba tiene mayor prioridad para archivos duplicados.",
    "loader_note": "Compilar Mods + EXE modificado siempre reconstruye T3_Modded.exe desde el T3.exe original, carga mods/Mods.Cod y aplica patches/executable.json de todos los mods habilitados. T3.exe queda intacto.",
})


def tr(language: str, key: str, **values: object) -> str:
    language = language if language in I18N else "en"
    template = I18N[language].get(key, I18N["en"].get(key, key))
    return template.format(**values)


def settings_path() -> Path:
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / APP_NAME / "settings.json"
    return Path.home() / ".config" / "t3-modtools" / "settings.json"


def legacy_settings_path() -> Path:
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "T3 Asset Tool" / "settings.json"
    return Path.home() / ".config" / "t3_asset_tool" / "settings.json"


def load_settings() -> dict[str, str]:
    defaults = {"language": "en", "input_path": "", "output_path": "", "mode": "extract", "game_folder": "", "mods_folder": ""}
    path = settings_path()
    if not path.is_file():
        legacy = legacy_settings_path()
        if legacy.is_file():
            path = legacy
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            for key in defaults:
                value = loaded.get(key)
                if isinstance(value, str):
                    defaults[key] = value
    except (OSError, ValueError, TypeError):
        pass
    if defaults["language"] not in I18N:
        defaults["language"] = "en"
    return defaults


def save_settings(settings: dict[str, str]) -> None:
    path = settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        # Settings persistence must never prevent the extractor from opening or running.
        pass


def norm_arc_path(value: str) -> str:
    return value.replace("\\", "/").lstrip("./").lower()


def safe_component(value: str, fallback: str = "unnamed") -> str:
    value = value.strip().strip('"').replace("|", "_").replace("/", "_").replace("\\", "_")
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_.")
    return value[:120] or fallback


def quoted_value(text: str, key: str, default: str = "") -> str:
    m = re.search(rf"\b{re.escape(key)}\b\s*[\t ]*\"([^\"]*)\"", text)
    if m:
        return m.group(1)
    m = re.search(rf"\b{re.escape(key)}\b\s*[\t ]*([^\s{{}}]+)", text)
    return m.group(1).strip('"') if m else default


def numeric_value(text: str, key: str, default: float = 0.0) -> float:
    m = re.search(rf"\b{re.escape(key)}\b\s*[\t ]*\"?({NUMBER_RE.pattern})\"?", text)
    return float(m.group(1)) if m else default


def brace_end(text: str, opening_brace: int, limit: Optional[int] = None) -> int:
    depth = 0
    end = len(text) if limit is None else min(limit, len(text))
    in_quote = False
    escaped = False
    i = opening_brace
    while i < end:
        ch = text[i]
        if in_quote:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_quote = False
        else:
            if ch == '"':
                in_quote = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    raise ValueError(f"Unclosed block at byte/character {opening_brace}")


def iter_blocks(text: str, keyword: str, start: int = 0, end: Optional[int] = None) -> Iterator[tuple[int, int, str]]:
    """Yield non-overlapping `keyword { ... }` blocks."""
    lim = len(text) if end is None else min(end, len(text))
    pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(keyword)}\s*\{{")
    pos = start
    while pos < lim:
        m = pattern.search(text, pos, lim)
        if not m:
            break
        op = text.find("{", m.start(), m.end())
        cl = brace_end(text, op, lim)
        yield m.start(), cl + 1, text[op + 1 : cl]
        pos = cl + 1


def data_block(text: str, label: str) -> Optional[str]:
    pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(label)}\s*\{{")
    m = pattern.search(text)
    if not m:
        return None
    op = text.find("{", m.start(), m.end())
    cl = brace_end(text, op)
    return text[op + 1 : cl]


def parse_float_tuples(text: Optional[str], width: int, expected: Optional[int] = None) -> list[tuple[float, ...]]:
    if not text:
        return []
    vals = [float(x) for x in NUMBER_RE.findall(text)]
    if expected is not None:
        vals = vals[: expected * width]
    usable = len(vals) - (len(vals) % width)
    return [tuple(vals[i : i + width]) for i in range(0, usable, width)]


def parse_int_tuples(text: Optional[str], width: int, expected_groups: Optional[int] = None) -> list[tuple[int, ...]]:
    if not text:
        return []
    vals = [int(x) for x in INT_RE.findall(text)]
    if expected_groups is not None:
        vals = vals[: expected_groups * width]
    usable = len(vals) - (len(vals) % width)
    return [tuple(vals[i : i + width]) for i in range(0, usable, width)]


class VirtualGameFS:
    """Case-insensitive patch-overlay view over one or more COD/ZIP archives."""

    def __init__(self, input_path: Path, log: Callable[[str], None] = print, language: str = "en"):
        self.input_path = input_path
        self.log = log
        self.language = language if language in I18N else "en"
        self._temp: Optional[tempfile.TemporaryDirectory] = None
        self._archives: list[tuple[Path, zipfile.ZipFile]] = []
        self._index: dict[str, tuple[zipfile.ZipFile, str]] = {}
        archive_paths = self._discover_archives(input_path)
        if not archive_paths:
            raise FileNotFoundError(tr(self.language, "no_archives"))
        archive_paths = self._sort_archives(archive_paths)
        for p in archive_paths:
            z = zipfile.ZipFile(p, "r")
            self._archives.append((p, z))
            self.log(tr(self.language, "opening_archive", name=p.name, entries=len(z.infolist())))
            for info in z.infolist():
                if info.is_dir():
                    continue
                self._index[norm_arc_path(info.filename)] = (z, info.filename)
        self.log(tr(self.language, "combined_view", files=len(self._index)))

    def _discover_archives(self, p: Path) -> list[Path]:
        if p.is_dir():
            return [x for x in p.iterdir() if x.is_file() and x.suffix.lower() == ".cod" and zipfile.is_zipfile(x)]
        if not p.is_file():
            return []
        if p.suffix.lower() == ".cod" and zipfile.is_zipfile(p):
            return [p]
        if p.suffix.lower() == ".zip" and zipfile.is_zipfile(p):
            self._temp = tempfile.TemporaryDirectory(prefix="t3asset_cod_")
            out = Path(self._temp.name)
            result: list[Path] = []
            with zipfile.ZipFile(p, "r") as outer:
                cod_entries = [i for i in outer.infolist() if not i.is_dir() and i.filename.lower().endswith(".cod")]
                if not cod_entries:
                    return []
                self.log(tr(self.language, "outer_zip", count=len(cod_entries)))
                for i, info in enumerate(cod_entries):
                    dst = out / f"{i:02d}_{PurePosixPath(info.filename).name}"
                    with outer.open(info) as src, dst.open("wb") as fh:
                        shutil.copyfileobj(src, fh, length=4 * 1024 * 1024)
                    if zipfile.is_zipfile(dst):
                        result.append(dst)
            return result
        return []

    @staticmethod
    def _sort_archives(paths: list[Path]) -> list[Path]:
        def key(p: Path) -> tuple[int, str]:
            n = p.name.lower()
            if "game.cod" in n:
                return (0, n)
            if "language.cod" in n:
                return (1, n)
            if "patch" in n:
                return (2, n)
            return (1, n)
        return sorted(paths, key=key)

    def close(self) -> None:
        for _, z in self._archives:
            z.close()
        self._archives.clear()
        if self._temp:
            self._temp.cleanup()
            self._temp = None

    def __enter__(self) -> "VirtualGameFS":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def paths(self) -> list[str]:
        return sorted(self._index.keys())

    def actual_name(self, path: str) -> Optional[str]:
        item = self._index.get(norm_arc_path(path))
        return item[1] if item else None

    def exists(self, path: str) -> bool:
        return norm_arc_path(path) in self._index

    def read_bytes(self, path: str) -> bytes:
        item = self._index.get(norm_arc_path(path))
        if not item:
            raise FileNotFoundError(path)
        z, actual = item
        return z.read(actual)

    def read_text(self, path: str) -> str:
        data = self.read_bytes(path)
        for enc in ("utf-8-sig", "cp1252", "latin1"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                pass
        return data.decode("latin1", errors="replace")

    def extract(self, path: str, destination: Path) -> Path:
        data = self.read_bytes(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return destination

    def resolve_texture(self, texture_ref: str, texture_library: str, source_path: str) -> Optional[str]:
        ref = texture_ref.replace("\\", "/").lstrip("/")
        lib = texture_library.replace("\\", "/").strip("/")
        source_dir = str(PurePosixPath(source_path).parent)
        refs: list[str] = []
        for ext in (None, ".dds", ".tga", ".png", ".jpg"):
            candidate_ref = ref if ext is None else str(PurePosixPath(ref).with_suffix(ext))
            refs.extend([
                f"{lib}/{candidate_ref}" if lib else candidate_ref,
                f"{source_dir}/{candidate_ref}" if source_dir else candidate_ref,
                candidate_ref,
            ])
        for candidate in refs:
            n = norm_arc_path(candidate)
            if n in self._index:
                return n
        # Last resort: same basename, preferring the library/source folder.
        stems = {PurePosixPath(ref).stem.lower()}
        matches = [p for p in self._index if PurePosixPath(p).stem.lower() in stems and PurePosixPath(p).suffix.lower() in {".dds", ".tga", ".png", ".jpg"}]
        if not matches:
            return None
        def score(path: str) -> tuple[int, int, str]:
            prefix_score = 0 if (lib and path.startswith(norm_arc_path(lib) + "/")) else 1
            source_score = 0 if path.startswith(norm_arc_path(source_dir) + "/") else 1
            return (prefix_score, source_score, path)
        return sorted(matches, key=score)[0]


@dataclass
class MaterialDef:
    name: str
    base_texture: str = ""
    lightmap: str = ""
    shader_type: str = ""


@dataclass
class Primitive:
    name: str
    material: MaterialDef
    vertices: list[tuple[float, float, float]]
    normals: list[tuple[float, float, float]]
    uv0: list[tuple[float, float]]
    uv1: list[tuple[float, float]]
    triangles: list[tuple[int, int, int]]
    mesh_name: str = ""
    lod_min: float = 0.0


@dataclass
class ConversionResult:
    source: str
    obj: Optional[str]
    vertices: int = 0
    triangles: int = 0
    materials: int = 0
    textures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class SCAParser:
    def parse_regular(self, text: str, source_path: str, first_lod_only: bool = True) -> list[Primitive]:
        candidates: list[Primitive] = []
        for mesh_idx, (_, _, mesh_block) in enumerate(iter_blocks(text, "cMesh")):
            first_sub = re.search(r"(?<![A-Za-z0-9_])cSubMesh\s*\{", mesh_block)
            header = mesh_block[: first_sub.start()] if first_sub else mesh_block
            mesh_name = quoted_value(header, "Name", f"mesh_{mesh_idx}")
            lod_min = numeric_value(header, "LODMin", 0.0)
            for sub_idx, (_, _, sub) in enumerate(iter_blocks(mesh_block, "cSubMesh")):
                vcount = int(numeric_value(sub, "VertexNumber", 0))
                vertices = parse_float_tuples(data_block(sub, "Coordinates"), 3, vcount or None)
                normals = parse_float_tuples(data_block(sub, "Normals"), 3, vcount or None)
                uv0 = parse_float_tuples(data_block(sub, "Textcoord0"), 2, vcount or None)
                uv1 = parse_float_tuples(data_block(sub, "Textcoord1"), 2, vcount or None)
                index_count = int(numeric_value(sub, "IndexNumber", 0))
                triangles = parse_int_tuples(data_block(sub, "Indices"), 3, (index_count // 3) if index_count else None)
                if not vertices or not triangles:
                    continue
                sub_name = quoted_value(sub, "Name", f"submesh_{sub_idx}")
                shader_block = next(iter_blocks(sub, "Shader"), None)
                shader_text = shader_block[2] if shader_block else sub
                base_tex = quoted_value(shader_text, "BaseTexture", "")
                lightmap = quoted_value(shader_text, "Lightmap", "")
                shader_type = quoted_value(shader_text, "Type", "")
                mat_name = safe_component(f"{PurePosixPath(base_tex).stem or 'material'}_{mesh_idx}_{sub_idx}", "material")
                candidates.append(Primitive(
                    name=safe_component(f"{mesh_name}_{sub_name}", f"primitive_{len(candidates)}"),
                    material=MaterialDef(mat_name, base_tex, lightmap, shader_type),
                    vertices=vertices,
                    normals=normals,
                    uv0=uv0,
                    uv1=uv1,
                    triangles=triangles,
                    mesh_name=mesh_name,
                    lod_min=lod_min,
                ))
        if not first_lod_only or not source_path.lower().endswith(".lod"):
            return candidates
        # Keep only the nearest LOD for every logical mesh name.
        best: dict[str, float] = {}
        for p in candidates:
            k = p.mesh_name.lower()
            best[k] = min(best.get(k, p.lod_min), p.lod_min)
        return [p for p in candidates if p.lod_min == best[p.mesh_name.lower()]]

    def parse_map(self, text: str, source_path: str, log: Callable[[str], None] = print, language: str = "en") -> tuple[list[list[tuple[float, float, float]]], list[list[tuple[float, float, float]]], list[list[tuple[float, float]]], list[MaterialDef], dict[tuple[int, int], list[tuple[int, int, int]]]]:
        tree_info = next(iter_blocks(text, "cBinaryTree"), None)
        if not tree_info:
            raise ValueError(tr(language, "no_binary_tree"))
        tree = tree_info[2]
        first_vb = re.search(r"(?<![A-Za-z0-9_])cVertexBuffer\s*\{", tree)
        shader_region = tree[: first_vb.start()] if first_vb else tree
        materials: list[MaterialDef] = []
        for sid, (_, _, sh) in enumerate(iter_blocks(shader_region, "Shader")):
            base = quoted_value(sh, "BaseTexture", "")
            light = quoted_value(sh, "Lightmap", "")
            stype = quoted_value(sh, "Type", "")
            materials.append(MaterialDef(f"shader_{sid:04d}_{safe_component(PurePosixPath(base).stem, 'material')}", base, light, stype))
        log(tr(language, "map_shaders", count=len(materials)))

        all_v: list[list[tuple[float, float, float]]] = []
        all_n: list[list[tuple[float, float, float]]] = []
        all_uv: list[list[tuple[float, float]]] = []
        for vid, (_, _, vb) in enumerate(iter_blocks(tree, "cVertexBuffer")):
            vcount = int(numeric_value(vb, "VertexNumber", 0))
            verts = parse_float_tuples(data_block(vb, "Coordinates"), 3, vcount or None)
            norms = parse_float_tuples(data_block(vb, "Normals"), 3, vcount or None)
            uv0 = parse_float_tuples(data_block(vb, "Textcoord0"), 2, vcount or None)
            all_v.append(verts)
            all_n.append(norms)
            all_uv.append(uv0)
            log(tr(language, "map_buffer", buffer_id=vid, count=len(verts)))

        grouped: dict[tuple[int, int], list[tuple[int, int, int]]] = defaultdict(list)
        seen: dict[tuple[int, int], set[tuple[int, int, int]]] = defaultdict(set)
        list_count = 0
        for _, _, lst in iter_blocks(tree, "List"):
            vb_id = int(numeric_value(lst, "VBufferId", -1))
            shader_id = int(numeric_value(lst, "ShaderId", -1))
            tri_count = int(numeric_value(lst, "TriangleNumber", 0))
            tris = parse_int_tuples(data_block(lst, "Triangles"), 3, tri_count or None)
            if vb_id < 0 or vb_id >= len(all_v):
                continue
            key = (vb_id, shader_id)
            for tri in tris:
                if max(tri) >= len(all_v[vb_id]) or min(tri) < 0:
                    continue
                if tri not in seen[key]:
                    seen[key].add(tri)
                    grouped[key].append(tri)
            list_count += 1
        log(tr(language, "map_tree", lists=list_count, triangles=sum(len(v) for v in grouped.values())))
        return all_v, all_n, all_uv, materials, grouped


class OBJExporter:
    def __init__(self, z_up: bool = True, flip_v: bool = True, mirror_x: bool = True):
        self.z_up = z_up
        self.flip_v = flip_v
        self.mirror_x = mirror_x

    def vec3(self, v: tuple[float, float, float]) -> tuple[float, float, float]:
        x, y, z = v
        transformed = (x, -z, y) if self.z_up else (x, y, z)
        if self.mirror_x:
            transformed = (-transformed[0], transformed[1], transformed[2])
        return transformed

    def triangle_indices(self, a: int, b: int, c: int) -> tuple[int, int, int]:
        # A mirror changes handedness. Reverse winding so front faces and normals stay correct.
        return (a, c, b) if self.mirror_x else (a, b, c)

    def uv(self, uv: tuple[float, float]) -> tuple[float, float]:
        u, v = uv
        return (u, 1.0 - v) if self.flip_v else (u, v)

    def export_regular(self, primitives: list[Primitive], obj_path: Path, texture_paths: dict[str, str]) -> tuple[int, int, int]:
        obj_path.parent.mkdir(parents=True, exist_ok=True)
        mtl_path = obj_path.with_suffix(".mtl")
        unique_materials: dict[str, MaterialDef] = {}
        for p in primitives:
            unique_materials[p.material.name] = p.material
        self._write_mtl(mtl_path, unique_materials.values(), texture_paths)
        v_off = vt_off = vn_off = 1
        vertices_total = triangles_total = 0
        with obj_path.open("w", encoding="utf-8", newline="\n") as out:
            out.write(f"# Exported by {APP_NAME} {APP_VERSION}\n")
            out.write(f"mtllib {mtl_path.name}\n")
            for p in primitives:
                out.write(f"\no {safe_component(p.name)}\n")
                out.write(f"usemtl {p.material.name}\n")
                for v in p.vertices:
                    x, y, z = self.vec3(v)
                    out.write(f"v {x:.7g} {y:.7g} {z:.7g}\n")
                has_uv = len(p.uv0) == len(p.vertices)
                has_n = len(p.normals) == len(p.vertices)
                if has_uv:
                    for uv in p.uv0:
                        u, vv = self.uv(uv)
                        out.write(f"vt {u:.7g} {vv:.7g}\n")
                if has_n:
                    for n in p.normals:
                        x, y, z = self.vec3(n)
                        out.write(f"vn {x:.7g} {y:.7g} {z:.7g}\n")
                for a, b, c in p.triangles:
                    if max(a, b, c) >= len(p.vertices):
                        continue
                    ids = list(self.triangle_indices(a, b, c))
                    refs = []
                    for i in ids:
                        vi = v_off + i
                        if has_uv and has_n:
                            refs.append(f"{vi}/{vt_off+i}/{vn_off+i}")
                        elif has_uv:
                            refs.append(f"{vi}/{vt_off+i}")
                        elif has_n:
                            refs.append(f"{vi}//{vn_off+i}")
                        else:
                            refs.append(str(vi))
                    out.write("f " + " ".join(refs) + "\n")
                    triangles_total += 1
                vertices_total += len(p.vertices)
                v_off += len(p.vertices)
                if has_uv:
                    vt_off += len(p.uv0)
                if has_n:
                    vn_off += len(p.normals)
        return vertices_total, triangles_total, len(unique_materials)

    def export_map(self, all_v: list[list[tuple[float, float, float]]], all_n: list[list[tuple[float, float, float]]], all_uv: list[list[tuple[float, float]]], materials: list[MaterialDef], grouped: dict[tuple[int, int], list[tuple[int, int, int]]], obj_path: Path, texture_paths: dict[str, str]) -> tuple[int, int, int]:
        obj_path.parent.mkdir(parents=True, exist_ok=True)
        mtl_path = obj_path.with_suffix(".mtl")
        used_ids = sorted({sid for _, sid in grouped if 0 <= sid < len(materials)})
        self._write_mtl(mtl_path, [materials[i] for i in used_ids], texture_paths)
        offsets: list[int] = []
        current = 1
        for verts in all_v:
            offsets.append(current)
            current += len(verts)
        with obj_path.open("w", encoding="utf-8", newline="\n") as out:
            out.write(f"# Static map exported by {APP_NAME} {APP_VERSION}\n")
            out.write("# OBJ stores UV0/base textures. Lightmap references are preserved in the MTL comments/manifest.\n")
            out.write(f"mtllib {mtl_path.name}\n")
            for verts in all_v:
                for v in verts:
                    x, y, z = self.vec3(v)
                    out.write(f"v {x:.7g} {y:.7g} {z:.7g}\n")
            for bid, uvs in enumerate(all_uv):
                # Keep one vt per vertex. Missing UVs get 0,0 so offsets remain aligned.
                count = len(all_v[bid])
                for i in range(count):
                    uv = uvs[i] if i < len(uvs) else (0.0, 0.0)
                    u, vv = self.uv(uv)
                    out.write(f"vt {u:.7g} {vv:.7g}\n")
            for bid, norms in enumerate(all_n):
                count = len(all_v[bid])
                for i in range(count):
                    n = norms[i] if i < len(norms) else (0.0, 1.0, 0.0)
                    x, y, z = self.vec3(n)
                    out.write(f"vn {x:.7g} {y:.7g} {z:.7g}\n")
            tri_total = 0
            for (bid, sid), tris in sorted(grouped.items()):
                mat = materials[sid].name if 0 <= sid < len(materials) else f"shader_{sid}"
                out.write(f"\ng buffer_{bid}_shader_{sid}\nusemtl {mat}\n")
                off = offsets[bid]
                for a, b, c in tris:
                    refs = [f"{off+i}/{off+i}/{off+i}" for i in self.triangle_indices(a, b, c)]
                    out.write("f " + " ".join(refs) + "\n")
                    tri_total += 1
        return sum(map(len, all_v)), tri_total, len(used_ids)

    @staticmethod
    def _write_mtl(path: Path, materials: Iterable[MaterialDef], texture_paths: dict[str, str]) -> None:
        with path.open("w", encoding="utf-8", newline="\n") as out:
            out.write(f"# Exported by {APP_NAME} {APP_VERSION}\n")
            for mat in materials:
                out.write(f"\nnewmtl {mat.name}\nKd 1 1 1\nKa 0 0 0\nKs 0 0 0\n")
                if mat.shader_type:
                    out.write(f"# T3 shader: {mat.shader_type}\n")
                if mat.base_texture:
                    resolved = texture_paths.get(mat.base_texture.lower(), mat.base_texture)
                    out.write(f"map_Kd {resolved.replace(os.sep, '/')}\n")
                if mat.lightmap:
                    resolved = texture_paths.get(mat.lightmap.lower(), mat.lightmap)
                    out.write(f"# T3 lightmap (UV1): {resolved.replace(os.sep, '/')}\n")


class AssetTool:
    AUDIO_PREFIXES = ("sound11/", "sound22/", "sound44/", "musics/")
    EFFECT_PREFIXES = ("particles/", "textures/particles/", "shaders/", "bases/")
    EFFECT_EXTENSIONS = {".dat", ".dds", ".tga", ".png", ".jpg", ".sca", ".lod", ".fxs", ".vso", ".pso", ".shd", ".cfg"}
    EFFECT_KEYWORDS = {
        "bullet", "impact", "muzzle", "fire", "flame", "spark", "smoke", "dust",
        "explosion", "explode", "glow", "laser", "plasma", "beam", "decal", "blood",
        "case", "shell", "static", "signal", "engine", "boom", "flash", "missile",
        "particle", "lovesnyom", "szikra", "robbanas", "villam", "por01", "por02",
    }
    REFERENCE_RE = re.compile(
        r"(?i)([A-Za-z0-9_./\\-]+\.(?:dds|tga|png|jpg|sca|lod|det|dat|fxs|vso|pso|shd))"
    )

    def __init__(self, vfs: VirtualGameFS, output: Path, log: Callable[[str], None] = print, z_up: bool = True, flip_v: bool = True, language: str = "en"):
        self.vfs = vfs
        self.output = output
        self.log = log
        self.language = language if language in I18N else "en"
        self.parser = SCAParser()
        # Characters, vehicles and maps retain the game's native orientation.
        # The only mandatory geometric transform for them is the requested global X mirror.
        self.native_exporter = OBJExporter(z_up=False, flip_v=flip_v, mirror_x=True)
        # The optional Blender axis conversion is retained only for weapons/effect models.
        self.blender_exporter = OBJExporter(z_up=z_up, flip_v=flip_v, mirror_x=True)
        self.results: list[ConversionResult] = []
        self.rigged_results: list[RiggedExportResult] = []
        self.extractions: list[dict[str, object]] = []
        self.texture_cache: dict[str, str] = {}
        self._effect_paths_cache: Optional[set[str]] = None

    @classmethod
    def is_audio_path(cls, path: str) -> bool:
        p = norm_arc_path(path)
        return p.startswith(cls.AUDIO_PREFIXES)

    @classmethod
    def is_obvious_effect_path(cls, path: str) -> bool:
        p = norm_arc_path(path)
        pp = PurePosixPath(p)
        if p.startswith(cls.EFFECT_PREFIXES):
            return True
        if p.startswith("scene/") and pp.name == "scene.fxs":
            return True
        if p.startswith("weapons/") and pp.name in {"bullets.sca", "bullets.lod"}:
            return True
        if cls.is_audio_path(p):
            return False
        return pp.suffix.lower() in cls.EFFECT_EXTENSIONS and any(k in pp.name.lower() for k in cls.EFFECT_KEYWORDS)

    def effect_paths(self) -> set[str]:
        if self._effect_paths_cache is not None:
            return self._effect_paths_cache

        all_paths = set(self.vfs.paths())
        selected = {p for p in all_paths if self.is_obvious_effect_path(p)}

        # Resolve direct file references found in particle/effect definitions.
        # Iterate because one referenced text asset may reference another asset.
        for _ in range(4):
            before = len(selected)
            for source in list(selected):
                ext = PurePosixPath(source).suffix.lower()
                if ext not in {".dat", ".fxs", ".sca", ".lod", ".shd", ".cfg"}:
                    continue
                try:
                    body = self.vfs.read_text(source)
                except Exception:
                    continue
                source_dir = str(PurePosixPath(source).parent)
                library = quoted_value(body[:20000], "TextureLibrary", "")
                for match in self.REFERENCE_RE.findall(body):
                    ref = match.replace("\\", "/").lstrip("./")
                    candidates = [
                        norm_arc_path(ref),
                        norm_arc_path(f"{source_dir}/{ref}"),
                        norm_arc_path(f"{library}/{ref}") if library else "",
                    ]
                    for candidate in candidates:
                        if candidate and candidate in all_paths:
                            selected.add(candidate)
                            break
                    else:
                        resolved = self.vfs.resolve_texture(ref, library, source)
                        if resolved:
                            selected.add(resolved)
            if len(selected) == before:
                break

        self._effect_paths_cache = selected
        return selected

    def categories_for(self, path: str) -> set[str]:
        p = norm_arc_path(path)
        categories: set[str] = set()
        if p.startswith("ca/"):
            categories.add("characters")
        if p.startswith("vehicles/"):
            categories.add("vehicles")
        if p.startswith("weapons/"):
            categories.add("weapons")
        if p.startswith("scene/"):
            categories.add("maps")
        if p.startswith("menudatas/3dmodells/") and PurePosixPath(p).suffix.lower() == ".sca":
            categories.add("menu_models")
        if PurePosixPath(p).suffix.lower() == ".anm":
            categories.add("animations")
        if self.is_audio_path(p):
            categories.add("audio")
        if p in self.effect_paths():
            categories.add("effects")
        if not categories:
            categories.add("other")
        return categories

    def selected(self, path: str, categories: set[str]) -> bool:
        return "all" in categories or bool(self.categories_for(path) & categories)

    def exporter_for(self, path: str) -> OBJExporter:
        """Choose orientation per asset category.

        Characters, vehicles and maps must not receive the old fixed X-axis
        rotation (Y-up -> Z-up). They are exported in native orientation with
        only the global X mirror. Weapons and effect models may still use the
        optional Blender conversion selected in the UI/CLI.
        """
        categories = self.categories_for(path)
        if categories & {"characters", "vehicles", "maps", "menu_models"}:
            return self.native_exporter
        return self.blender_exporter

    def _extract_path_set(self, paths: Iterable[str], destination_root: Path, kind: str) -> int:
        selected_paths = sorted(set(paths))
        count = 0
        bytes_total = 0
        for source in selected_paths:
            dst = destination_root / PurePosixPath(source)
            self.vfs.extract(source, dst)
            count += 1
            try:
                bytes_total += dst.stat().st_size
            except OSError:
                pass
            if count % 250 == 0:
                self.log(tr(self.language, "extract_progress", kind=tr(self.language, kind), count=count))
        self.extractions.append({
            "kind": kind,
            "destination": str(destination_root),
            "files": count,
            "bytes": bytes_total,
        })
        self.log(tr(self.language, "extract_done", kind=tr(self.language, kind), count=count, destination=destination_root))
        return count

    def extract_effects(self) -> int:
        paths = self.effect_paths()
        return self._extract_path_set(paths, self.output / "effects", "effects")

    def audio_paths(self) -> set[str]:
        return {p for p in self.vfs.paths() if self.is_audio_path(p)}

    def extract_audio(self) -> int:
        return self._extract_path_set(self.audio_paths(), self.output / "audio", "audio")

    def animation_paths(self) -> set[str]:
        return {p for p in self.vfs.paths() if PurePosixPath(p).suffix.lower() == ".anm"}

    def extract_animations(self) -> int:
        animation_root = self.output / "animations"
        raw_root = animation_root / "raw"
        paths = sorted(self.animation_paths())
        count = self._extract_path_set(paths, raw_root, "animations")
        summaries: list[dict[str, object]] = []
        for source in paths:
            try:
                summaries.append(parse_animation_summary(self.vfs.read_text(source), source).__dict__)
            except Exception as exc:
                summaries.append({"source": source, "error": f"{type(exc).__name__}: {exc}"})
        animation_root.mkdir(parents=True, exist_ok=True)
        (animation_root / "t3_animation_manifest.json").write_text(
            json.dumps({"tool": APP_NAME, "version": APP_VERSION, "animations": summaries}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tool_root = Path(__file__).resolve().parent
        plugin_root = tool_root / "Blender plugin"
        for filename in ("T3_Blender_ANM_Importer.py", "ANIMATION_IMPORT_README.txt"):
            candidates = (plugin_root / filename, tool_root / filename)
            source_file = next((candidate for candidate in candidates if candidate.is_file()), None)
            if source_file is not None:
                shutil.copy2(source_file, animation_root / filename)
        self.log(tr(self.language, "animation_summary", count=count, destination=animation_root))
        return count

    def convert_rigged_assets(self, categories: set[str]) -> list[RiggedExportResult]:
        """Export every compatible rig found in selected character, vehicle, or weapon categories."""
        rig_categories = {"characters", "vehicles", "weapons"}
        selected_rig_categories = rig_categories if "all" in categories else categories & rig_categories
        targets: list[str] = []
        for path in self.vfs.paths():
            if PurePosixPath(path).suffix.lower() != ".sca":
                continue
            if not (self.categories_for(path) & selected_rig_categories):
                continue
            try:
                header = self.vfs.read_text(path)
            except Exception:
                continue
            if "WeightmapNumber" in header and "cBone" in header:
                targets.append(path)
        self.log(tr(self.language, "rigged_selected", count=len(targets)))
        for index, path in enumerate(targets, 1):
            self.log(tr(self.language, "rigged_converting", index=index, total=len(targets), path=path))
            src_pp = PurePosixPath(path)
            out_dir = self.output / "converted_rigged" / src_pp.parent / f"{safe_component(src_pp.stem)}_sca"
            try:
                text = self.vfs.read_text(path)
                library = quoted_value(text[:20000], "TextureLibrary", "")
                primitives = self.parser.parse_regular(text, path, first_lod_only=True)
                warnings: list[str] = []
                mapping, _ = self._copy_material_textures(
                    [primitive.material for primitive in primitives],
                    library,
                    path,
                    out_dir,
                    warnings,
                    prepare_gltf=True,
                )
                result = export_rigged_gltf(
                    text,
                    path,
                    out_dir,
                    texture_mapping=mapping,
                    flip_v=False,
                    z_up=self.exporter_for(path).z_up,
                )
                result.warnings.extend(warnings)
                if result.gltf:
                    self.log(tr(self.language, "rigged_ok", vertices=result.vertices, triangles=result.triangles, bones=result.bones))
                else:
                    self.log("  RIG SKIPPED: " + "; ".join(result.warnings))
            except Exception as exc:
                result = RiggedExportResult(path, None, None, warnings=[f"{type(exc).__name__}: {exc}"])
                self.log(f"  RIG ERROR: {exc}")
            self.rigged_results.append(result)
        return self.rigged_results

    def convert_rigged_characters(self) -> list[RiggedExportResult]:
        """Backward-compatible alias retained for older scripts."""
        return self.convert_rigged_assets({"characters"})

    def extract_raw(self, categories: set[str]) -> int:
        count = 0
        raw_root = self.output / "raw"
        for i, path in enumerate(self.vfs.paths(), 1):
            if not self.selected(path, categories):
                continue
            dst = raw_root / PurePosixPath(path)
            self.vfs.extract(path, dst)
            count += 1
            if count % 250 == 0:
                self.log(tr(self.language, "raw_progress", count=count))
        self.extractions.append({
            "kind": "Raw",
            "destination": str(raw_root),
            "files": count,
        })
        self.log(tr(self.language, "raw_done", count=count))
        return count

    def convert(self, categories: set[str], include_lod: bool = False, first_lod_only: bool = True) -> list[ConversionResult]:
        paths = self.vfs.paths()
        sca_stems = {str(PurePosixPath(p).with_suffix("")) for p in paths if p.endswith(".sca")}
        targets: list[str] = []
        for p in paths:
            ext = PurePosixPath(p).suffix.lower()
            if ext not in {".sca", ".lod", ".det"}:
                continue
            if not self.selected(p, categories):
                continue
            if ext == ".lod" and not include_lod and str(PurePosixPath(p).with_suffix("")) in sca_stems:
                continue
            targets.append(p)
        self.log(tr(self.language, "geometry_selected", count=len(targets)))
        for idx, path in enumerate(targets, 1):
            self.log(tr(self.language, "converting", index=idx, total=len(targets), path=path))
            try:
                result = self.convert_one(path, first_lod_only=first_lod_only)
            except Exception as exc:
                result = ConversionResult(source=path, obj=None, warnings=[f"{type(exc).__name__}: {exc}"])
                self.log(f"  ERROR: {exc}")
            self.results.append(result)
        return self.results

    def convert_one(self, path: str, first_lod_only: bool = True) -> ConversionResult:
        text = self.vfs.read_text(path)
        library = quoted_value(text[:20000], "TextureLibrary", "")
        src_pp = PurePosixPath(path)
        suffix_tag = src_pp.suffix.lower().lstrip(".") or "asset"
        out_dir = self.output / "converted" / src_pp.parent / f"{safe_component(src_pp.stem)}_{suffix_tag}"
        out_dir.mkdir(parents=True, exist_ok=True)
        obj_path = out_dir / f"{safe_component(src_pp.stem)}_{suffix_tag}.obj"
        warnings: list[str] = []

        exporter = self.exporter_for(path)
        is_static_scene = PurePosixPath(path).name.lower() == "scene.sca" and "cBinaryTree" in text
        if is_static_scene:
            all_v, all_n, all_uv, mats, grouped = self.parser.parse_map(text, path, self.log, self.language)
            texture_paths, copied = self._copy_material_textures(mats, library, path, out_dir, warnings)
            v, t, m = exporter.export_map(all_v, all_n, all_uv, mats, grouped, obj_path, texture_paths)
        else:
            primitives = self.parser.parse_regular(text, path, first_lod_only=first_lod_only)
            if not primitives:
                warnings.append(tr(self.language, "no_submeshes"))
                return ConversionResult(path, None, warnings=warnings)
            mats = [p.material for p in primitives]
            texture_paths, copied = self._copy_material_textures(mats, library, path, out_dir, warnings)
            v, t, m = exporter.export_regular(primitives, obj_path, texture_paths)
        self.log(tr(self.language, "conversion_ok", vertices=v, triangles=t, materials=m))
        return ConversionResult(path, str(obj_path), v, t, m, copied, warnings)

    def _copy_material_textures(
        self,
        materials: Iterable[MaterialDef],
        library: str,
        source_path: str,
        out_dir: Path,
        warnings: list[str],
        prepare_gltf: bool = False,
    ) -> tuple[dict[str, str], list[str]]:
        mapping: dict[str, str] = {}
        copied: list[str] = []
        tex_dir = out_dir / "textures"
        used_names: dict[str, str] = {}
        for mat in materials:
            for ref in (mat.base_texture, mat.lightmap):
                if not ref or ref.lower() in mapping:
                    continue
                resolved = self.vfs.resolve_texture(ref, library, source_path)
                if not resolved:
                    warnings.append(tr(self.language, "texture_missing", texture=ref))
                    continue
                base = safe_component(PurePosixPath(resolved).name, "texture")
                key = base.lower()
                if key in used_names and used_names[key] != resolved:
                    base = safe_component(
                        PurePosixPath(resolved).stem
                        + "_"
                        + str(abs(hash(resolved)) % 100000)
                        + PurePosixPath(resolved).suffix
                    )
                used_names[base.lower()] = resolved
                dst = tex_dir / base
                if not dst.exists():
                    self.vfs.extract(resolved, dst)
                selected = dst
                copied.append(str(dst))

                if prepare_gltf and dst.suffix.lower() in {".dds", ".tga"}:
                    png_name = safe_component(dst.stem + ".png", "texture.png")
                    png_dst = tex_dir / png_name
                    try:
                        if not png_dst.exists():
                            convert_texture_file_to_png(dst, png_dst)
                        selected = png_dst
                        copied.append(str(png_dst))
                    except (TextureConversionError, OSError, ValueError) as exc:
                        warnings.append(
                            tr(self.language, "texture_convert_failed", texture=ref, error=str(exc))
                        )

                rel = os.path.relpath(selected, out_dir).replace(os.sep, "/")
                mapping[ref.lower()] = rel
        return mapping, copied

    def write_manifest(self) -> Path:
        self.output.mkdir(parents=True, exist_ok=True)
        path = self.output / "t3_export_manifest.json"
        payload = {
            "tool": APP_NAME,
            "version": APP_VERSION,
            "input": str(self.vfs.input_path),
            "global_mirror_x": True,
            "native_orientation_categories": ["characters", "vehicles", "maps", "menu_models"],
            "optional_z_up_categories": ["weapons", "effects"],
            "extractions": self.extractions,
            "results": [r.__dict__ for r in self.results],
            "rigged_results": [r.__dict__ for r in self.rigged_results],
            "notes": [
                "All exported geometry is mirrored on global X; triangle winding is reversed to preserve front faces.",
                "Characters, vehicles, maps, and menu models retain native T3 orientation and receive no fixed X-axis rotation.",
                "The optional Y-up to Z-up conversion only applies to weapons and effect models.",
                "OBJ exports use UV0 and base textures.",
                "Map lightmap filenames are retained as MTL comments, but OBJ cannot store the second UV set/lightmap relationship.",
                "Static OBJ files remain unrigged; optional glTF exports include skeletons, skin weights, UV0, and connected base-color textures for compatible characters, vehicles, and weapons.",
                "Original ANM files can be extracted with a Blender importer and an animation manifest.",
                "Menu Models selects SCA files stored under MenuDatas/3DModells in Game.cod.",
                "scene.dyn dynamic object placement is not reconstructed in this release.",
            ],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path


def parse_categories(value: str) -> set[str]:
    allowed = {"all", "characters", "vehicles", "weapons", "maps", "menu_models", "effects", "audio", "animations", "other"}
    result = {x.strip().lower() for x in value.split(",") if x.strip()}
    invalid = result - allowed
    if invalid:
        raise ValueError(tr("en", "invalid_categories", categories=", ".join(sorted(invalid))))
    return result or {"all"}


def run_cli(args: argparse.Namespace) -> int:
    categories = parse_categories(args.categories)
    out = Path(args.output).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    with VirtualGameFS(Path(args.input).expanduser().resolve(), language="en") as vfs:
        tool = AssetTool(vfs, out, z_up=not args.keep_y_up, flip_v=not args.keep_v, language="en")
        if "all" in categories or "effects" in categories:
            tool.extract_effects()
        if "all" in categories or "audio" in categories:
            tool.extract_audio()
        if "all" in categories or "animations" in categories:
            tool.extract_animations()
        if args.extract_raw:
            tool.extract_raw(categories)
        if args.convert:
            tool.convert(categories, include_lod=args.include_lod, first_lod_only=not args.all_lods)
        if args.rigged and ("all" in categories or bool(categories & {"characters", "vehicles", "weapons"})):
            tool.convert_rigged_assets(categories)
        tool.write_manifest()
    print(tr("en", "done_cli", output=out))
    return 0


def launch_gui() -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, simpledialog, ttk
    except Exception as exc:
        print(tr("en", "tk_unavailable", error=exc), file=sys.stderr)
        return 2

    saved = load_settings()
    root = tk.Tk()
    root.title(f"{APP_NAME} {APP_VERSION}")
    root.geometry("980x780")
    root.minsize(820, 650)

    language_var = tk.StringVar(value=saved["language"])
    mode_var = tk.StringVar(value=saved.get("mode", "extract"))
    input_var = tk.StringVar(value=saved["input_path"])
    output_var = tk.StringVar(value=saved["output_path"])
    game_folder_var = tk.StringVar(value=saved.get("game_folder", ""))
    mods_folder_var = tk.StringVar(value=saved.get("mods_folder", ""))
    raw_var = tk.BooleanVar(value=False)
    convert_var = tk.BooleanVar(value=True)
    lod_var = tk.BooleanVar(value=False)
    all_lods_var = tk.BooleanVar(value=False)
    zup_var = tk.BooleanVar(value=True)
    flipv_var = tk.BooleanVar(value=True)
    rigged_var = tk.BooleanVar(value=False)
    cat_vars = {
        "characters": tk.BooleanVar(value=True),
        "vehicles": tk.BooleanVar(value=True),
        "weapons": tk.BooleanVar(value=True),
        "maps": tk.BooleanVar(value=True),
        "menu_models": tk.BooleanVar(value=False),
        "effects": tk.BooleanVar(value=False),
        "audio": tk.BooleanVar(value=False),
        "animations": tk.BooleanVar(value=False),
    }

    shell = ttk.Frame(root, padding=12)
    shell.pack(fill="both", expand=True)
    shell.columnconfigure(0, weight=1)
    shell.rowconfigure(2, weight=1)

    topbar = ttk.Frame(shell)
    topbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    topbar.columnconfigure(0, weight=1)
    ttk.Label(topbar, text=f"{APP_NAME} {APP_VERSION}").grid(row=0, column=0, sticky="w")
    language_button = ttk.Menubutton(topbar)
    language_button.grid(row=0, column=1, sticky="e")
    language_menu = tk.Menu(language_button, tearoff=False)
    language_button.configure(menu=language_menu)

    mode_bar = ttk.Frame(shell)
    mode_bar.grid(row=1, column=0, sticky="ew", pady=(0, 8))
    mode_buttons = {
        "extract": ttk.Radiobutton(mode_bar, variable=mode_var, value="extract"),
        "modding": ttk.Radiobutton(mode_bar, variable=mode_var, value="modding"),
    }
    mode_buttons["extract"].pack(side="left", padx=(0, 8))
    mode_buttons["modding"].pack(side="left")

    content = ttk.Frame(shell)
    content.grid(row=2, column=0, sticky="nsew")
    content.rowconfigure(0, weight=1)
    content.columnconfigure(0, weight=1)

    extract_frame = ttk.Frame(content)
    mod_frame = ttk.Frame(content)
    for frame in (extract_frame, mod_frame):
        frame.grid(row=0, column=0, sticky="nsew")

    # Asset Extraction mode -------------------------------------------------
    main = ttk.Frame(extract_frame)
    main.pack(fill="both", expand=True)
    main.columnconfigure(1, weight=1)
    main.rowconfigure(7, weight=1)

    input_label = ttk.Label(main)
    input_label.grid(row=0, column=0, sticky="w", pady=4)
    ttk.Entry(main, textvariable=input_var).grid(row=0, column=1, sticky="ew", padx=6)
    input_button = ttk.Button(main)
    input_button.grid(row=0, column=2)

    output_label = ttk.Label(main)
    output_label.grid(row=1, column=0, sticky="w", pady=4)
    ttk.Entry(main, textvariable=output_var).grid(row=1, column=1, sticky="ew", padx=6)
    output_button = ttk.Button(main)
    output_button.grid(row=1, column=2)

    cats = ttk.LabelFrame(main, padding=8)
    cats.grid(row=2, column=0, columnspan=3, sticky="ew", pady=8)
    category_buttons: dict[str, ttk.Checkbutton] = {}
    for i, key in enumerate(("characters", "vehicles", "weapons", "maps", "menu_models", "effects", "audio", "animations")):
        button = ttk.Checkbutton(cats, variable=cat_vars[key])
        button.grid(row=i // 4, column=i % 4, padx=14, pady=3, sticky="w")
        category_buttons[key] = button

    opts = ttk.LabelFrame(main, padding=8)
    opts.grid(row=3, column=0, columnspan=3, sticky="ew")
    option_buttons = {
        "convert_geometry": ttk.Checkbutton(opts, variable=convert_var),
        "extract_raw": ttk.Checkbutton(opts, variable=raw_var),
        "include_lod": ttk.Checkbutton(opts, variable=lod_var),
        "all_lods": ttk.Checkbutton(opts, variable=all_lods_var),
        "z_up": ttk.Checkbutton(opts, variable=zup_var),
        "flip_v": ttk.Checkbutton(opts, variable=flipv_var),
        "rigged_models": ttk.Checkbutton(opts, variable=rigged_var),
    }
    option_buttons["convert_geometry"].grid(row=0, column=0, sticky="w")
    option_buttons["extract_raw"].grid(row=1, column=0, sticky="w")
    option_buttons["include_lod"].grid(row=0, column=1, sticky="w", padx=20)
    option_buttons["all_lods"].grid(row=1, column=1, sticky="w", padx=20)
    option_buttons["z_up"].grid(row=2, column=0, sticky="w")
    option_buttons["flip_v"].grid(row=2, column=1, sticky="w", padx=20)
    option_buttons["rigged_models"].grid(row=3, column=0, columnspan=2, sticky="w")

    progress = ttk.Progressbar(main, mode="indeterminate")
    progress.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(10, 4))
    status = ttk.Label(main)
    status.grid(row=5, column=0, columnspan=3, sticky="w")
    start_btn = ttk.Button(main)
    start_btn.grid(row=6, column=0, columnspan=3, pady=8)
    log_box = tk.Text(main, height=20, wrap="word")
    log_box.grid(row=7, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
    scroll = ttk.Scrollbar(main, orient="vertical", command=log_box.yview)
    scroll.grid(row=7, column=3, sticky="ns")
    log_box.configure(yscrollcommand=scroll.set)

    # Modding mode ----------------------------------------------------------
    mod_frame.columnconfigure(1, weight=1)
    mod_frame.rowconfigure(5, weight=1)

    game_folder_label = ttk.Label(mod_frame)
    game_folder_label.grid(row=0, column=0, sticky="w", pady=4)
    ttk.Entry(mod_frame, textvariable=game_folder_var).grid(row=0, column=1, sticky="ew", padx=6)
    game_folder_button = ttk.Button(mod_frame)
    game_folder_button.grid(row=0, column=2)

    mods_folder_label = ttk.Label(mod_frame)
    mods_folder_label.grid(row=1, column=0, sticky="w", pady=4)
    ttk.Entry(mod_frame, textvariable=mods_folder_var).grid(row=1, column=1, sticky="ew", padx=6)
    mods_folder_button = ttk.Button(mod_frame)
    mods_folder_button.grid(row=1, column=2)

    mod_note = ttk.Label(mod_frame, wraplength=900)
    mod_note.grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 8))

    projects_frame = ttk.LabelFrame(mod_frame, padding=8)
    projects_frame.grid(row=3, column=0, columnspan=3, sticky="nsew")
    projects_frame.columnconfigure(0, weight=1)
    projects_frame.rowconfigure(0, weight=1)
    mod_list = tk.Listbox(projects_frame, height=12, exportselection=False)
    mod_list.grid(row=0, column=0, rowspan=2, sticky="nsew")
    mod_list_scroll = ttk.Scrollbar(projects_frame, orient="vertical", command=mod_list.yview)
    mod_list_scroll.grid(row=0, column=1, rowspan=2, sticky="ns")
    mod_list.configure(yscrollcommand=mod_list_scroll.set)

    project_buttons_frame = ttk.Frame(projects_frame)
    project_buttons_frame.grid(row=0, column=2, sticky="ns", padx=(10, 0))
    mod_buttons = {
        "create_mod": ttk.Button(project_buttons_frame),
        "open_mod_files": ttk.Button(project_buttons_frame),
        "toggle_mod": ttk.Button(project_buttons_frame),
        "move_up": ttk.Button(project_buttons_frame),
        "move_down": ttk.Button(project_buttons_frame),
        "refresh": ttk.Button(project_buttons_frame),
    }
    for index, button in enumerate(mod_buttons.values()):
        button.grid(row=index, column=0, sticky="ew", pady=2)

    project_details = ttk.Label(projects_frame, wraplength=780)
    project_details.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))

    mod_actions = ttk.Frame(mod_frame)
    mod_actions.grid(row=4, column=0, columnspan=3, sticky="ew", pady=8)
    mod_action_buttons = {
        "build_mods": ttk.Button(mod_actions),
        "install_loader": ttk.Button(mod_actions),
        "launch_modded": ttk.Button(mod_actions),
    }
    mod_action_buttons["build_mods"].pack(side="left", padx=(0, 8))
    mod_action_buttons["install_loader"].pack(side="left", padx=(0, 8))
    mod_action_buttons["launch_modded"].pack(side="left")

    mod_log = tk.Text(mod_frame, height=18, wrap="word")
    mod_log.grid(row=5, column=0, columnspan=3, sticky="nsew")
    mod_log_scroll = ttk.Scrollbar(mod_frame, orient="vertical", command=mod_log.yview)
    mod_log_scroll.grid(row=5, column=3, sticky="ns")
    mod_log.configure(yscrollcommand=mod_log_scroll.set)
    loader_note = ttk.Label(mod_frame, wraplength=900)
    loader_note.grid(row=6, column=0, columnspan=3, sticky="w", pady=(8, 0))

    running = False
    mod_running = False
    save_after_id: Optional[str] = None
    mod_projects: list[ModProject] = []

    def current_language() -> str:
        value = language_var.get()
        return value if value in I18N else "en"

    def persist_settings() -> None:
        nonlocal save_after_id
        save_after_id = None
        save_settings({
            "language": current_language(),
            "input_path": input_var.get(),
            "output_path": output_var.get(),
            "mode": mode_var.get(),
            "game_folder": game_folder_var.get(),
            "mods_folder": mods_folder_var.get(),
        })

    def schedule_settings_save(*_: object) -> None:
        nonlocal save_after_id
        if save_after_id is not None:
            root.after_cancel(save_after_id)
        save_after_id = root.after(350, persist_settings)

    def browse_input() -> None:
        lang = current_language()
        selected = filedialog.askopenfilename(
            title=tr(lang, "select_input_title"),
            filetypes=[
                (tr(lang, "game_cod_files"), "Game.cod"),
                (tr(lang, "cod_files"), "*.cod"),
                (tr(lang, "zip_files"), "*.zip"),
                (tr(lang, "all_files"), "*.*"),
            ],
        )
        if selected:
            input_var.set(selected)
            persist_settings()

    def browse_output() -> None:
        lang = current_language()
        selected = filedialog.askdirectory(title=tr(lang, "select_output_title"))
        if selected:
            output_var.set(selected)
            persist_settings()

    def browse_game_folder() -> None:
        lang = current_language()
        selected = filedialog.askdirectory(title=tr(lang, "select_game_folder"))
        if selected:
            game_folder_var.set(selected)
            mods_folder_var.set(str(Path(selected) / "mods"))
            persist_settings()
            refresh_mods()

    def browse_mods_folder() -> None:
        lang = current_language()
        selected = filedialog.askdirectory(title=tr(lang, "select_mods_folder"))
        if selected:
            mods_folder_var.set(selected)
            persist_settings()
            refresh_mods()

    input_button.configure(command=browse_input)
    output_button.configure(command=browse_output)
    game_folder_button.configure(command=browse_game_folder)
    mods_folder_button.configure(command=browse_mods_folder)

    def rebuild_language_menu() -> None:
        language_menu.delete(0, "end")
        language_menu.add_radiobutton(label="English", variable=language_var, value="en", command=change_language)
        language_menu.add_radiobutton(label="Español", variable=language_var, value="es", command=change_language)

    def refresh_texts() -> None:
        lang = current_language()
        language_button.configure(text=tr(lang, "language"))
        mode_buttons["extract"].configure(text=tr(lang, "mode_extraction"), command=switch_mode)
        mode_buttons["modding"].configure(text=tr(lang, "mode_modding"), command=switch_mode)
        input_label.configure(text=tr(lang, "input_label"))
        output_label.configure(text=tr(lang, "output_label"))
        input_button.configure(text=tr(lang, "browse"))
        output_button.configure(text=tr(lang, "browse"))
        cats.configure(text=tr(lang, "categories"))
        opts.configure(text=tr(lang, "options"))
        for key, button in category_buttons.items():
            button.configure(text=tr(lang, key))
        for key, button in option_buttons.items():
            button.configure(text=tr(lang, key))
        start_btn.configure(text=tr(lang, "start"))
        if not running:
            status.configure(text=tr(lang, "ready"))
        game_folder_label.configure(text=tr(lang, "game_folder"))
        mods_folder_label.configure(text=tr(lang, "mods_folder"))
        game_folder_button.configure(text=tr(lang, "browse"))
        mods_folder_button.configure(text=tr(lang, "browse"))
        mod_note.configure(text=tr(lang, "modding_note"))
        projects_frame.configure(text=tr(lang, "mod_projects"))
        for key, button in mod_buttons.items():
            button.configure(text=tr(lang, key))
        for key, button in mod_action_buttons.items():
            button.configure(text=tr(lang, key))
        loader_note.configure(text=tr(lang, "loader_note"))
        rebuild_language_menu()
        refresh_project_details()

    def change_language() -> None:
        persist_settings()
        refresh_texts()
        refresh_mod_list()

    def switch_mode() -> None:
        if mode_var.get() == "modding":
            mod_frame.tkraise()
            refresh_mods()
        else:
            extract_frame.tkraise()
        persist_settings()

    def log(message: str) -> None:
        root.after(0, lambda value=message: (
            log_box.insert("end", value + "\n"),
            log_box.see("end"),
            status.configure(text=value[:110]),
        ))

    def mod_log_message(message: str) -> None:
        root.after(0, lambda value=message: (
            mod_log.insert("end", value + "\n"),
            mod_log.see("end"),
        ))

    def set_running(value: bool) -> None:
        nonlocal running
        running = value
        if value:
            progress.start(10)
            start_btn.configure(state="disabled")
            language_button.configure(state="disabled")
        else:
            progress.stop()
            start_btn.configure(state="normal")
            language_button.configure(state="normal")

    def set_mod_running(value: bool) -> None:
        nonlocal mod_running
        mod_running = value
        state = "disabled" if value else "normal"
        for button in mod_action_buttons.values():
            button.configure(state=state)
        for button in mod_buttons.values():
            button.configure(state=state)
        language_button.configure(state=state)

    def worker(job: dict[str, object]) -> None:
        lang = str(job["language"])
        try:
            inp = Path(str(job["input"])).expanduser().resolve()
            out = Path(str(job["output"])).expanduser().resolve()
            selected_categories = set(job["categories"])
            out.mkdir(parents=True, exist_ok=True)
            with VirtualGameFS(inp, log=log, language=lang) as vfs:
                tool = AssetTool(
                    vfs,
                    out,
                    log=log,
                    z_up=bool(job["z_up"]),
                    flip_v=bool(job["flip_v"]),
                    language=lang,
                )
                if "effects" in selected_categories:
                    tool.extract_effects()
                if "audio" in selected_categories:
                    tool.extract_audio()
                if "animations" in selected_categories:
                    tool.extract_animations()
                if bool(job["extract_raw"]):
                    tool.extract_raw(selected_categories)
                if bool(job["convert"]):
                    tool.convert(
                        selected_categories,
                        include_lod=bool(job["include_lod"]),
                        first_lod_only=not bool(job["all_lods"]),
                    )
                if bool(job["rigged_models"]) and bool(selected_categories & {"characters", "vehicles", "weapons"}):
                    tool.convert_rigged_assets(selected_categories)
                tool.write_manifest()
            log(tr(lang, "finished_log", output=out))
            root.after(0, lambda: messagebox.showinfo(APP_NAME, tr(lang, "finished_message", output=out)))
        except Exception as exc:
            log(traceback.format_exc())
            message = str(exc)
            root.after(0, lambda value=message: messagebox.showerror(tr(lang, "error_title"), value))
        finally:
            root.after(0, lambda: set_running(False))

    def start() -> None:
        lang = current_language()
        if not input_var.get().strip() or not output_var.get().strip():
            messagebox.showwarning(tr(lang, "warning_title"), tr(lang, "missing_paths"))
            return
        selected_categories = {key for key, variable in cat_vars.items() if variable.get()}
        if not selected_categories:
            messagebox.showwarning(tr(lang, "warning_title"), tr(lang, "select_category"))
            return
        persist_settings()
        job: dict[str, object] = {
            "language": lang,
            "input": input_var.get(),
            "output": output_var.get(),
            "categories": selected_categories,
            "extract_raw": raw_var.get(),
            "convert": convert_var.get(),
            "include_lod": lod_var.get(),
            "all_lods": all_lods_var.get(),
            "z_up": zup_var.get(),
            "flip_v": flipv_var.get(),
            "rigged_models": rigged_var.get(),
        }
        log_box.delete("1.0", "end")
        set_running(True)
        threading.Thread(target=worker, args=(job,), daemon=True).start()

    def manager_or_warning() -> Optional[ModManager]:
        lang = current_language()
        if not game_folder_var.get().strip() or not mods_folder_var.get().strip():
            messagebox.showwarning(tr(lang, "warning_title"), tr(lang, "mod_missing_paths"))
            return None
        return ModManager(Path(game_folder_var.get()), Path(mods_folder_var.get()), log=mod_log_message)

    def selected_project_index() -> Optional[int]:
        selection = mod_list.curselection()
        return int(selection[0]) if selection else None

    def selected_project() -> Optional[ModProject]:
        index = selected_project_index()
        return mod_projects[index] if index is not None and 0 <= index < len(mod_projects) else None

    def refresh_mod_list(select_id: str = "") -> None:
        current = selected_project()
        selected_id = select_id or (current.id if current else "")
        mod_list.delete(0, "end")
        target_index = None
        for index, project in enumerate(mod_projects):
            prefix = "[x]" if project.enabled else "[ ]"
            mod_list.insert("end", f"{prefix} {index + 1:02d}. {project.name} ({project.id}) - {project.file_count} files")
            if project.id == selected_id:
                target_index = index
        if target_index is not None:
            mod_list.selection_set(target_index)
            mod_list.see(target_index)
        refresh_project_details()

    def refresh_project_details(*_: object) -> None:
        project = selected_project()
        if not project:
            project_details.configure(text="")
            return
        lang = current_language()
        project_details.configure(text=tr(
            lang,
            "project_details",
            status=tr(lang, "enabled" if project.enabled else "disabled"),
            name=project.name,
            id=project.id,
            version=project.version,
            files=project.file_count,
            patches=project.patch_count,
        ))

    def refresh_mods() -> None:
        nonlocal mod_projects
        if not game_folder_var.get().strip() or not mods_folder_var.get().strip():
            mod_projects = []
            refresh_mod_list()
            return
        try:
            manager = ModManager(Path(game_folder_var.get()), Path(mods_folder_var.get()), log=mod_log_message)
            mod_projects = manager.discover()
            refresh_mod_list()
        except Exception as exc:
            mod_log_message(str(exc))

    def create_mod() -> None:
        manager = manager_or_warning()
        if not manager:
            return
        lang = current_language()
        name = simpledialog.askstring(APP_NAME, tr(lang, "mod_name_prompt"), parent=root)
        if not name:
            return
        author = simpledialog.askstring(APP_NAME, tr(lang, "mod_author_prompt"), parent=root) or ""
        try:
            project = manager.create_project(name, author)
            mod_log_message(tr(lang, "mod_created", name=project.name))
            refresh_mods()
            refresh_mod_list(project.id)
            open_in_file_manager(project.files_path)
        except Exception as exc:
            messagebox.showerror(tr(lang, "error_title"), str(exc))

    def open_selected_mod() -> None:
        lang = current_language()
        project = selected_project()
        if not project:
            messagebox.showwarning(tr(lang, "warning_title"), tr(lang, "no_mod_selected"))
            return
        try:
            project.files_path.mkdir(parents=True, exist_ok=True)
            project.patches_path.mkdir(parents=True, exist_ok=True)
            open_in_file_manager(project.folder)
        except Exception as exc:
            messagebox.showerror(tr(lang, "error_title"), str(exc))

    def toggle_selected_mod() -> None:
        manager = manager_or_warning()
        index = selected_project_index()
        if not manager or index is None:
            return
        mod_projects[index].enabled = not mod_projects[index].enabled
        manager.save_projects(mod_projects)
        refresh_mod_list(mod_projects[index].id)

    def move_selected(direction: int) -> None:
        manager = manager_or_warning()
        index = selected_project_index()
        if not manager or index is None:
            return
        target = index + direction
        if target < 0 or target >= len(mod_projects):
            return
        mod_projects[index], mod_projects[target] = mod_projects[target], mod_projects[index]
        manager.save_projects(mod_projects)
        refresh_mod_list(mod_projects[target].id)

    def build_mods() -> None:
        manager = manager_or_warning()
        if not manager or mod_running:
            return
        lang = current_language()
        mod_log.delete("1.0", "end")
        mod_log_message(tr(lang, "mod_building"))
        set_mod_running(True)

        def task() -> None:
            try:
                full = manager.build_all(mod_projects)
                result = full.package
                exe_result = full.executable
                mod_log_message(tr(lang, "mod_build_done", files=result.files, mods=len(result.enabled_mods), output=result.output))
                mod_log_message(f"Mods.Cod SHA-256: {result.sha256}")
                mod_log_message(tr(lang, "loader_done", output=exe_result.output))
                mod_log_message(f"Original T3.exe SHA-256: {exe_result.original_sha256}")
                mod_log_message(f"T3_Modded.exe SHA-256: {exe_result.patched_sha256}")
                if exe_result.patches_applied:
                    mod_log_message(f"Executable patches applied: {len(exe_result.patches_applied)}")
                    for patch in exe_result.patches_applied:
                        mod_log_message(f"  {patch.mod_id}/{patch.patch_id} @ 0x{patch.file_offset:X} ({patch.size} bytes)")
                if result.conflicts:
                    mod_log_message(tr(lang, "mod_conflicts", count=len(result.conflicts)))
                    for conflict in result.conflicts[:30]:
                        mod_log_message(f"  {conflict.path}: {conflict.previous_mod} -> {conflict.winning_mod}")
            except Exception as exc:
                mod_log_message(traceback.format_exc())
                root.after(0, lambda value=str(exc): messagebox.showerror(tr(lang, "error_title"), value))
            finally:
                root.after(0, lambda: set_mod_running(False))
        threading.Thread(target=task, daemon=True).start()

    def install_loader() -> None:
        manager = manager_or_warning()
        if not manager or mod_running:
            return
        lang = current_language()
        mod_log_message(tr(lang, "loader_installing"))
        set_mod_running(True)

        def task() -> None:
            try:
                result = manager.install_loader(mod_projects)
                mod_log_message(tr(lang, "loader_done", output=result.output))
                mod_log_message(f"Original SHA-256: {result.original_sha256}")
                mod_log_message(f"Modded SHA-256: {result.patched_sha256}")
            except Exception as exc:
                mod_log_message(traceback.format_exc())
                root.after(0, lambda value=str(exc): messagebox.showerror(tr(lang, "error_title"), value))
            finally:
                root.after(0, lambda: set_mod_running(False))
        threading.Thread(target=task, daemon=True).start()

    def launch_modded() -> None:
        manager = manager_or_warning()
        if not manager:
            return
        lang = current_language()
        try:
            manager.launch_modded()
            mod_log_message(tr(lang, "mod_launched"))
        except Exception as exc:
            messagebox.showerror(tr(lang, "error_title"), str(exc))

    mod_buttons["create_mod"].configure(command=create_mod)
    mod_buttons["open_mod_files"].configure(command=open_selected_mod)
    mod_buttons["toggle_mod"].configure(command=toggle_selected_mod)
    mod_buttons["move_up"].configure(command=lambda: move_selected(-1))
    mod_buttons["move_down"].configure(command=lambda: move_selected(1))
    mod_buttons["refresh"].configure(command=refresh_mods)
    mod_action_buttons["build_mods"].configure(command=build_mods)
    mod_action_buttons["install_loader"].configure(command=install_loader)
    mod_action_buttons["launch_modded"].configure(command=launch_modded)
    mod_list.bind("<<ListboxSelect>>", refresh_project_details)

    def close_window() -> None:
        persist_settings()
        root.destroy()

    for variable in (input_var, output_var, game_folder_var, mods_folder_var):
        variable.trace_add("write", schedule_settings_save)
    start_btn.configure(command=start)
    root.protocol("WM_DELETE_WINDOW", close_window)
    refresh_texts()
    switch_mode()
    root.mainloop()
    return 0

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=f"{APP_NAME} {APP_VERSION}")
    p.add_argument("--input", help="Game.cod, installed game folder, or outer ZIP backup")
    p.add_argument("--output", help="Output folder")
    p.add_argument("--categories", default="all", help="all or a list: characters,vehicles,weapons,maps,menu_models,effects,audio,animations,other")
    p.add_argument("--extract-raw", action="store_true", help="Extract original raw files")
    p.add_argument("--convert", action="store_true", help="Convert geometry to OBJ/MTL")
    p.add_argument("--rigged", action="store_true", help="Export compatible character, vehicle, and weapon rigs to glTF 2.0")
    p.add_argument("--include-lod", action="store_true", help="Convert .lod even when a matching .sca exists")
    p.add_argument("--all-lods", action="store_true", help="Export every LOD level")
    p.add_argument("--keep-y-up", action="store_true", help="Do not convert weapons/effect models to Blender Z-up")
    p.add_argument("--keep-v", action="store_true", help="Do not flip the V texture coordinate")
    p.add_argument("--gui", action="store_true", help="Open the graphical interface")
    return p


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    if args.gui or (not args.input and not args.output):
        return launch_gui()
    if not args.input or not args.output:
        parser.error("--input and --output are required in CLI mode")
    if not args.extract_raw and not args.convert and not args.rigged:
        args.convert = True
    return run_cli(args)


if __name__ == "__main__":
    raise SystemExit(main())
