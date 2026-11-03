bl_info = {
    "name": "T3 ANM Animation Exporter",
    "author": "T3-ModTools",
    "version": (0, 8, 1),
    "blender": (3, 6, 0),
    "location": "File > Export > T3 Animation (.anm); Pose Mode right-click",
    "description": "Export T3 ANM Actions and manually add joints from Pose Mode",
    "category": "Import-Export",
}

import json
import re
from pathlib import Path

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty
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


FOOTSTEP_NAMES = ("Footstep_Left", "Footstep_Right")


def active_action(context):
    armature = active_armature(context)
    return armature.animation_data.action if armature and armature.animation_data else None


def footstep_notify_lines(action, start, end):
    """Use the same frame origin as exported poses (frame 0 stays frame 0)."""
    frames = {name: set() for name in FOOTSTEP_NAMES}
    for marker in action.pose_markers:
        if marker.name not in frames:
            continue
        if not start <= marker.frame <= end:
            raise RuntimeError(
                f"{marker.name} at frame {marker.frame} is outside the Action range "
                f"({start} to {end}). Move or remove this footstep before exporting."
            )
        frames[marker.name].add(marker.frame - start)
    events = [(name, sorted(values)) for name, values in frames.items() if values]
    if not events:
        raise RuntimeError(
            "Walk Animation is enabled but this Action has no footsteps. "
            "Choose a frame, then right-click > AnimationNotify Footstep_Left or Footstep_Right."
        )
    lines = ["AnimationNotify", "{", f"    NotifyNum\t{len(events)}"]
    for name, values in events:
        # cAnimManager::LoadAnim stores four frame integers at Notify + 0x88
        # in a 0x98-byte record. Never write past that native fixed-size array.
        if len(values) > 4:
            raise RuntimeError(f"{name} has {len(values)} frames; T3 supports at most 4 per Notify.")
        lines += ["    Notify", "    {", f'        Name\t"{name}"',
                  f"        FrameNum\t{len(values)}"]
        # After one Frame token the native parser consumes FrameNum integers.
        lines += ["        Frame\t" + " ".join(str(frame) for frame in values)]
        lines += ["    } // Notify"]
    return lines + ["} // AnimationNotify", ""]


class ANIM_OT_t3_footstep_add(bpy.types.Operator):
    bl_idname = "anim.t3_footstep_add"
    bl_label = "Assign T3 Footstep"
    bl_description = "Assign a footstep to the current timeline frame of the active armature Action"
    bl_options = {"REGISTER", "UNDO"}

    foot: EnumProperty(items=[(name, name, "") for name in FOOTSTEP_NAMES])

    @classmethod
    def poll(cls, context):
        action = active_action(context)
        return action is not None and action.is_editable

    def execute(self, context):
        action = active_action(context)
        frame = context.scene.frame_current
        if not any(m.name == self.foot and m.frame == frame for m in action.pose_markers):
            marker = action.pose_markers.new(self.foot)
            marker.frame = frame
        action.t3_walk_animation = True
        if context.space_data and context.space_data.type == "DOPESHEET_EDITOR":
            if context.space_data.mode == "ACTION":
                context.space_data.show_pose_markers = True
        for area in context.screen.areas if context.screen else []:
            area.tag_redraw()
        self.report({"INFO"}, f"{self.foot}: frame {frame} ({action.name})")
        return {"FINISHED"}


