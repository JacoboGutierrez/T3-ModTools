bl_info = {
    "name": "T3 Rigged glTF Importer",
    "author": "T3-ModTools",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "File > Import > T3 Rigged glTF (.gltf/.glb)",
    "description": "Import rigged glTF while preserving canonical T3 SCA hierarchy names",
    "category": "Import-Export",
}

import json
import re
import struct
from pathlib import Path

import bpy
from bpy.props import BoolProperty, FloatProperty, StringProperty
from bpy_extras.io_utils import ImportHelper


_PATH_KEYS = ("t3_instance_name", "t3_mesh_name")
_META_KEYS = ("t3_primitive_name", "t3_instance_name", "t3_mesh_name", "t3_mesh_root")


def _brace_end(text, opening_brace):
    depth = 0
    in_quote = False
    escaped = False
    for index in range(opening_brace, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_quote:
            escaped = True
            continue
        if char == '"':
            in_quote = not in_quote
            continue
        if in_quote:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _first_block(text, token):
    match = re.search(rf"(?<![A-Za-z0-9_]){re.escape(token)}\s*\{{", text)
    if not match:
        return ""
    opening = text.find("{", match.start())
    closing = _brace_end(text, opening)
    return text[opening + 1 : closing] if closing >= 0 else ""


def _quoted(text, key):
    match = re.search(rf"\b{re.escape(key)}\b\s*[\t ]*\"([^\"]*)\"", text)
    return match.group(1) if match else ""


def _clean_path(value):
    value = str(value or "").strip()
    if not value:
        return ""
    if any(character in value for character in ('"', "\n", "\r", "{", "}")):
        return ""
    return value if value.startswith("|") else "|" + value.strip("|")


def _complete_metadata(metadata):
    result = {key: str(metadata.get(key, "")).strip() for key in _META_KEYS}
    for key in _PATH_KEYS:
        result[key] = _clean_path(result[key])

    if not result["t3_mesh_root"]:
        parts = [part for part in result["t3_instance_name"].split("|") if part]
        if parts:
            result["t3_mesh_root"] = parts[-1]
        else:
            parts = [part for part in result["t3_mesh_name"].split("|") if part]
            if len(parts) >= 2:
                result["t3_mesh_root"] = parts[-2]
    return {key: value for key, value in result.items() if value}


def _template_metadata(filepath):
    if not filepath:
        return {}
    text = Path(bpy.path.abspath(filepath)).read_text(encoding="utf-8", errors="replace")
    primitive = _first_block(text, "cPrimitive") or text
    first_child = len(primitive)
    for token in ("cMesh", "cInstance", "cBone"):
        match = re.search(rf"(?<![A-Za-z0-9_]){token}\s*\{{", primitive)
        if match:
            first_child = min(first_child, match.start())
    instance = _first_block(primitive, "cInstance")
    mesh = _first_block(primitive, "cMesh")
    mesh_header = mesh.split("cSubMesh", 1)[0]
    return _complete_metadata({
        "t3_primitive_name": _quoted(primitive[:first_child], "Name"),
        "t3_instance_name": _quoted(instance, "Name"),
        "t3_mesh_name": _quoted(instance, "Mesh") or _quoted(mesh_header, "Name"),
    })


def _load_gltf_json(filepath):
    path = Path(filepath)
    data = path.read_bytes()
    if path.suffix.lower() != ".glb":
        return json.loads(data.decode("utf-8-sig"))
    if len(data) < 20 or data[:4] != b"glTF":
        raise ValueError("Invalid GLB header")
    _, version, total_length = struct.unpack_from("<4sII", data, 0)
    if version != 2 or total_length > len(data):
        raise ValueError("Only valid glTF 2.0 GLB files are supported")
    chunk_length, chunk_type = struct.unpack_from("<II", data, 12)
    if chunk_type != 0x4E4F534A:
        raise ValueError("The GLB JSON chunk is missing")
    return json.loads(data[20 : 20 + chunk_length].decode("utf-8").rstrip("\x00 \t\r\n"))


def _mesh_descriptors(document):
    root_extras = document.get("extras", {})
    root_metadata = root_extras.get("t3_hierarchy", {}) if isinstance(root_extras, dict) else {}
    meshes = document.get("meshes", [])
    descriptors = []
    for node in document.get("nodes", []):
        mesh_index = node.get("mesh")
        if not isinstance(mesh_index, int) or not (0 <= mesh_index < len(meshes)):
            continue
        metadata = dict(root_metadata) if isinstance(root_metadata, dict) else {}
        mesh_extras = meshes[mesh_index].get("extras", {})
        node_extras = node.get("extras", {})
        if isinstance(mesh_extras, dict):
            metadata.update(mesh_extras)
        if isinstance(node_extras, dict):
            metadata.update(node_extras)
        descriptors.append({
            "node_name": str(node.get("name", "")),
            "metadata": _complete_metadata(metadata),
        })
    return descriptors


def _base_blender_name(name):
    return re.sub(r"\.\d{3}$", "", str(name))


def _descriptor_for_object(obj, descriptors):
    object_name = _base_blender_name(obj.name)
    for descriptor in descriptors:
        if _base_blender_name(descriptor["node_name"]) == object_name:
            return descriptor
    return None


def _apply_metadata(obj, metadata, rename_objects):
    metadata = _complete_metadata(metadata)
    for key, value in metadata.items():
        obj[key] = value
        obj.data[key] = value
    obj["t3_hierarchy_preserved"] = bool(metadata.get("t3_mesh_name"))

    if rename_objects and metadata.get("t3_mesh_root"):
        obj.name = metadata["t3_mesh_root"]
        mesh_leaf = metadata.get("t3_mesh_name", "").rsplit("|", 1)[-1]
        obj.data.name = mesh_leaf or metadata["t3_mesh_root"] + "Shape"
    return bool(metadata.get("t3_instance_name") and metadata.get("t3_mesh_name"))


class IMPORT_OT_t3_rigged_gltf(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.t3_rigged_gltf"
    bl_label = "Import T3 Rigged glTF"
    bl_options = {"PRESET", "UNDO"}

    filename_ext = ".gltf"
    filter_glob: StringProperty(default="*.gltf;*.glb", options={"HIDDEN"})
    hierarchy_template: StringProperty(
        name="Legacy SCA/LOD template",
        description="Optional original SCA/LOD used to recover hierarchy from older glTF files without T3 metadata",
        subtype="FILE_PATH",
        default="",
    )
    rename_objects: BoolProperty(
        name="Use canonical Blender names",
        description="Rename imported mesh objects to their canonical T3 root while retaining exact paths as metadata",
        default=True,
    )
    bone_shape_scale: FloatProperty(
        name="Bone Shape Scale",
        description="Visual scale used by Blender for the custom bone shapes created by the native glTF importer",
        default=0.10,
        min=0.0,
        soft_max=10.0,
        precision=3,
    )

    def execute(self, context):
        try:
            document = _load_gltf_json(self.filepath)
            descriptors = _mesh_descriptors(document)
            template = _template_metadata(self.hierarchy_template)
        except Exception as exc:
            self.report({"ERROR"}, f"Could not read T3 hierarchy metadata: {exc}")
            return {"CANCELLED"}

        # bpy may recreate both Python wrappers and RNA pointers after an
        # operator. Existing object names remain stable; Blender suffixes any
        # imported collision, so names are the reliable boundary here.
        before_names = {obj.name for obj in bpy.data.objects}
        gltf_options = {"filepath": self.filepath}
        native_properties = bpy.ops.import_scene.gltf.get_rna_type().properties
        if "bone_shape_scale_factor" in native_properties:
            gltf_options["bone_shape_scale_factor"] = self.bone_shape_scale
        result = bpy.ops.import_scene.gltf(**gltf_options)
        if "FINISHED" not in result:
            return result
        imported_meshes = [
            obj for obj in bpy.data.objects
            if obj.name not in before_names and obj.type == "MESH"
        ]

        preserved = 0
        missing = 0
        assignments = [
            (obj, descriptor)
            for obj in imported_meshes
            for descriptor in [_descriptor_for_object(obj, descriptors)]
            if descriptor is not None
        ]
        if not assignments and len(imported_meshes) == 1 and len(descriptors) == 1:
            assignments = [(imported_meshes[0], descriptors[0])]
        if not assignments:
            self.report(
                {"WARNING"},
                "The glTF geometry was imported, but no Blender mesh could be matched to its T3 node metadata.",
            )
            return {"FINISHED"}

        for obj, descriptor in assignments:
            metadata = dict(template)
            metadata.update(descriptor.get("metadata", {}))
            if not metadata:
                # A visible fallback is useful, but it is deliberately marked as
                # non-canonical instead of pretending the original path is known.
                root = _base_blender_name(obj.name)
                metadata = _complete_metadata({
                    "t3_instance_name": "|" + root,
                    "t3_mesh_name": f"|{root}|{root}Shape",
                    "t3_mesh_root": root,
                })
                missing += 1
            preserved += int(_apply_metadata(obj, metadata, self.rename_objects))
            obj["t3_gltf_source"] = self.filepath

        if missing:
            self.report(
                {"WARNING"},
                f"Imported {len(assignments)} T3 mesh(es), but {missing} used inferred names. "
                "Choose the original SCA/LOD as Legacy template for exact hierarchy.",
            )
        else:
            self.report({"INFO"}, f"Imported {preserved} mesh(es) with canonical T3 hierarchy")
        return {"FINISHED"}


def menu_func_import(self, context):
    self.layout.operator(
        IMPORT_OT_t3_rigged_gltf.bl_idname,
        text="T3 Rigged glTF (.gltf/.glb)",
    )


def register():
    bpy.utils.register_class(IMPORT_OT_t3_rigged_gltf)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.utils.unregister_class(IMPORT_OT_t3_rigged_gltf)


if __name__ == "__main__":
    register()
