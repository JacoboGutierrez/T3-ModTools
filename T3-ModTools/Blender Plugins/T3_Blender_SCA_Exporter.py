bl_info = {
    "name": "T3 SCA Model Exporter",
    "author": "T3-ModTools",
    "version": (0, 5, 0),
    "blender": (3, 6, 0),
    "location": "File > Export > T3 Model (.sca)",
    "description": "Export selected static or rigged Blender meshes to the T3 SCA text format",
    "category": "Import-Export",
}

from pathlib import Path
from collections import defaultdict

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy_extras.io_utils import ExportHelper
from mathutils import Matrix


def fmt(value):
    if abs(value) < 0.0000005:
        value = 0.0
    return f"{value:.6f}"


def indent(lines, level=1):
    prefix = "    " * level
    return [prefix + line if line else "" for line in lines]


def full_bone_names(armature):
    result = {}

    def resolve(bone):
        if bone.name in result:
            return result[bone.name]
        if "|" in bone.name:
            name = bone.name if bone.name.startswith("|") else "|" + bone.name
        elif bone.parent:
            name = resolve(bone.parent) + "|" + bone.name
        else:
            name = "|" + bone.name
        result[bone.name] = name
        return name

    if armature:
        for bone in armature.data.bones:
            resolve(bone)
    return result


def material_texture_name(material):
    if material is None:
        return ""
    custom = material.get("t3_base_texture")
    if custom:
        return str(custom).replace("\\", "/")
    if material.use_nodes and material.node_tree:
        for node in material.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image:
                return Path(bpy.path.abspath(node.image.filepath)).name or node.image.name
    return material.name + ".tga"


def selected_meshes(context):
    return [obj for obj in context.selected_objects if obj.type == "MESH" and obj.visible_get()]


def find_armature(meshes, context):
    active = context.object
    if active and active.type == "ARMATURE":
        return active
    armatures = set()
    for obj in meshes:
        candidate = obj.find_armature()
        if candidate:
            armatures.add(candidate)
    if len(armatures) > 1:
        names = ", ".join(sorted(armature.name for armature in armatures))
        raise RuntimeError(
            "Selected meshes use multiple armatures ("
            + names
            + "). T3 SCA supports one exported skeleton; export each runtime instance "
              "separately or join the bones into one armature."
        )
    return next(iter(armatures)) if armatures else None


def transform_position(matrix, co, undo_mirror):
    value = matrix @ co
    if undo_mirror:
        value.x = -value.x
    return value


def transform_normal(matrix, normal, undo_mirror):
    normal_matrix = matrix.to_3x3().inverted_safe().transposed()
    value = (normal_matrix @ normal).normalized()
    if undo_mirror:
        value.x = -value.x
    return value


def matrix_rows_for_t3(matrix, undo_mirror=False):
    value = matrix.copy()
    if undo_mirror:
        mirror = Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0))
        value = mirror @ value @ mirror
    # T3 stores row-vector matrices; Blender uses column-vector matrices.
    value = value.transposed()
    return [[value[row][column] for column in range(4)] for row in range(4)]


