bl_info = {
    "name": "T3 ANM Animation Importer",
    "author": "T3-ModTools",
    "version": (0, 5, 0),
    "blender": (3, 6, 0),
    "location": "File > Import > T3 Animation (.anm)",
    "description": "Apply a Terminator 3 .anm animation to a compatible imported T3 armature",
    "category": "Import-Export",
}

import json
import re
from pathlib import Path

import bpy
from bpy.props import StringProperty
from bpy_extras.io_utils import ImportHelper
from mathutils import Matrix

NUMBER_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")


def brace_end(text, opening):
    depth = 0
    in_quote = False
    escaped = False
    for index in range(opening, len(text)):
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


def iter_blocks(text, token):
    pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(token)}\s*\{{")
    position = 0
    while True:
        match = pattern.search(text, position)
        if not match:
            return
        opening = text.find("{", match.start())
        closing = brace_end(text, opening)
        if closing < 0:
            return
        yield text[opening + 1:closing]
        position = closing + 1



def iter_numbered_blocks(text, token):
    pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(token)}\s+([-+]?\d+)\s*\{{")
    position = 0
    while True:
        match = pattern.search(text, position)
        if not match:
            return
        opening = text.find("{", match.start())
        closing = brace_end(text, opening)
        if closing < 0:
            return
        yield int(match.group(1)), text[opening + 1:closing]
        position = closing + 1

def quoted_value(text, key, default=""):
    match = re.search(rf"\b{re.escape(key)}\b\s*[\t ]*\"([^\"]*)\"", text)
    return match.group(1) if match else default


def numeric_value(text, key, default=0.0):
    match = re.search(rf"\b{re.escape(key)}\b\s*[\t ]*\"?({NUMBER_RE.pattern})\"?", text)
    return float(match.group(1)) if match else default


def matrix_block(text):
    match = re.search(r"(?<![A-Za-z0-9_])TransformationMatrix\s*\{", text)
    if not match:
        return None
    opening = text.find("{", match.start())
    closing = brace_end(text, opening)
    if closing < 0:
        return None
    values = [float(value) for value in NUMBER_RE.findall(text[opening + 1:closing])][:16]
    if len(values) != 16:
        return None
    row_matrix = Matrix((
        values[0:4], values[4:8], values[8:12], values[12:16]
    ))
    # T3 stores row-vector matrices with translation in the last row.
    return row_matrix.transposed()


def parse_anm(filepath):
    raw = Path(filepath).read_bytes()
    text = raw.decode("utf-8", errors="replace")
    animation = next(iter_blocks(text, "Animation"), text)
    name = quoted_value(animation, "Name", Path(filepath).stem)
    fps = numeric_value(animation, "Fps", 25.0) or 25.0
    max_time = int(round(numeric_value(animation, "MaxTimeValue", 0.0)))
    frames = []
    joint_names = []
    seen_joint_names = set()
    for frame_number, time_block in iter_numbered_blocks(animation, "Time"):
        joints = {}
        for joint_block in iter_blocks(time_block, "Joint"):
            full_name = quoted_value(joint_block, "Name", "")
            matrix = matrix_block(joint_block)
            if full_name and matrix is not None:
                joints[full_name] = matrix
                if full_name not in seen_joint_names:
                    seen_joint_names.add(full_name)
                    joint_names.append(full_name)
        frames.append((frame_number, joints))
    return name, fps, max_time, joint_names, frames


def leaf_name(full_name):
    return full_name.rsplit("|", 1)[-1] or full_name


def active_armature(context):
    obj = context.object
    if obj and obj.type == "ARMATURE":
        return obj
    armatures = [candidate for candidate in context.selected_objects if candidate.type == "ARMATURE"]
    return armatures[0] if len(armatures) == 1 else None


def apply_animation(context, filepath):
    armature = active_armature(context)
    if armature is None:
        raise RuntimeError("Select the compatible T3 armature before importing the .anm file.")

    animation_name, fps, max_time, joint_names, frames = parse_anm(filepath)
    if not frames:
        raise RuntimeError("The .anm file contains no animation frames.")

    scene = context.scene
    scene.render.fps = max(1, round(fps))
    scene.frame_start = min(frame for frame, _ in frames)
    scene.frame_end = max(frame for frame, _ in frames)

    action = bpy.data.actions.new(name=animation_name)
    action["t3_fps"] = float(fps)
    action["t3_max_time_value"] = int(max_time or len(frames))
    action["t3_joint_names_json"] = json.dumps(joint_names, ensure_ascii=False)
    action["t3_source_file"] = str(Path(filepath))
    armature.animation_data_create()
    armature.animation_data.action = action

    pose_by_full = {}
    pose_by_leaf = {}
    duplicate_leaves = set()
    for pose_bone in armature.pose.bones:
        stored = ""
        for candidate in (pose_bone.bone, pose_bone):
            try:
                value = candidate.get("t3_full_name", "")
            except (AttributeError, TypeError):
                value = ""
            if isinstance(value, str) and value:
                stored = value if value.startswith("|") else "|" + value
                break
        if stored:
            pose_by_full[stored] = pose_bone
        leaf = pose_bone.name.rsplit("|", 1)[-1]
        if leaf in pose_by_leaf:
            duplicate_leaves.add(leaf)
        else:
            pose_by_leaf[leaf] = pose_bone
    missing = set()
    mapped = {}

    for full_name in joint_names:
        pose_bone = pose_by_full.get(full_name)
        leaf = leaf_name(full_name)
        if pose_bone is None and leaf not in duplicate_leaves:
            pose_bone = pose_by_leaf.get(leaf)
        if pose_bone is None:
            missing.add(leaf)
            continue
        mapped[full_name] = pose_bone
        pose_bone.bone["t3_full_name"] = full_name
        pose_bone["t3_full_name"] = full_name
        pose_bone.matrix_basis = Matrix.Identity(4)

    for frame, joint_matrices in frames:
        scene.frame_set(frame)
        for full_name, animated_local in joint_matrices.items():
            pose_bone = mapped.get(full_name)
            if pose_bone is None:
                continue

            rest_world = pose_bone.bone.matrix_local.copy()
            if pose_bone.parent:
                parent_rest_world = pose_bone.parent.bone.matrix_local.copy()
                rest_local = parent_rest_world.inverted_safe() @ rest_world
            else:
                rest_local = rest_world

            basis = rest_local.inverted_safe() @ animated_local
            location, rotation, scale = basis.decompose()
            pose_bone.rotation_mode = "QUATERNION"
            pose_bone.location = location
            pose_bone.rotation_quaternion = rotation
            pose_bone.scale = scale
            pose_bone.keyframe_insert(data_path="location", frame=frame, group=pose_bone.name)
            pose_bone.keyframe_insert(data_path="rotation_quaternion", frame=frame, group=pose_bone.name)
            pose_bone.keyframe_insert(data_path="scale", frame=frame, group=pose_bone.name)

    for fcurve in action.fcurves:
        for keyframe in fcurve.keyframe_points:
            keyframe.interpolation = "LINEAR"

    return animation_name, len(frames), len(missing), sorted(missing)


class IMPORT_OT_t3_anm(bpy.types.Operator, ImportHelper):
    bl_idname = "import_anim.t3_anm"
    bl_label = "Import T3 Animation"
    bl_options = {"UNDO"}

    filename_ext = ".anm"
    filter_glob: StringProperty(default="*.anm", options={"HIDDEN"})

    def execute(self, context):
        try:
            name, frame_count, missing_count, missing = apply_animation(context, self.filepath)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        message = f"Imported {name}: {frame_count} frames"
        if missing_count:
            preview = ", ".join(missing[:5])
            message += f"; {missing_count} unmatched bones ({preview})"
        self.report({"INFO"}, message)
        return {"FINISHED"}


def menu_func_import(self, context):
    self.layout.operator(IMPORT_OT_t3_anm.bl_idname, text="T3 Animation (.anm)")


def register():
    bpy.utils.register_class(IMPORT_OT_t3_anm)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.utils.unregister_class(IMPORT_OT_t3_anm)


if __name__ == "__main__":
    register()
