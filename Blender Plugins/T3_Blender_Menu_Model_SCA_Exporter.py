bl_info = {
    "name": "T3 Menu Model SCA Exporter",
    "author": "T3-ModTools",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "File > Export > T3 Menu Model (.sca)",
    "description": "Export T3 MenuDatas/3DModells SCA models with native menu-model rules",
    "category": "Import-Export",
}

from pathlib import Path
from collections import defaultdict
import re

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy_extras.io_utils import ExportHelper
from mathutils import Vector


MENU_TEXTURE_LIBRARY = "MenuDatas/3DModells/"


def fmt(value):
    if abs(value) < 0.0000005:
        value = 0.0
    return f"{value:.6f}"


def custom_string(owner, key):
    if owner is None:
        return ""
    try:
        value = owner.get(key)
    except Exception:
        return ""
    return str(value) if value not in (None, "") else ""


def selected_meshes(context):
    return [
        obj
        for obj in context.selected_objects
        if obj.type == "MESH" and obj.visible_get()
    ]


def material_texture_name(material):
    if material is None:
        return ""

    custom = custom_string(material, "t3_base_texture")
    if custom:
        return Path(custom.replace("\\", "/")).name

    if material.use_nodes and material.node_tree:
        for node in material.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image:
                filepath = bpy.path.abspath(node.image.filepath)
                name = Path(filepath).name if filepath else ""
                return name or node.image.name

    name = material.name
    # Asset Tool OBJ/MTL material names may include suffixes such as _0_0.
    # Prefer the material name only as a final fallback.
    if "." not in name:
        name += ".tga"
    return Path(name).name


def effective_transform_determinant(obj):
    """Determinant after applying the mandatory Menu Model X un-mirror."""
    determinant = obj.matrix_world.to_3x3().determinant()
    determinant *= -1.0

    if abs(determinant) < 1.0e-10:
        raise RuntimeError(
            f'Object "{obj.name}" has a singular transform. '
            "Apply or repair its scale before exporting."
        )
    return determinant


def transform_position(obj, coordinate):
    # Menu Models extracted by T3-ModTools retain native T3 Y/Z axes and
    # receive only the global X mirror. Undo that mirror here.
    value = obj.matrix_world @ coordinate
    value.x = -value.x
    return value


def transform_normal(obj, normal):
    normal_matrix = obj.matrix_world.to_3x3().inverted_safe().transposed()
    value = (normal_matrix @ normal).normalized()
    value.x = -value.x
    return value.normalized()


def quoted_value(text, key, default=""):
    match = re.search(
        rf'(?<![A-Za-z0-9_]){re.escape(key)}\s*"([^"]*)"',
        text,
    )
    return match.group(1) if match else default


def balanced_block(text, token):
    match = re.search(
        rf"(?<![A-Za-z0-9_]){re.escape(token)}\s*\{{",
        text,
    )
    if not match:
        return ""

    opening = text.find("{", match.start(), match.end() + 1)
    depth = 0
    in_quote = False
    escaped = False

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
                return text[match.start():index + 1]

    return ""


def names_from_template(template_path):
    if not template_path:
        return "", ""

    path = Path(bpy.path.abspath(template_path))
    if not path.is_file():
        raise RuntimeError("The selected original Menu Model SCA template does not exist.")

    text = path.read_text(encoding="latin-1", errors="replace")
    mesh_block = balanced_block(text, "cMesh")
    instance_block = balanced_block(text, "cInstance")

    mesh_name = quoted_value(mesh_block, "Name", "") if mesh_block else ""
    instance_name = (
        quoted_value(instance_block, "Name", "")
        if instance_block
        else ""
    )
    return mesh_name, instance_name


def fallback_names(objects):
    # Every original MenuDatas/3DModells SCA inspected contains one cMesh and
    # one cInstance. If a template is unavailable, create a simple compatible
    # identity from the active/first selected object.
    source_name = objects[0].name.strip().strip("|") or "MenuModel"
    source_name = re.sub(r"Shape$", "", source_name, flags=re.I)
    instance_name = "|" + source_name
    mesh_name = instance_name + "|" + source_name + "Shape"
    return mesh_name, instance_name