def gather_submeshes(obj, armature, bone_names, undo_mirror):
    mesh = obj.data
    mesh.calc_loop_triangles()
    uv_layer = mesh.uv_layers.active.data if mesh.uv_layers.active else None
    groups_by_index = {group.index: group.name for group in obj.vertex_groups}
    material_triangles = defaultdict(list)
    for triangle in mesh.loop_triangles:
        material_triangles[triangle.material_index].append(triangle)

    submeshes = []
    for material_index, triangles in sorted(material_triangles.items()):
        vertices = []
        normals = []
        uvs = []
        indices = []
        weights = defaultdict(list)
        for triangle in triangles:
            corner_indices = list(triangle.loops)
            if undo_mirror:
                corner_indices[1], corner_indices[2] = corner_indices[2], corner_indices[1]
            tri_indices = []
            for loop_index in corner_indices:
                loop = mesh.loops[loop_index]
                vertex = mesh.vertices[loop.vertex_index]
                vertices.append(transform_position(obj.matrix_world, vertex.co.copy(), undo_mirror))
                normals.append(transform_normal(obj.matrix_world, loop.normal.copy(), undo_mirror))
                uv = uv_layer[loop_index].uv.copy() if uv_layer else (0.0, 0.0)
                uvs.append((float(uv[0]), float(uv[1])))
                exported_index = len(vertices) - 1
                tri_indices.append(exported_index)
                vertex_weights = {groups_by_index.get(item.group, ""): item.weight for item in vertex.groups}
                for bone_name in bone_names:
                    source_name = bone_name.rsplit("|", 1)[-1]
                    weight = vertex_weights.get(source_name, vertex_weights.get(bone_name, 0.0))
                    weights[bone_name].append(float(weight))
            indices.append(tuple(tri_indices))
        material = obj.material_slots[material_index].material if material_index < len(obj.material_slots) else None
        submeshes.append({
            "name": str(material_index),
            "material": material,
            "vertices": vertices,
            "normals": normals,
            "uvs": uvs,
            "indices": indices,
            "weights": {name: values for name, values in weights.items() if any(value > 0.000001 for value in values)},
        })
    return submeshes


