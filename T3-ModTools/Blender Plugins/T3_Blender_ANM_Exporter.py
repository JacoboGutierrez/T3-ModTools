bl_info = {
    "name": "T3 ANM Animation Exporter",
    "author": "T3-ModTools",
    "version": (0, 6, 0),
    "blender": (3, 6, 0),
    "location": "File > Export > T3 Animation (.anm)",
    "description": "Export the active Blender armature action to the T3 ANM text format",
    "category": "Import-Export",
}

import json
import re
from pathlib import Path

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy_extras.io_utils import ExportHelper


def fmt(value):
    if abs(value) < 0.0000005:
        value = 0.0
    return f"{value:.6f}"


def active_armature(context):
    if context.object and context.object.type == "ARMATURE":
        return context.object
    armatures = [obj for obj in context.selected_objects if obj.type == "ARMATURE"]
    return armatures[0] if len(armatures) == 1 else None


def stored_t3_full_name(armature, bone):
    """Recover the source SCA name preserved in glTF node extras.

    Blender's glTF importer normally exposes node extras as custom properties. Depending
    on the Blender version, a bone-node property can land on either the data bone or the
    corresponding pose bone, so check both locations.
    """
    candidates = [bone]
    pose_bone = armature.pose.bones.get(bone.name) if armature.pose else None
    if pose_bone is not None:
        candidates.append(pose_bone)
    for candidate in candidates:
        try:
            value = candidate.get("t3_full_name", "")
        except (AttributeError, TypeError):
            value = ""
        if isinstance(value, str) and value.strip():
            return value if value.startswith("|") else "|" + value
    return ""


def full_bone_names(armature):
    result = {}

    def resolve(bone):
        if bone.name in result:
            return result[bone.name]
        stored_name = stored_t3_full_name(armature, bone)
        if stored_name:
            name = stored_name
        elif "|" in bone.name:
            name = bone.name if bone.name.startswith("|") else "|" + bone.name
        elif bone.parent:
            name = resolve(bone.parent) + "|" + bone.name
        else:
            name = "|" + bone.name
        result[bone.name] = name
        return name

    for bone in armature.data.bones:
        resolve(bone)
    return result


def imported_joint_names(action):
    """Return the exact joint order recorded by the ANM importer, when available."""
    try:
        raw = action.get("t3_joint_names_json", "")
    except (AttributeError, TypeError):
        raw = ""
    if not isinstance(raw, str) or not raw:
        return []
    try:
        values = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [value for value in values if isinstance(value, str) and value]


def reference_joint_names(filepath):
    """Read the first occurrence of every Joint name from a reference ANM."""
    if not filepath:
        return []
    path = Path(bpy.path.abspath(filepath)).expanduser()
    if not path.is_file():
        raise RuntimeError(f"Reference ANM was not found: {path}")
    text = path.read_bytes().decode("utf-8", errors="replace")
    values = re.findall(
        r'(?s)(?<![A-Za-z0-9_])Joint\s*\{.*?\bName\s*[\t ]*"([^"]+)"', text
    )
    # Every frame repeats the same joint list. Preserve only the first occurrence/order.
    result = []
    seen = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    if not result:
        raise RuntimeError(f"Reference ANM contains no Joint names: {path}")
    return result


def ordered_export_bones(
    armature,
    action,
    selected_only,
    selected_pose_bones,
    use_imported_joint_set,
    reference_anm,
):
    names = full_bone_names(armature)
    pose_bones = list(armature.pose.bones)
    by_full_name = {names[bone.name]: bone for bone in pose_bones}
    by_leaf = {}
    duplicate_leaves = set()
    for bone in pose_bones:
        leaf = bone.name.rsplit("|", 1)[-1]
        if leaf in by_leaf:
            duplicate_leaves.add(leaf)
        else:
            by_leaf[leaf] = bone

    source_names = reference_joint_names(reference_anm)
    if not source_names and use_imported_joint_set:
        source_names = imported_joint_names(action)

    if source_names:
        result = []
        missing = []
        used = set()
        for full_name in source_names:
            bone = by_full_name.get(full_name)
            leaf = full_name.rsplit("|", 1)[-1]
            if bone is None and leaf not in duplicate_leaves:
                bone = by_leaf.get(leaf)
            if bone is None:
                missing.append(full_name)
                continue
            if bone.name in used:
                continue
            used.add(bone.name)
            result.append((bone, full_name))
        if missing:
            preview = ", ".join(missing[:5])
            raise RuntimeError(
                f"The armature is missing {len(missing)} reference joints ({preview})."
            )
    else:
        result = [(bone, names[bone.name]) for bone in pose_bones]

    if selected_only:
        selected_names = {bone.name for bone in selected_pose_bones or []}
        result = [(bone, full_name) for bone, full_name in result if bone.name in selected_names]
    if not result:
        raise RuntimeError("No pose bones are available for export.")
    return result