class ANIM_OT_t3_footstep_remove(bpy.types.Operator):
    bl_idname = "anim.t3_footstep_remove"
    bl_label = "Remove T3 Footstep"
    bl_options = {"UNDO"}

    marker_index: IntProperty(options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        return ANIM_OT_t3_footstep_add.poll(context)

    def execute(self, context):
        action = active_action(context)
        if not 0 <= self.marker_index < len(action.pose_markers):
            return {"CANCELLED"}
        marker = action.pose_markers[self.marker_index]
        if marker.name not in FOOTSTEP_NAMES:
            return {"CANCELLED"}
        action.pose_markers.remove(marker)
        return {"FINISHED"}


def draw_footstep_settings(layout, context, editable=False):
    action = active_action(context)
    if action is None:
        layout.label(text="Select an armature with an active Action")
        return
    box = layout.box()
    box.prop(action, "t3_walk_animation")
    if not action.t3_walk_animation:
        return
    box.label(text=f"Action: {action.name}")
    box.label(text=f"Current frame: {context.scene.frame_current}")
    markers = [(i, m) for i, m in enumerate(action.pose_markers) if m.name in FOOTSTEP_NAMES]
    for index, marker in sorted(markers, key=lambda item: (item[1].frame, item[1].name)):
        row = box.row(align=True)
        row.label(text=marker.name)
        if editable:
            row.prop(marker, "frame", text="")
            row.operator("anim.t3_footstep_remove", text="", icon="X").marker_index = index
        else:
            row.label(text=str(marker.frame))
    if not markers:
        box.label(text="No footsteps assigned", icon="ERROR")
    if editable:
        for name in FOOTSTEP_NAMES:
            box.operator("anim.t3_footstep_add", text=f"AnimationNotify {name}").foot = name


class DOPESHEET_PT_t3_footsteps(bpy.types.Panel):
    bl_label = "T3 AnimationNotify"
    bl_space_type = "DOPESHEET_EDITOR"
    bl_region_type = "UI"
    bl_category = "T3"

    def draw(self, context):
        draw_footstep_settings(self.layout, context, editable=True)


def menu_func_footsteps(self, context):
    if active_action(context) is None:
        return
    self.layout.separator()
    self.layout.label(text=f"T3 footsteps - frame {context.scene.frame_current}")
    for name in FOOTSTEP_NAMES:
        self.layout.operator("anim.t3_footstep_add", text=f"AnimationNotify {name}").foot = name


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


def added_joint_names(action):
    """Joints explicitly added in Pose Mode, separate from the imported ANM set."""
    raw = action.get("t3_added_joint_names_json", "")
    if not raw:
        return []
    try:
        values = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("The Action's manually added T3 joints are invalid.") from exc
    if not isinstance(values, list) or any(
        not isinstance(value, str) or not value.startswith("|") for value in values
    ) or len(set(values)) != len(values):
        raise RuntimeError("The Action's manually added T3 joints are invalid.")
    return values


def selected_armature_pose_bones(context, armature):
    selected = getattr(context, "selected_pose_bones_from_active_object", None)
    if selected is None:
        selected = getattr(context, "selected_pose_bones", None)
    selected_names = {bone.name for bone in selected or ()}
    return [bone for bone in armature.pose.bones if bone.name in selected_names]


def merge_joint_names(source_names, added_names):
    """Keep source order while placing newly added ancestors before descendants."""
    result = list(dict.fromkeys(source_names))
    for name in added_names:
        if name in result:
            continue
        prefix = name + "|"
        position = next(
            (index for index, existing in enumerate(result) if existing.startswith(prefix)),
            len(result),
        )
        result.insert(position, name)
    positions = {name: index for index, name in enumerate(result)}
    for name in result:
        parent = name.rsplit("|", 1)[0]
        if parent in positions and positions[parent] > positions[name]:
            raise RuntimeError(f"T3 joint order has {parent} after its child {name}.")
    return result


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
        if not source_names and action.get("t3_source_file", ""):
            raise RuntimeError("The imported Action has no valid T3 joint list.")

    if source_names:
        source_names = merge_joint_names(source_names, added_joint_names(action))
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


class ANIM_OT_t3_joint_add(bpy.types.Operator):
    bl_idname = "anim.t3_joint_add"
    bl_label = "(T3) Add Joint to animation"
    bl_description = "Append selected Pose Mode bones to this imported Action's ANM joint list"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        armature = active_armature(context)
        action = active_action(context)
        return (
            context.mode == "POSE" and armature is not None and action is not None
            and action.is_editable and bool(selected_armature_pose_bones(context, armature))
        )

    def execute(self, context):
        armature = active_armature(context)
        action = active_action(context)
        source_names = imported_joint_names(action)
        if not source_names:
            self.report({"ERROR"}, "Import a T3 ANM Action before adding joints.")
            return {"CANCELLED"}

        try:
            included_bones = {
                bone.name for bone, _ in ordered_export_bones(
                    armature, action, False, None, True, ""
                )
            }
            additions = added_joint_names(action)
            names = full_bone_names(armature)
            full_name_counts = {}
            for full_name in names.values():
                full_name_counts[full_name] = full_name_counts.get(full_name, 0) + 1
            new_names = []
            for bone in selected_armature_pose_bones(context, armature):
                if bone.name in included_bones:
                    continue
                full_name = names[bone.name]
                if full_name_counts[full_name] != 1:
                    raise RuntimeError(f"Ambiguous T3 joint path: {full_name}")
                if full_name not in additions and full_name not in new_names:
                    new_names.append(full_name)
        except (KeyError, RuntimeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        if new_names:
            action["t3_added_joint_names_json"] = json.dumps(
                additions + new_names, ensure_ascii=False
            )
        self.report({"INFO"}, f"Added {len(new_names)} T3 joint(s) to {action.name}")
        return {"FINISHED"}


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
    walk_animation=None,
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
    if walk_animation is None:
        walk_animation = getattr(action, "t3_walk_animation", False)
    notify_lines = footstep_notify_lines(action, start, end) if walk_animation else []
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
    lines += notify_lines
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
            "Export imported joints plus joints manually added in Pose Mode; this prevents "
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

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "animation_name")
        layout.prop(self, "selected_bones_only")
        layout.prop(self, "use_imported_joint_set")
        layout.prop(self, "reference_anm")
        draw_footstep_settings(layout, context)

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


def menu_func_add_joint(self, context):
    if context.mode == "POSE" and active_action(context) is not None:
        self.layout.separator()
        self.layout.operator(ANIM_OT_t3_joint_add.bl_idname, text="(T3) Add Joint to animation")


def register():
    bpy.types.Action.t3_walk_animation = BoolProperty(
        name="Walk Animation",
        description="Export this Action's Footstep_Left and Footstep_Right markers as AnimationNotify events",
        default=False,
    )
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    bpy.types.VIEW3D_MT_pose_context_menu.append(menu_func_add_joint)
    for name in CONTEXT_MENUS:
        menu = getattr(bpy.types, name, None)
        if menu is not None:
            menu.append(menu_func_footsteps)


def unregister():
    bpy.types.VIEW3D_MT_pose_context_menu.remove(menu_func_add_joint)
    for name in CONTEXT_MENUS:
        menu = getattr(bpy.types, name, None)
        if menu is not None:
            menu.remove(menu_func_footsteps)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    del bpy.types.Action.t3_walk_animation


CONTEXT_MENUS = ("DOPESHEET_MT_context_menu", "TIME_MT_context_menu")
CLASSES = (ANIM_OT_t3_footstep_add, ANIM_OT_t3_footstep_remove,
           ANIM_OT_t3_joint_add,
           DOPESHEET_PT_t3_footsteps, EXPORT_OT_t3_anm)


if __name__ == "__main__":
    register()