def write_sca(filepath, context, texture_library, undo_mirror):
    meshes = selected_meshes(context)
    if not meshes:
        raise RuntimeError("Select at least one mesh object before exporting SCA.")
    armature = find_armature(meshes, context)
    names_by_leaf = full_bone_names(armature)
    full_bones = [names_by_leaf[bone.name] for bone in armature.data.bones] if armature else []

    mesh_data = []
    all_positions = []
    for obj in meshes:
        submeshes = gather_submeshes(obj, armature, full_bones, undo_mirror)
        if not submeshes:
            continue
        all_positions.extend(vertex for submesh in submeshes for vertex in submesh["vertices"])
        mesh_data.append((obj, submeshes))
    if not mesh_data:
        raise RuntimeError("The selected objects contain no triangulated faces.")

    minimum = [min(position[axis] for position in all_positions) for axis in range(3)]
    maximum = [max(position[axis] for position in all_positions) for axis in range(3)]

    lines = [
        "//Mesh definition file",
        "//Exported by T3-ModTools Blender plugin",
        "",
        "cPrimitive",
        "{",
        "    Version\t1.0",
        f'    Name\t"{Path(filepath).name}"',
        f'    TextureLibrary\t"{texture_library.replace(chr(92), "/").strip("/")}/"',
        f"    BoneNumber\t{len(full_bones)}",
        "    cBoundingBox",
        "    {",
        "        cMin",
        "        {",
        "            " + " ".join(fmt(value) for value in minimum),
        "        } // cMin",
        "        cMax",
        "        {",
        "            " + " ".join(fmt(value) for value in maximum),
        "        } // cMax",
        "    } // cBoundingBox",
        f"    MeshNumber\t{len(mesh_data)}",
    ]

    for obj, submeshes in mesh_data:
        mesh_name = f"|{obj.name}|{obj.name}Shape"
        lines += [
            "    cMesh",
            "    {",
            f'        Name\t"{mesh_name}"',
            f"        SubMeshNumber\t{len(submeshes)}",
        ]
        for submesh in submeshes:
            texture_name = material_texture_name(submesh["material"])
            lines += [
                "        cSubMesh",
                "        {",
                f'            Name\t"{submesh["name"]}"',
                "            Type\tTriangleList",
                "            Shader",
                "            {",
                "                Type\tBASE",
                f'                BaseTexture\t"{texture_name}"',
                "            } // Shader",
                f'            VertexNumber\t{len(submesh["vertices"])}',
                "            Coordinates",
                "            {",
            ]
            lines += ["                " + " ".join(fmt(value) for value in vertex) for vertex in submesh["vertices"]]
            lines += ["            } // Coordinates", "            Normals", "            {"]
            lines += ["                " + " ".join(fmt(value) for value in normal) for normal in submesh["normals"]]
            lines += ["            } // Normals", "            Textcoord0", "            {"]
            lines += ["                " + " ".join(fmt(value) for value in uv) for uv in submesh["uvs"]]
            lines += ["            } // Textcoord0", f'            WeightmapNumber\t{len(submesh["weights"])}']
            for bone_name, values in submesh["weights"].items():
                lines += [
                    "            Weightmap",
                    "            {",
                    f'                BoneName\t"{bone_name}"',
                    "                Weights",
                    "                {",
                ]
                for index in range(0, len(values), 8):
                    lines.append("                    " + " ".join(fmt(value) for value in values[index:index + 8]))
                lines += ["                } // Weights", "            } // Weightmap"]
            flat_indices = [index for triangle in submesh["indices"] for index in triangle]
            lines += [f"            IndexNumber\t{len(flat_indices)}", "            Indices", "            {"]
            lines += ["                " + " ".join(str(index) for index in triangle) for triangle in submesh["indices"]]
            lines += ["            } // Indices", "        } // cSubMesh"]
        lines += ["    } // cMesh"]

    lines.append(f"    InstanceNumber\t{len(mesh_data)}")
    for obj, _ in mesh_data:
        mesh_name = f"|{obj.name}|{obj.name}Shape"
        lines += [
            "    cInstance",
            "    {",
            f'        Name\t"|{obj.name}"',
            f'        Mesh\t"{mesh_name}"',
            "        Matrix",
            "        {",
            "            1.000000 0.000000 0.000000 0.000000 0.000000 1.000000 0.000000 0.000000 0.000000 0.000000 1.000000 0.000000 0.000000 0.000000 0.000000 1.000000",
            "        } // Matrix",
            "    } // cInstance",
        ]

    if armature:
        for bone in armature.data.bones:
            full_name = names_by_leaf[bone.name]
            children = [names_by_leaf[child.name] for child in bone.children]
            rows = matrix_rows_for_t3(bone.matrix_local, undo_mirror)
            values = [fmt(value) for row in rows for value in row]
            lines += ["    cBone", "    {", f'        Name\t"{full_name}"', "        Matrix", "        {"]
            lines.append("            " + " ".join(values))
            lines += ["        } // Matrix"]
            if children:
                lines += [f"        ChildNumber\t{len(children)}", "        Childs", "        {"]
                lines += [f'            "{child}"' for child in children]
                lines += ["        } // Childs"]
            lines += ["    } // cBone"]
        roots = [bone for bone in armature.data.bones if bone.parent is None]
        if roots:
            lines.append(f'    RootBone\t"{names_by_leaf[roots[0].name]}"')

    lines += ["} // cPrimitive", "Ital", "{", "} // Ital", ""]
    Path(filepath).write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return len(mesh_data), sum(len(submeshes) for _, submeshes in mesh_data), len(full_bones)


class EXPORT_OT_t3_sca(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.t3_sca"
    bl_label = "Export T3 Model"
    bl_options = {"PRESET"}

    filename_ext = ".sca"
    filter_glob: StringProperty(default="*.sca", options={"HIDDEN"})
    texture_library: StringProperty(
        name="Texture library",
        description="Internal T3 texture folder stored in the SCA",
        default="CA/Textures",
    )
    undo_mirror_x: BoolProperty(
        name="Undo T3-ModTools X mirror",
        description="Convert an extracted mirrored glTF model back toward the game's native X orientation",
        default=True,
    )

    def execute(self, context):
        try:
            meshes, submeshes, bones = write_sca(
                self.filepath, context, self.texture_library, self.undo_mirror_x
            )
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Exported {meshes} meshes, {submeshes} submeshes, {bones} bones")
        return {"FINISHED"}


def menu_func_export(self, context):
    self.layout.operator(EXPORT_OT_t3_sca.bl_idname, text="T3 Model (.sca)")


def register():
    bpy.utils.register_class(EXPORT_OT_t3_sca)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy.utils.unregister_class(EXPORT_OT_t3_sca)


if __name__ == "__main__":
    register()