def gather_submeshes(objects, apply_modifiers, context):
    depsgraph = context.evaluated_depsgraph_get()
    output = []

    for obj in objects:
        evaluated = None
        mesh = None
        try:
            if apply_modifiers:
                evaluated = obj.evaluated_get(depsgraph)
                mesh = evaluated.to_mesh()
                work_obj = evaluated
            else:
                mesh = obj.data
                work_obj = obj

            if not mesh:
                continue

            mesh.calc_loop_triangles()
            uv_layer = (
                mesh.uv_layers.active.data
                if mesh.uv_layers.active
                else None
            )

            triangles_by_material = defaultdict(list)
            for triangle in mesh.loop_triangles:
                triangles_by_material[triangle.material_index].append(triangle)

            for material_index, triangles in sorted(triangles_by_material.items()):
                vertices = []
                normals = []
                uvs = []
                indices = []

                reverse_winding = effective_transform_determinant(work_obj) < 0.0

                for triangle in triangles:
                    loop_indices = list(triangle.loops)
                    if reverse_winding:
                        loop_indices[1], loop_indices[2] = (
                            loop_indices[2],
                            loop_indices[1],
                        )

                    triangle_indices = []
                    for loop_index in loop_indices:
                        loop = mesh.loops[loop_index]
                        vertex = mesh.vertices[loop.vertex_index]

                        vertices.append(
                            transform_position(work_obj, vertex.co.copy())
                        )
                        normals.append(
                            transform_normal(work_obj, loop.normal.copy())
                        )

                        if uv_layer:
                            uv = uv_layer[loop_index].uv
                            # IMPORTANT: Menu Model export preserves Blender V
                            # exactly. There is intentionally NO 1.0 - V here.
                            uvs.append((float(uv[0]), float(uv[1])))
                        else:
                            uvs.append((0.0, 0.0))

                        triangle_indices.append(len(vertices) - 1)

                    indices.append(tuple(triangle_indices))

                if not vertices or not indices:
                    continue

                material = (
                    obj.material_slots[material_index].material
                    if material_index < len(obj.material_slots)
                    else None
                )

                output.append({
                    "material": material,
                    "vertices": vertices,
                    "normals": normals,
                    "uvs": uvs,
                    "indices": indices,
                })

        finally:
            if evaluated is not None:
                evaluated.to_mesh_clear()

    return output


