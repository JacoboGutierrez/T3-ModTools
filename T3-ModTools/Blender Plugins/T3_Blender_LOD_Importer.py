bl_info = {
    "name": "T3 LOD Importer",
    "author": "T3-ModTools",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "File > Import > T3 LOD (.lod)",
    "description": "Import T3 model.lod files with LOD ranges, materials, UVs and weight maps",
    "category": "Import-Export",
}

from pathlib import Path
from collections import defaultdict
import json
import re

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy_extras.io_utils import ImportHelper
from mathutils import Matrix, Vector


# Native T3 is Y-up. This is a +90 degree X rotation into Blender Z-up:
# (x, y, z) -> (x, -z, y). The determinant is +1.
T3_TO_BLENDER = Matrix((
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 0.0, -1.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
))


def iter_blocks(text, token):
    """Yield balanced token { ... } blocks, including nested braces."""
    pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(token)}\s*\{{")
    position = 0
    while True:
        match = pattern.search(text, position)
        if not match:
            return
        opening = text.find("{", match.start(), match.end() + 1)
        depth = 0
        in_quote = False
        escaped = False
        closing = -1
        for index in range(opening, len(text)):
            char = text[index]
            if in_quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_quote = False
                continue
            if char == '"':
                in_quote = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    closing = index + 1
                    break
        if closing < 0:
            raise RuntimeError(f"Unclosed {token} block.")
        yield match.start(), closing, text[match.start():closing]
        position = closing


def first_block(text, token):
    return next(iter_blocks(text, token), None)


def quoted_value(text, key, default=""):
    match = re.search(rf"(?<![A-Za-z0-9_]){re.escape(key)}\s*\"([^\"]*)\"", text)
    return match.group(1) if match else default


def token_value(text, key, default=""):
    quoted = quoted_value(text, key, "")
    if quoted:
        return quoted
    match = re.search(rf"(?<![A-Za-z0-9_]){re.escape(key)}\s+([^\s{{}}]+)", text)
    return match.group(1) if match else default


def numeric_value(text, key, default=0.0):
    match = re.search(rf"(?<![A-Za-z0-9_]){re.escape(key)}\s+([-+0-9.eE]+)", text)
    return float(match.group(1)) if match else default


def data_block(text, token):
    block = first_block(text, token)
    if not block:
        return ""
    body = block[2]
    opening = body.find("{")
    closing = body.rfind("}")
    return body[opening + 1:closing]


def float_tuples(text, width, limit=None):
    numbers = [float(item) for item in re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", text)]
    count = len(numbers) // width
    if limit is not None:
        count = min(count, limit)
    return [tuple(numbers[index * width:(index + 1) * width]) for index in range(count)]


def int_tuples(text, width, limit=None):
    numbers = [int(item) for item in re.findall(r"[-+]?\d+", text)]
    count = len(numbers) // width
    if limit is not None:
        count = min(count, limit)
    return [tuple(numbers[index * width:(index + 1) * width]) for index in range(count)]


def parse_lod(text):
    primitive = first_block(text, "cPrimitive")
    if not primitive:
        raise RuntimeError("The file has no cPrimitive block.")
    body = primitive[2]
    texture_library = token_value(body, "TextureLibrary", "")
    root_bone = quoted_value(body, "RootBone", "")

    meshes = []
    for mesh_index, (_, _, mesh_block) in enumerate(iter_blocks(body, "cMesh")):
        first_submesh = re.search(r"(?<![A-Za-z0-9_])cSubMesh\s*\{", mesh_block)
        header = mesh_block[:first_submesh.start()] if first_submesh else mesh_block
        mesh_name = quoted_value(header, "Name", f"LODMesh_{mesh_index}")
        lod_level = int(numeric_value(header, "LODLevel", mesh_index))
        lod_min = numeric_value(header, "LODMin", float(lod_level * 10))
        lod_max = numeric_value(header, "LODMax", float((lod_level + 1) * 10))
        submeshes = []
        for sub_index, (_, _, submesh) in enumerate(iter_blocks(mesh_block, "cSubMesh")):
            vertex_count = int(numeric_value(submesh, "VertexNumber", 0))
            coordinates = float_tuples(data_block(submesh, "Coordinates"), 3, vertex_count or None)
            normals = float_tuples(data_block(submesh, "Normals"), 3, vertex_count or None)
            uvs = float_tuples(data_block(submesh, "Textcoord0"), 2, vertex_count or None)
            index_count = int(numeric_value(submesh, "IndexNumber", 0))
            triangles = int_tuples(data_block(submesh, "Indices"), 3, (index_count // 3) if index_count else None)
            shader_block = first_block(submesh, "Shader")
            shader_text = shader_block[2] if shader_block else submesh
            shader_type = token_value(shader_text, "Type", "DIFFUSE_SPECULAR")
            base_texture = quoted_value(shader_text, "BaseTexture", "")
            weightmaps = {}
            for _, _, weightmap in iter_blocks(submesh, "Weightmap"):
                full_name = quoted_value(weightmap, "BoneName", "")
                if not full_name:
                    continue
                values = [item[0] for item in float_tuples(data_block(weightmap, "Weights"), 1)]
                if len(values) < len(coordinates):
                    values.extend([0.0] * (len(coordinates) - len(values)))
                weightmaps[full_name] = values[:len(coordinates)]
            submeshes.append({
                "name": quoted_value(submesh, "Name", str(sub_index)),
                "shader_type": shader_type,
                "base_texture": base_texture,
                "coordinates": coordinates,
                "normals": normals,
                "uvs": uvs,
                "triangles": triangles,
                "weightmaps": weightmaps,
            })
        meshes.append({
            "name": mesh_name,
            "lod_level": lod_level,
            "lod_min": lod_min,
            "lod_max": lod_max,
            "submeshes": submeshes,
        })

    bones = []
    raw_names = set()
    for _, _, bone_block in iter_blocks(body, "cBone"):
        full_name = quoted_value(bone_block, "Name", "")
        values = [item[0] for item in float_tuples(data_block(bone_block, "Matrix"), 1, 16)]
        if full_name and len(values) == 16:
            raw_names.add(full_name)
            bones.append({
                "full_name": full_name,
                "matrix": Matrix([values[row * 4:(row + 1) * 4] for row in range(4)]),
            })
    for bone in bones:
        parent = bone["full_name"].rsplit("|", 1)[0]
        bone["parent"] = parent if parent in raw_names else None
        bone["leaf"] = bone["full_name"].rsplit("|", 1)[-1] or "bone"
    return {
        "texture_library": texture_library,
        "root_bone": root_bone,
        "meshes": meshes,
        "bones": bones,
    }


def t3_vector_to_blender(value, apply_mirror_x=False):
    vector = Vector((value[0], -value[2], value[1]))
    if apply_mirror_x:
        vector.x = -vector.x
    return vector


def t3_matrix_to_blender(row_matrix):
    # Inverse of the SCA exporter relation:
    # M_t3(row) = transpose(M_blender) * transpose(T3_TO_BLENDER)
    return T3_TO_BLENDER @ row_matrix.transposed()


def unique_leaf_names(bones):
    used = set()
    result = {}
    for bone in sorted(bones, key=lambda item: item["full_name"].count("|")):
        base = bone["leaf"] or "bone"
        name = base
        suffix = 1
        while name in used:
            suffix += 1
            name = f"{base}_{suffix}"
        used.add(name)
        result[bone["full_name"]] = name
    return result


def create_armature(collection, bones, root_name):
    if not bones:
        return None, {}
    names = unique_leaf_names(bones)
    matrices = {bone["full_name"]: t3_matrix_to_blender(bone["matrix"]) for bone in bones}
    children = defaultdict(list)
    for bone in bones:
        if bone["parent"]:
            children[bone["parent"]].append(bone["full_name"])

    arm_data = bpy.data.armatures.new(f"{root_name}_Armature")
    arm_obj = bpy.data.objects.new(f"{root_name}_Armature", arm_data)
    collection.objects.link(arm_obj)
    arm_obj.show_in_front = True
    arm_obj["t3_root_bone"] = root_name

    view_layer = bpy.context.view_layer
    previous_active = view_layer.objects.active
    previous_selection = list(bpy.context.selected_objects)
    for item in previous_selection:
        item.select_set(False)
    arm_obj.select_set(True)
    view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = {}
    try:
        for bone in sorted(bones, key=lambda item: item["full_name"].count("|")):
            full = bone["full_name"]
            matrix = matrices[full]
            head = matrix.translation.copy()
            child_names = children.get(full, [])
            if child_names:
                direction = matrices[child_names[0]].translation - head
            else:
                direction = matrix.to_3x3() @ Vector((0.0, 0.05, 0.0))
            if direction.length < 0.0001:
                direction = Vector((0.0, 0.05, 0.0))
            length = max(0.025, min(0.20, direction.length))
            edit = arm_data.edit_bones.new(names[full])
            edit.head = head
            edit.tail = head + direction.normalized() * length
            if bone["parent"] and bone["parent"] in edit_bones:
                edit.parent = edit_bones[bone["parent"]]
            try:
                roll_axis = matrix.to_3x3() @ Vector((0.0, 0.0, 1.0))
                edit.align_roll(roll_axis)
            except Exception:
                pass
            edit_bones[full] = edit
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        for full, blender_name in names.items():
            data_bone = arm_data.bones.get(blender_name)
            if data_bone:
                data_bone["t3_full_name"] = full
        arm_obj.select_set(False)
        if previous_active and view_layer.objects.get(previous_active.name):
            previous_active.select_set(True)
            view_layer.objects.active = previous_active
    return arm_obj, names


def build_texture_index(texture_root):
    if not texture_root:
        return {}, {}
    root = Path(bpy.path.abspath(texture_root))
    if not root.is_dir():
        return {}, {}
    by_name = {}
    by_stem = defaultdict(list)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        lower = path.name.lower()
        by_name.setdefault(lower, path)
        by_stem[path.stem.lower()].append(path)
    return by_name, by_stem


def find_texture(base_texture, by_name, by_stem):
    if not base_texture:
        return None
    name = Path(base_texture.replace("\\", "/")).name.lower()
    if name in by_name:
        return by_name[name]
    stem = Path(name).stem.lower()
    candidates = by_stem.get(stem, [])
    priority = {".png": 0, ".tga": 1, ".dds": 2, ".jpg": 3, ".jpeg": 4}
    candidates = sorted(candidates, key=lambda path: priority.get(path.suffix.lower(), 99))
    return candidates[0] if candidates else None


def create_material(name, shader_type, base_texture, texture_path=None):
    material = bpy.data.materials.new(name=name)
    material.use_nodes = True
    material["t3_shader_type"] = shader_type
    material["t3_base_texture"] = base_texture
    material.diffuse_color = (0.65, 0.65, 0.65, 1.0)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = next((node for node in nodes if node.type == "BSDF_PRINCIPLED"), None)
    if texture_path and principled:
        try:
            image = bpy.data.images.load(str(texture_path), check_existing=True)
            tex = nodes.new("ShaderNodeTexImage")
            tex.image = image
            tex.label = base_texture
            links.new(tex.outputs.get("Color"), principled.inputs.get("Base Color"))
            alpha = tex.outputs.get("Alpha")
            alpha_input = principled.inputs.get("Alpha")
            if alpha and alpha_input:
                links.new(alpha, alpha_input)
            if "sillum" in base_texture.lower():
                emission = principled.inputs.get("Emission Color") or principled.inputs.get("Emission")
                if emission:
                    links.new(tex.outputs.get("Color"), emission)
        except Exception:
            pass
    return material


def set_custom_normals(mesh, normals):
    if len(normals) != len(mesh.vertices):
        return
    try:
        if hasattr(mesh, "normals_split_custom_set_from_vertices"):
            mesh.normals_split_custom_set_from_vertices(normals)
            if hasattr(mesh, "use_auto_smooth"):
                mesh.use_auto_smooth = True
    except Exception:
        pass


def import_lod(filepath, context, texture_root, apply_mirror_x, flip_uv_v,
               create_rig, show_all_lods):
    source = Path(filepath)
    text = source.read_text(encoding="latin-1", errors="replace")
    parsed = parse_lod(text)
    master = bpy.data.collections.new(f"T3_LOD_{source.stem}")
    context.scene.collection.children.link(master)
    master["t3_lod_source_path"] = str(source)
    master["t3_texture_library"] = parsed["texture_library"]
    master["t3_apply_mirror_x"] = bool(apply_mirror_x)
    master["t3_flip_uv_v"] = bool(flip_uv_v)

    armature = None
    bone_names = {}
    rig_skipped_for_mirror = bool(create_rig and apply_mirror_x)
    if create_rig and parsed["bones"] and not apply_mirror_x:
        armature, bone_names = create_armature(master, parsed["bones"], parsed["root_bone"] or source.stem)
    else:
        bone_names = unique_leaf_names(parsed["bones"])

    by_name, by_stem = build_texture_index(texture_root)
    imported = []
    for mesh_info in sorted(parsed["meshes"], key=lambda item: item["lod_level"]):
        vertices = []
        faces = []
        face_materials = []
        normals = []
        uv_by_vertex = []
        weight_values = defaultdict(dict)
        materials = []
        material_cache = {}

        for sub_index, submesh in enumerate(mesh_info["submeshes"]):
            offset = len(vertices)
            local_vertices = [t3_vector_to_blender(item, apply_mirror_x) for item in submesh["coordinates"]]
            local_normals = [t3_vector_to_blender(item, apply_mirror_x).normalized() for item in submesh["normals"]]
            local_uvs = [
                (float(uv[0]), 1.0 - float(uv[1]) if flip_uv_v else float(uv[1]))
                for uv in submesh["uvs"]
            ]
            vertices.extend(local_vertices)
            normals.extend(local_normals)
            if len(local_uvs) < len(local_vertices):
                local_uvs.extend([(0.0, 0.0)] * (len(local_vertices) - len(local_uvs)))
            uv_by_vertex.extend(local_uvs[:len(local_vertices)])

            for triangle in submesh["triangles"]:
                a, b, c = triangle
                # Mirroring coordinates changes handedness; reverse to keep front faces.
                if apply_mirror_x:
                    b, c = c, b
                if min(a, b, c) < 0 or max(a, b, c) >= len(local_vertices):
                    continue
                faces.append((offset + a, offset + b, offset + c))
                face_materials.append(sub_index)

            for full_name, values in submesh["weightmaps"].items():
                for local_index, weight in enumerate(values[:len(local_vertices)]):
                    if weight > 0.000001:
                        weight_values[full_name][offset + local_index] = float(weight)

            key = (submesh["shader_type"], submesh["base_texture"])
            material = material_cache.get(key)
            if material is None:
                texture_path = find_texture(submesh["base_texture"], by_name, by_stem)
                mat_name = Path(submesh["base_texture"]).stem or f"LOD{mesh_info['lod_level']}_Material{sub_index}"
                material = create_material(mat_name, submesh["shader_type"], submesh["base_texture"], texture_path)
                material_cache[key] = material
            materials.append(material)

        mesh_data = bpy.data.meshes.new(f"LOD{mesh_info['lod_level']}_{source.stem}")
        mesh_data.from_pydata(vertices, [], faces)
        mesh_data.update()
        for material in materials:
            mesh_data.materials.append(material)
        for polygon, material_index in zip(mesh_data.polygons, face_materials):
            polygon.material_index = material_index
        if uv_by_vertex:
            uv_layer = mesh_data.uv_layers.new(name="UVMap")
            for loop in mesh_data.loops:
                uv_layer.data[loop.index].uv = uv_by_vertex[loop.vertex_index]
        set_custom_normals(mesh_data, normals)

        obj = bpy.data.objects.new(f"LOD{mesh_info['lod_level']}_{source.stem}", mesh_data)
        master.objects.link(obj)
        obj["t3_lod_level"] = int(mesh_info["lod_level"])
        obj["t3_lod_min"] = float(mesh_info["lod_min"])
        obj["t3_lod_max"] = float(mesh_info["lod_max"])
        obj["t3_mesh_name"] = mesh_info["name"]
        obj["t3_texture_library"] = parsed["texture_library"]
        obj["t3_lod_template"] = str(source)
        obj["t3_import_mirror_x"] = bool(apply_mirror_x)
        obj["t3_import_flip_uv_v"] = bool(flip_uv_v)
        obj["t3_bone_name_map"] = json.dumps({bone_names.get(full, full): full for full in weight_values}, ensure_ascii=False)

        for full_name, values in weight_values.items():
            group_name = bone_names.get(full_name, full_name.rsplit("|", 1)[-1])
            group = obj.vertex_groups.get(group_name) or obj.vertex_groups.new(name=group_name)
            for vertex_index, weight in values.items():
                group.add([vertex_index], weight, "REPLACE")
        if armature:
            modifier = obj.modifiers.new(name="T3 Armature", type="ARMATURE")
            modifier.object = armature
        if not show_all_lods and mesh_info["lod_level"] != 0:
            obj.hide_set(True)
            obj.hide_render = True
        imported.append(obj)

    for obj in context.selected_objects:
        obj.select_set(False)
    if imported:
        imported[0].hide_set(False)
        imported[0].select_set(True)
        context.view_layer.objects.active = imported[0]
    return (
        len(imported),
        sum(len(mesh["submeshes"]) for mesh in parsed["meshes"]),
        len(parsed["bones"]),
        rig_skipped_for_mirror,
    )


class IMPORT_OT_t3_lod(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.t3_lod"
    bl_label = "Import T3 LOD"
    bl_options = {"UNDO", "PRESET"}

    filename_ext = ".lod"
    filter_glob: StringProperty(default="*.lod", options={"HIDDEN"})
    texture_root: StringProperty(
        name="Texture folder",
        description="Optional folder searched recursively for TGA, DDS or PNG textures",
        subtype="DIR_PATH",
        default="",
    )
    apply_mirror_x: BoolProperty(
        name="Apply T3-ModTools X mirror",
        description="Mirror X while importing. Leave disabled for a native direct LOD editing workflow",
        default=False,
    )
    flip_uv_v: BoolProperty(
        name="Flip UV V for Blender",
        description="Convert T3 texture coordinates to Blender's image orientation; exporter can reverse this automatically",
        default=True,
    )
    create_armature: BoolProperty(
        name="Create armature",
        description="Create a preview armature and connect imported weight maps",
        default=True,
    )
    show_all_lods: BoolProperty(
        name="Show all LODs",
        description="Show every imported LOD overlapping in the viewport. Otherwise only LOD0 is visible initially",
        default=False,
    )

    def execute(self, context):
        try:
            meshes, submeshes, bones, rig_skipped = import_lod(
                self.filepath,
                context,
                self.texture_root,
                self.apply_mirror_x,
                self.flip_uv_v,
                self.create_armature,
                self.show_all_lods,
            )
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Imported {meshes} LOD meshes, {submeshes} submeshes and {bones} bones")
        if rig_skipped:
            self.report({"WARNING"}, "Armature preview was skipped because X mirror import is enabled. Use native orientation for the rigged LOD workflow.")
        return {"FINISHED"}


def menu_func_import(self, context):
    self.layout.operator(IMPORT_OT_t3_lod.bl_idname, text="T3 LOD (.lod)")


def register():
    bpy.utils.register_class(IMPORT_OT_t3_lod)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.utils.unregister_class(IMPORT_OT_t3_lod)


if __name__ == "__main__":
    register()
