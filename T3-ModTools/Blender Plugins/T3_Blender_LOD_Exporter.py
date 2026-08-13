bl_info = {
    "name": "T3 LOD Exporter",
    "author": "T3-ModTools",
    "version": (0, 2, 0),
    "blender": (3, 6, 0),
    "location": "File > Export > T3 LOD (.lod)",
    "description": "Export edited T3 LOD meshes into an original model.lod template",
    "category": "Import-Export",
}

from pathlib import Path
from collections import defaultdict
import json
import re

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy_extras.io_utils import ExportHelper
from mathutils import Matrix, Vector


T3_TO_BLENDER = Matrix((
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 0.0, -1.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
))


def fmt(value):
    if abs(value) < 0.0000005:
        value = 0.0
    return f"{value:.6f}"


def iter_blocks(text, token):
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


def quoted_value(text, key, default=""):
    match = re.search(rf"(?<![A-Za-z0-9_]){re.escape(key)}\s*\"([^\"]*)\"", text)
    return match.group(1) if match else default


def numeric_value(text, key, default=0.0):
    match = re.search(rf"(?<![A-Za-z0-9_]){re.escape(key)}\s+([-+0-9.eE]+)", text)
    return float(match.group(1)) if match else default


def custom_value(owner, key, default=None):
    try:
        return owner.get(key, default)
    except Exception:
        return default


def material_texture_name(material):
    if material is None:
        return ""
    custom = custom_value(material, "t3_base_texture", "")
    if custom:
        return str(custom).replace("\\", "/")
    if material.use_nodes and material.node_tree:
        for node in material.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image:
                return Path(bpy.path.abspath(node.image.filepath)).name or node.image.name
    return material.name + ".tga"


def material_shader_type(material):
    if material is None:
        return "DIFFUSE_SPECULAR"
    return str(custom_value(material, "t3_shader_type", "DIFFUSE_SPECULAR"))


def to_t3_axis(value):
    return Vector((value.x, value.z, -value.y))


def transform_position(matrix, coordinate, undo_mirror_x, convert_axes):
    value = matrix @ coordinate
    if undo_mirror_x:
        value.x = -value.x
    return to_t3_axis(value) if convert_axes else value


def transform_normal(matrix, normal, undo_mirror_x, convert_axes):
    normal_matrix = matrix.to_3x3().inverted_safe().transposed()
    value = (normal_matrix @ normal).normalized()
    if undo_mirror_x:
        value.x = -value.x
    if convert_axes:
        value = to_t3_axis(value).normalized()
    return value


def effective_transform_determinant(obj, undo_mirror_x):
    determinant = obj.matrix_world.to_3x3().determinant()
    if undo_mirror_x:
        determinant *= -1.0
    if abs(determinant) < 1.0e-10:
        raise RuntimeError(f'Object "{obj.name}" has a singular transform.')
    return determinant


def parse_bone_names(template):
    names = []
    for _, _, block in iter_blocks(template, "cBone"):
        name = quoted_value(block, "Name", "")
        if name:
            names.append(name)
    root_match = re.search(r'\bRootBone\s*"([^"]+)"', template)
    root = root_match.group(1) if root_match else (names[0] if names else "")
    return names, root