def write_menu_sca(
    filepath,
    context,
    template_path,
    apply_modifiers,
):
    objects = selected_meshes(context)
    if not objects:
        raise RuntimeError(
            "Select at least one visible mesh object before exporting a Menu Model."
        )

    submeshes = gather_submeshes(objects, apply_modifiers, context)
    if not submeshes:
        raise RuntimeError("The selected objects contain no triangulated faces.")

    template_mesh_name, template_instance_name = names_from_template(template_path)
    if template_mesh_name and template_instance_name:
        mesh_name = template_mesh_name
        instance_name = template_instance_name
    else:
        mesh_name, instance_name = fallback_names(objects)

    all_positions = [
        vertex
        for submesh in submeshes
        for vertex in submesh["vertices"]
    ]
    minimum = [
        min(position[axis] for position in all_positions)
        for axis in range(3)
    ]
    maximum = [
        max(position[axis] for position in all_positions)
        for axis in range(3)
    ]

    lines = [
        "//Mesh definition file",
        "//Exported by T3 Menu Model SCA Exporter v0.1.0",
        "",
        "cPrimitive",
        "{",
        "    Version\t1.0",
        f'    Name\t"{Path(filepath).name}"',
        f'    TextureLibrary\t"{MENU_TEXTURE_LIBRARY}"',
        "    BoneNumber\t0",
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
        "    MeshNumber\t1",
        "    cMesh",
        "    {",
        f'        Name\t"{mesh_name}"',
        f"        SubMeshNumber\t{len(submeshes)}",
    ]

    for sub_index, submesh in enumerate(submeshes):
        texture_name = material_texture_name(submesh["material"])

        lines += [
            "        cSubMesh",
            "        {",
            f'            Name\t"{sub_index}"',
            "            Type\tTriangleList",
            "            Shader",
            "            {",
            # Every original MenuDatas/3DModells model inspected uses BASE.
            "                Type\tBASE",
            f'                BaseTexture\t"{texture_name}"',
            "            } // Shader",
            f'            VertexNumber\t{len(submesh["vertices"])}',
            "            Coordinates",
            "            {",
        ]

        lines += [
            "                " + " ".join(fmt(value) for value in vertex)
            for vertex in submesh["vertices"]
        ]

        lines += [
            "            } // Coordinates",
            "            Normals",
            "            {",
        ]

        lines += [
            "                " + " ".join(fmt(value) for value in normal)
            for normal in submesh["normals"]
        ]

        lines += [
            "            } // Normals",
            "            Textcoord0",
            "            {",
        ]

        lines += [
            "                " + " ".join(fmt(value) for value in uv)
            for uv in submesh["uvs"]
        ]

        lines += [
            "            } // Textcoord0",
            "            WeightmapNumber\t0",
            f'            IndexNumber\t{len(submesh["indices"]) * 3}',
            "            Indices",
            "            {",
        ]

        lines += [
            "                " + " ".join(str(index) for index in triangle)
            for triangle in submesh["indices"]
        ]

        lines += [
            "            } // Indices",
            "        } // cSubMesh",
        ]

    lines += [
        "    } // cMesh",
        "    InstanceNumber\t1",
        "    cInstance",
        "    {",
        f'        Name\t"{instance_name}"',
        f'        Mesh\t"{mesh_name}"',
        "        Matrix",
        "        {",
        (
            "            1.000000 0.000000 0.000000 0.000000 "
            "0.000000 1.000000 0.000000 0.000000 "
            "0.000000 0.000000 1.000000 0.000000 "
            "0.000000 0.000000 0.000000 1.000000"
        ),
        "        } // Matrix",
        "    } // cInstance",
        "} // cPrimitive",
        "Ital",
        "{",
        "} // Ital",
        "",
    ]

    Path(filepath).write_text(
        "\n".join(lines),
        encoding="latin-1",
        newline="\n",
    )

    return len(objects), len(submeshes), mesh_name, instance_name


class EXPORT_OT_t3_menu_sca(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.t3_menu_sca"
    bl_label = "Export T3 Menu Model"
    bl_options = {"PRESET"}

    filename_ext = ".sca"

    filter_glob: StringProperty(
        default="*.sca",
        options={"HIDDEN"},
    )

    template_path: StringProperty(
        name="Original Menu Model SCA (recommended)",
        description=(
            "Optional original MenuDatas/3DModells SCA used only to preserve "
            "the exact cMesh and cInstance names"
        ),
        subtype="FILE_PATH",
        default="",
    )

    apply_modifiers: BoolProperty(
        name="Apply modifiers",
        description="Export evaluated geometry including active modifiers",
        default=True,
    )

    def execute(self, context):
        try:
            objects, submeshes, mesh_name, instance_name = write_menu_sca(
                self.filepath,
                context,
                self.template_path,
                self.apply_modifiers,
            )
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        self.report(
            {"INFO"},
            (
                f"Exported Menu Model from {objects} Blender mesh object(s), "
                f"{submeshes} submeshes"
            ),
        )
        self.report(
            {"INFO"},
            "Menu rules: UV V preserved, shader BASE, native axes, X mirror undone.",
        )
        return {"FINISHED"}


def menu_func_export(self, context):
    self.layout.operator(
        EXPORT_OT_t3_menu_sca.bl_idname,
        text="T3 Menu Model (.sca)",
    )


def register():
    bpy.utils.register_class(EXPORT_OT_t3_menu_sca)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy.utils.unregister_class(EXPORT_OT_t3_menu_sca)


if __name__ == "__main__":
    register()