def t3_row_values(matrix):
    row_matrix = matrix.transposed()
    return [row_matrix[row][column] for row in range(4) for column in range(4)]


def export_anm(
    filepath,
    context,
    action_name,
    selected_only,
    use_imported_joint_set=True,
    reference_anm="",
):
    armature = active_armature(context)
    if armature is None:
        raise RuntimeError("Select the T3 armature before exporting an animation.")
    action = armature.animation_data.action if armature.animation_data else None
    if action is None:
        raise RuntimeError("The selected armature has no active Action.")

    scene = context.scene
    start = int(round(action.frame_range[0]))
    end = int(round(action.frame_range[1]))
    if end < start:
        start, end = end, start
    scene_fps = scene.render.fps / (scene.render.fps_base or 1.0)
    try:
        fps = float(action.get("t3_fps", scene_fps))
    except (TypeError, ValueError):
        fps = scene_fps
    export_bones = ordered_export_bones(
        armature,
        action,
        selected_only,
        context.selected_pose_bones,
        use_imported_joint_set,
        reference_anm,
    )

    previous_frame = scene.frame_current
    lines = [
        "//Clevers Animation file",
        "//Exported by T3-ModTools Blender plugin",
        "",
        "Animation",
        "{",
        f'    Name\t"{action_name or action.name}"',
        f"    Fps\t{fmt(fps)}",
        # Native T3 files store the frame count here, not the last zero-based frame.
        f"    MaxTimeValue\t{end - start + 1}",
    ]
    try:
        for source_frame in range(start, end + 1):
            scene.frame_set(source_frame)
            frame_number = source_frame - start
            lines += [f"    Time {frame_number}", "    {"]
            for pose_bone, full_name in export_bones:
                if pose_bone.parent:
                    animated_local = pose_bone.parent.matrix.inverted_safe() @ pose_bone.matrix
                else:
                    animated_local = pose_bone.matrix.copy()
                values = t3_row_values(animated_local)
                lines += [
                    "        Joint",
                    "        {",
                    f'            Name\t"{full_name}"',
                    "            TransformationMatrix",
                    "            {",
                    "                " + " ".join(fmt(value) for value in values),
                    "            } // TransformationMatrix",
                    "        } // Joint",
                ]
            lines += ["    } // Time"]
    finally:
        scene.frame_set(previous_frame)
    lines += ["} // Animation", ""]
    Path(filepath).write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return end - start + 1, len(export_bones)


class EXPORT_OT_t3_anm(bpy.types.Operator, ExportHelper):
    bl_idname = "export_anim.t3_anm"
    bl_label = "Export T3 Animation"
    bl_options = {"PRESET"}

    filename_ext = ".anm"
    filter_glob: StringProperty(default="*.anm", options={"HIDDEN"})
    animation_name: StringProperty(
        name="Animation name",
        description="Name written inside the ANM file; the Action name is used when empty",
        default="",
    )
    selected_bones_only: BoolProperty(
        name="Selected pose bones only",
        description="Export only selected pose bones instead of the complete armature",
        default=False,
    )
    use_imported_joint_set: BoolProperty(
        name="Preserve imported ANM joint set",
        description=(
            "Export only the joints and order recorded by the ANM importer; this prevents "
            "an upper-body overlay from becoming an invalid full-body animation"
        ),
        default=True,
    )
    reference_anm: StringProperty(
        name="Reference ANM",
        description=(
            "Optional native ANM whose joint list/order should be used as the export template"
        ),
        subtype="FILE_PATH",
        default="",
    )

    def execute(self, context):
        try:
            frames, bones = export_anm(
                self.filepath,
                context,
                self.animation_name,
                self.selected_bones_only,
                self.use_imported_joint_set,
                self.reference_anm,
            )
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Exported {frames} frames and {bones} bones")
        return {"FINISHED"}


def menu_func_export(self, context):
    self.layout.operator(EXPORT_OT_t3_anm.bl_idname, text="T3 Animation (.anm)")


def register():
    bpy.utils.register_class(EXPORT_OT_t3_anm)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy.utils.unregister_class(EXPORT_OT_t3_anm)


if __name__ == "__main__":
    register()