def bone_matrix_values(block):
    match = re.search(r"\bMatrix\s*\{([^}]*)\}", block, re.DOTALL)
    if not match:
        return []
    return [float(value) for value in re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", match.group(1))]


def render_bone(name, matrix, children=()):
    lines = [
        "\tcBone",
        "\t{",
        f'\t\tName\t"{name}"',
        "\t\tMatrix",
        "\t\t{",
        "\t\t" + " ".join(fmt(value) for value in matrix) + " ",
        "\t\t} // Matrix",
    ]
    if children:
        lines += [
            f"\t\tChildNumber\t{len(children)}",
            "\t\tChilds",
            "\t\t{",
            *(f'\t\t"{child}"' for child in children),
            "\t\t} // Childs",
        ]
    lines += ["\t} // cBone"]
    return "\n".join(lines)


def scene_bone_t3_matrix(objects, bone_name):
    for obj in objects:
        armature = obj.find_armature()
        if not armature:
            continue
        bone = armature.data.bones.get(bone_name)
        if not bone:
            continue
        blender_matrix = armature.matrix_world @ bone.matrix_local
        row_matrix = (T3_TO_BLENDER.inverted() @ blender_matrix).transposed()
        return [float(row_matrix[row][column]) for row in range(4) for column in range(4)]
    return None


def ensure_dual_weapon_branch(template, objects):
    """Add the b3/b4 deform branch when Blender contains the authored second rifle."""
    names, root = parse_bone_names(template)
    if any(name.rsplit("|", 1)[-1] == "b3" for name in names):
        return template

    scene_bones = set()
    scene_groups = set()
    for obj in objects:
        scene_groups.update(group.name for group in obj.vertex_groups)
        armature = obj.find_armature()
        if armature:
            scene_bones.update(bone.name for bone in armature.data.bones)
    if "b3" not in scene_bones and "b3" not in scene_groups:
        return template

    b1 = root
    b2 = b1 + "|b2"
    if b1 not in names or b2 not in names:
        raise RuntimeError(
            "A b3 deform group was found, but the selected template is not the WM20 b1/b2 rig."
        )
    blocks = list(iter_blocks(template, "cBone"))
    matrices = {quoted_value(block, "Name", ""): bone_matrix_values(block) for _, _, block in blocks}
    if len(matrices.get(b1, [])) != 16 or len(matrices.get(b2, [])) != 16:
        raise RuntimeError("The WM20 template has invalid b1/b2 bind matrices.")

    b3 = b1 + "|b3"
    b4 = b3 + "|b4"
    b3_matrix = scene_bone_t3_matrix(objects, "b3") or list(matrices[b1])
    b4_matrix = scene_bone_t3_matrix(objects, "b4")
    if b4_matrix is None:
        b4_matrix = list(matrices[b2])
        for axis in range(3):
            b4_matrix[12 + axis] += b3_matrix[12 + axis] - matrices[b1][12 + axis]
    branch = "\n".join((
        render_bone(b1, matrices[b1], (b2, b3)),
        render_bone(b2, matrices[b2]),
        render_bone(b3, b3_matrix, (b4,)),
        render_bone(b4, b4_matrix),
    ))
    template = template[:blocks[0][0]] + branch + template[blocks[-1][1]:]
    template, count = re.subn(r"(\bBoneNumber\s+)\d+", r"\g<1>4", template, count=1)
    if count != 1:
        raise RuntimeError("Could not update BoneNumber for the b3/b4 branch.")
    return template


def group_mapping(obj, full_bones):
    mapping = {}
    raw = custom_value(obj, "t3_bone_name_map", "")
    if raw:
        try:
            parsed = json.loads(str(raw))
            if isinstance(parsed, dict):
                mapping.update({str(key): str(value) for key, value in parsed.items()})
        except Exception:
            pass
    by_leaf = defaultdict(list)
    for full in full_bones:
        by_leaf[full.rsplit("|", 1)[-1]].append(full)
    for group in obj.vertex_groups:
        if group.name in mapping:
            continue
        if group.name in full_bones:
            mapping[group.name] = group.name
        elif len(by_leaf.get(group.name, [])) == 1:
            mapping[group.name] = by_leaf[group.name][0]
    return mapping


def object_lod_level(obj):
    value = custom_value(obj, "t3_lod_level", None)
    if value is not None:
        try:
            return int(value)
        except Exception:
            pass
    match = re.search(r"(?:^|[_ .-])LOD\s*([0-9]+)", obj.name, re.I)
    if match:
        return int(match.group(1))
    return None


def candidate_objects(context, export_all_imported_lods):
    selected = [obj for obj in context.selected_objects if obj.type == "MESH"]
    if not export_all_imported_lods:
        return selected
    active = context.object if context.object and context.object.type == "MESH" else (selected[0] if selected else None)
    template = str(custom_value(active, "t3_lod_template", "")) if active else ""
    if template:
        matching = [
            obj for obj in context.scene.objects
            if obj.type == "MESH" and str(custom_value(obj, "t3_lod_template", "")) == template
        ]
        if matching:
            return matching
    return selected


def gather_object_submeshes(obj, depsgraph, apply_modifiers, full_bones, root_bone,
                              use_import_settings, undo_mirror_x, convert_axes, flip_uv_v):
    evaluated = None
    mesh = None
    source_obj = obj
    try:
        if apply_modifiers:
            evaluated = obj.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh()
            work_obj = evaluated
        else:
            mesh = obj.data
            work_obj = obj
        if not mesh:
            return []
        mesh.calc_loop_triangles()

        local_undo = undo_mirror_x
        local_flip = flip_uv_v
        if use_import_settings:
            imported_mirror = custom_value(obj, "t3_import_mirror_x", None)
            imported_flip = custom_value(obj, "t3_import_flip_uv_v", None)
            if imported_mirror is not None:
                local_undo = bool(imported_mirror)
            if imported_flip is not None:
                local_flip = bool(imported_flip)

        reverse_winding = effective_transform_determinant(work_obj, local_undo) < 0.0
        uv_layer = mesh.uv_layers.active.data if mesh.uv_layers.active else None
        group_names = {group.index: group.name for group in source_obj.vertex_groups}
        full_by_group = group_mapping(source_obj, full_bones)
        armature = source_obj.find_armature()
        deform_groups = {bone.name for bone in armature.data.bones} if armature else set()
        unmapped_deform_groups = set()
        triangles_by_material = defaultdict(list)
        for triangle in mesh.loop_triangles:
            triangles_by_material[triangle.material_index].append(triangle)

        results = []
        for material_index, triangles in sorted(triangles_by_material.items()):
            vertices = []
            normals = []
            uvs = []
            indices = []
            weights = {}
            for triangle in triangles:
                loop_indices = list(triangle.loops)
                if reverse_winding:
                    loop_indices[1], loop_indices[2] = loop_indices[2], loop_indices[1]
                tri = []
                for loop_index in loop_indices:
                    loop = mesh.loops[loop_index]
                    vertex = mesh.vertices[loop.vertex_index]
                    exported_index = len(vertices)
                    vertices.append(transform_position(work_obj.matrix_world, vertex.co.copy(), local_undo, convert_axes))
                    normals.append(transform_normal(work_obj.matrix_world, loop.normal.copy(), local_undo, convert_axes))
                    if uv_layer:
                        uv = uv_layer[loop_index].uv
                        u = float(uv[0])
                        v = 1.0 - float(uv[1]) if local_flip else float(uv[1])
                    else:
                        u, v = 0.0, 0.0
                    uvs.append((u, v))
                    for values in weights.values():
                        values.append(0.0)
                    assigned = False
                    for membership in vertex.groups:
                        group_name = group_names.get(membership.group, "")
                        full_name = full_by_group.get(group_name)
                        if (
                            membership.weight > 0.000001
                            and group_name in deform_groups
                            and not full_name
                        ):
                            unmapped_deform_groups.add(group_name)
                        if not full_name or membership.weight <= 0.000001:
                            continue
                        if full_name not in weights:
                            weights[full_name] = [0.0] * (exported_index + 1)
                        weights[full_name][exported_index] = float(membership.weight)
                        assigned = True
                    if not assigned and root_bone:
                        if root_bone not in weights:
                            weights[root_bone] = [0.0] * (exported_index + 1)
                        weights[root_bone][exported_index] = 1.0
                    tri.append(exported_index)
                indices.append(tuple(tri))
            if unmapped_deform_groups:
                names = ", ".join(sorted(unmapped_deform_groups))
                raise RuntimeError(
                    f'Object "{source_obj.name}" uses deform bones absent from the '
                    f'original LOD template: {names}. They cannot attach to character '
                    "bones and would otherwise be silently reassigned to the template root."
                )
            material = source_obj.material_slots[material_index].material if material_index < len(source_obj.material_slots) else None
            results.append({
                "material": material,
                "vertices": vertices,
                "normals": normals,
                "uvs": uvs,
                "indices": indices,
                "weights": {name: values for name, values in weights.items() if any(value > 0.000001 for value in values)},
            })
        return results
    finally:
        if evaluated is not None:
            evaluated.to_mesh_clear()


def build_mesh_block(level, objects, template_block, depsgraph, apply_modifiers,
                     full_bones, root_bone, use_import_settings, undo_mirror_x,
                     convert_axes, flip_uv_v):
    mesh_name = quoted_value(template_block, "Name", f"|LOD{level}|LOD{level}Shape")
    template_min = numeric_value(template_block, "LODMin", float(level * 10))
    template_max = numeric_value(template_block, "LODMax", float((level + 1) * 10))
    lod_min = min(float(custom_value(obj, "t3_lod_min", template_min)) for obj in objects)
    lod_max = max(float(custom_value(obj, "t3_lod_max", template_max)) for obj in objects)

    submeshes = []
    for obj in objects:
        submeshes.extend(gather_object_submeshes(
            obj,
            depsgraph,
            apply_modifiers,
            full_bones,
            root_bone,
            use_import_settings,
            undo_mirror_x,
            convert_axes,
            flip_uv_v,
        ))
    if not submeshes:
        raise RuntimeError(f"LOD{level} contains no triangulated faces.")

    lines = [
        "\tcMesh",
        "\t{",
        f'\t\tName\t"{mesh_name}"',
        f"\t\tLODLevel\t{level}",
        f"\t\tLODMin\t{fmt(lod_min)}",
        f"\t\tLODMax\t{fmt(lod_max)}",
        f"\t\tSubMeshNumber\t{len(submeshes)}",
    ]
    for sub_index, submesh in enumerate(submeshes):
        texture = material_texture_name(submesh["material"])
        shader = material_shader_type(submesh["material"])
        lines += [
            "\t\tcSubMesh",
            "\t\t{",
            f'\t\t\tName\t"{sub_index}"',
            "\t\t\tType\tTriangleList",
            "\t\t\tShader",
            "\t\t\t{",
            f"\t\t\t\tType\t{shader}",
            f'\t\t\t\tBaseTexture\t"{texture}"',
            "\t\t\t} //Shader",
            f"\t\t\tVertexNumber\t{len(submesh['vertices'])}",
            "\t\t\tCoordinates",
            "\t\t\t{",
        ]
        lines += ["\t\t\t" + " ".join(fmt(value) for value in vertex) for vertex in submesh["vertices"]]
        lines += ["\t\t\t} // Coordinates", "\t\t\tNormals", "\t\t\t{"]
        lines += ["\t\t\t" + " ".join(fmt(value) for value in normal) for normal in submesh["normals"]]
        lines += ["\t\t\t} // Normals", "\t\t\tTextcoord0", "\t\t\t{"]
        lines += ["\t\t\t" + " ".join(fmt(value) for value in uv) for uv in submesh["uvs"]]
        lines += ["\t\t\t} // Textcoord0", f"\t\t\tWeightmapNumber\t{len(submesh['weights'])}"]
        for bone_name, values in submesh["weights"].items():
            lines += [
                "\t\t\tWeightmap",
                "\t\t\t{",
                f'\t\t\t\tBoneName\t"{bone_name}"',
                "\t\t\t\tWeights",
                "\t\t\t\t{",
            ]
            for index in range(0, len(values), 8):
                lines.append("\t\t\t\t" + " ".join(fmt(value) for value in values[index:index + 8]))
            lines += ["\t\t\t\t} // Weights", "\t\t\t} // Weightmap"]
        flat_count = len(submesh["indices"]) * 3
        lines += [f"\t\t\tIndexNumber\t{flat_count}", "\t\t\tIndices", "\t\t\t{"]
        lines += ["\t\t\t" + " ".join(str(value) for value in triangle) for triangle in submesh["indices"]]
        lines += ["\t\t\t} // Indices", "\t\t} // cSubMesh"]
    lines += ["\t} // cMesh"]
    return "\n".join(lines)


def export_lod(filepath, context, template_path, export_all_imported_lods,
               preserve_unexported_lods, apply_modifiers, use_import_settings,
               undo_mirror_x, convert_axes, flip_uv_v):
    template_file = Path(bpy.path.abspath(template_path))
    if not template_file.is_file():
        raise RuntimeError("Select a valid original model.lod template.")
    template_bytes = template_file.read_bytes()
    template = template_bytes.decode("latin-1", errors="replace")
    objects = candidate_objects(context, export_all_imported_lods)
    template = ensure_dual_weapon_branch(template, objects)
    mesh_blocks = list(iter_blocks(template, "cMesh"))
    if not mesh_blocks:
        raise RuntimeError("The template contains no cMesh blocks.")
    by_level = {}
    for start, end, block in mesh_blocks:
        level = int(numeric_value(block, "LODLevel", len(by_level)))
        by_level[level] = (start, end, block)

    levels = defaultdict(list)
    for obj in objects:
        level = object_lod_level(obj)
        if level is not None:
            levels[level].append(obj)
    if not levels:
        raise RuntimeError("Select imported LOD mesh objects or objects with a t3_lod_level custom property.")

    full_bones, root_bone = parse_bone_names(template)
    depsgraph = context.evaluated_depsgraph_get()
    replacements = []
    for level, level_objects in sorted(levels.items()):
        if level not in by_level:
            raise RuntimeError(f"The template has no LODLevel {level}.")
        start, end, old_block = by_level[level]
        new_block = build_mesh_block(
            level,
            level_objects,
            old_block,
            depsgraph,
            apply_modifiers,
            full_bones,
            root_bone,
            use_import_settings,
            undo_mirror_x,
            convert_axes,
            flip_uv_v,
        )
        replacements.append((start, end, new_block))

    if not preserve_unexported_lods and set(levels) != set(by_level):
        missing = sorted(set(by_level) - set(levels))
        raise RuntimeError(f"Missing LOD objects for levels: {missing}")

    result = template
    for start, end, new_block in sorted(replacements, reverse=True):
        result = result[:start] + new_block + result[end:]

    # Validate that every original LOD level still exists exactly once.
    output_levels = [int(numeric_value(block, "LODLevel", index)) for index, (_, _, block) in enumerate(iter_blocks(result, "cMesh"))]
    expected_levels = sorted(by_level)
    if sorted(output_levels) != expected_levels:
        raise RuntimeError(f"LOD validation failed. Expected {expected_levels}, got {sorted(output_levels)}.")

    newline = "\r\n" if b"\r\n" in template_bytes else "\n"
    normalized = result.replace("\r\n", "\n").replace("\r", "\n")
    if newline == "\r\n":
        normalized = normalized.replace("\n", "\r\n")
    Path(filepath).write_bytes(normalized.encode("latin-1", errors="replace"))
    return sorted(levels), len(replacements), len(full_bones)


class EXPORT_OT_t3_lod(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.t3_lod"
    bl_label = "Export T3 LOD"
    bl_options = {"PRESET"}

    filename_ext = ".lod"
    filter_glob: StringProperty(default="*.lod", options={"HIDDEN"})
    template_path: StringProperty(
        name="Original model.lod template",
        description="The original game LOD supplies unedited LODs, bones, instances and collision targets",
        subtype="FILE_PATH",
        default="",
    )
    export_all_imported_lods: BoolProperty(
        name="Export all LODs from the imported set",
        description="Find all scene objects imported from the same template as the active LOD object",
        default=True,
    )
    preserve_unexported_lods: BoolProperty(
        name="Preserve missing LODs from template",
        description="Only replace levels present in Blender and keep all other levels exactly as in the original file",
        default=True,
    )
    apply_modifiers: BoolProperty(
        name="Apply modifiers",
        description="Export evaluated geometry, including Decimate modifiers used to create lower LODs",
        default=True,
    )
    use_import_settings: BoolProperty(
        name="Use settings stored by T3 LOD Importer",
        description="Automatically undo the mirror and UV conversion selected during import",
        default=True,
    )
    undo_mirror_x: BoolProperty(
        name="Undo X mirror",
        description="Use for geometry originating from a mirrored T3-ModTools glTF; normally disabled for direct LOD imports",
        default=False,
    )
    convert_to_t3_y_up: BoolProperty(
        name="Convert Blender Z-up to T3 Y-up",
        default=True,
    )
    flip_uv_v: BoolProperty(
        name="Flip UV V back to T3",
        description="Use with the importer's default Flip UV V option",
        default=True,
    )

    def invoke(self, context, event):
        active = context.object
        if active and active.type == "MESH":
            stored = str(custom_value(active, "t3_lod_template", ""))
            if stored and not self.template_path:
                self.template_path = stored
        return super().invoke(context, event)

    def execute(self, context):
        try:
            levels, replaced, bones = export_lod(
                self.filepath,
                context,
                self.template_path,
                self.export_all_imported_lods,
                self.preserve_unexported_lods,
                self.apply_modifiers,
                self.use_import_settings,
                self.undo_mirror_x,
                self.convert_to_t3_y_up,
                self.flip_uv_v,
            )
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Exported LOD levels {levels}; replaced {replaced} mesh blocks; wrote {bones} bones")
        return {"FINISHED"}


def menu_func_export(self, context):
    self.layout.operator(EXPORT_OT_t3_lod.bl_idname, text="T3 LOD (.lod)")


def register():
    bpy.utils.register_class(EXPORT_OT_t3_lod)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy.utils.unregister_class(EXPORT_OT_t3_lod)


if __name__ == "__main__":
    register()
