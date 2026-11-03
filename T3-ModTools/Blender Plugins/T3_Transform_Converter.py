bl_info = {
    "name": "T3 Transform Converter",
    "author": "OpenAI",
    "version": (2, 0, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > Animation > T3 Transform Converter",
    "description": "Converts pose transforms to and from editable TXT files",
    "category": "Animation",
}

import bpy
import re
from mathutils import Quaternion
from bpy.props import (
    BoolProperty,
    EnumProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import Operator, Panel
from bpy_extras.io_utils import ExportHelper, ImportHelper


TEXT_BLOCK_NAME = "T3_Transforms.txt"
REVERSED_TEXT_BLOCK_NAME = "T3_Transforms_Reversed.txt"


NUMBER_RE = r"[+-]?(?:\d+(?:[\.,]\d*)?|[\.,]\d+)(?:[eE][+-]?\d+)?"


def parse_number(text):
    """Parse dot/comma decimal values, including scientific notation."""
    return float(text.strip().replace(',', '.'))


def parse_transform_report(text):
    """
    Parse editable report sections.

    The target bone is taken from EACH section header, e.g.:
        left_wrist w F0 a F3:

    Absolute values printed on the left are retained as metadata. The importer
    primarily uses signed frame-to-frame changes, while a F0-to-F0 section uses
    its sole absolute value to reconstruct a static one-frame pose.
    """
    component_pattern = (
        r"location\s+[xyz]|scale\s+[xyz]|w|x|y|z"
    )
    header_re = re.compile(
        rf"^\s*(?P<bone>.+?)\s+(?P<component>{component_pattern})\s+"
        rf"F(?P<start>-?\d+)\s+(?:a|to)\s+F(?P<end>-?\d+)\s*:\s*$",
        re.IGNORECASE,
    )
    transition_re = re.compile(
        rf"^\s*(?P<current>{NUMBER_RE})\s*\(\s*frame\s+(?P<frame>-?\d+)\s*\)\s*"
        rf"(?P<op>más|mas|menos|plus|minus|\+|-)\s*"
        rf"(?P<change>{NUMBER_RE})\s*=\s*frame\s+(?P<next>-?\d+)\s*$",
        re.IGNORECASE,
    )
    final_re = re.compile(
        rf"^\s*(?P<value>{NUMBER_RE})\s*\(\s*frame\s+(?P<frame>-?\d+)\s*\)\s*$",
        re.IGNORECASE,
    )

    sections = []
    current = None

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        header_match = header_re.match(line)
        if header_match:
            current = {
                'bone': header_match.group('bone').strip(),
                'component': re.sub(r"\s+", " ", header_match.group('component').lower()),
                'start': int(header_match.group('start')),
                'end': int(header_match.group('end')),
                'transitions': [],
                'final_value': None,
                'final_frame': None,
                'line': line_number,
            }
            sections.append(current)
            continue

        if current is None:
            continue

        transition_match = transition_re.match(line)
        if transition_match:
            op = transition_match.group('op').lower()
            magnitude = abs(parse_number(transition_match.group('change')))
            signed_change = magnitude if op in {'más', 'mas', 'plus', '+'} else -magnitude
            current['transitions'].append({
                'frame': int(transition_match.group('frame')),
                'next_frame': int(transition_match.group('next')),
                'current_text_value': parse_number(transition_match.group('current')),
                'change': signed_change,
                'line': line_number,
            })
            continue

        final_match = final_re.match(line)
        if final_match:
            current['final_value'] = parse_number(final_match.group('value'))
            current['final_frame'] = int(final_match.group('frame'))

    return [
        section
        for section in sections
        if section['transitions']
        or (
            section['start'] == section['end']
            and section['final_value'] is not None
            and section['final_frame'] == section['start']
        )
    ]


def component_info(component):
    component = component.lower()
    if component in {'w', 'x', 'y', 'z'}:
        return 'rotation_quaternion', {'w': 0, 'x': 1, 'y': 2, 'z': 3}[component]
    if component.startswith('location '):
        return 'location', {'x': 0, 'y': 1, 'z': 2}[component[-1]]
    if component.startswith('scale '):
        return 'scale', {'x': 0, 'y': 1, 'z': 2}[component[-1]]
    raise ValueError(f"Unsupported component: {component}")


def get_pose_component_value(pbone, component):
    data_path, index = component_info(component)
    values = getattr(pbone, data_path)
    return float(values[index])


def set_pose_component_value(pbone, component, value):
    data_path, index = component_info(component)
    values = getattr(pbone, data_path)
    values[index] = value
    return data_path, index


def apply_transform_sections(context, sections, use_text_start=False):
    scene = context.scene
    obj = get_armature(context)
    if not obj:
        raise RuntimeError("Select an Armature object.")

    if not sections:
        raise RuntimeError("No valid transform sections were found in the TXT file.")

    original_frame = scene.frame_current
    applied_sections = 0
    inserted_keys = 0
    missing_bones = set()
    errors = []

    try:
        for section in sections:
            bone_name = section['bone']
            component = section['component']
            pbone = obj.pose.bones.get(bone_name)

            if pbone is None:
                missing_bones.add(bone_name)
                continue

            if component in {'w', 'x', 'y', 'z'} and pbone.rotation_mode != 'QUATERNION':
                errors.append(
                    f"{bone_name} {component}: bone rotation mode is {pbone.rotation_mode}, not QUATERNION"
                )
                continue

            transitions = sorted(section['transitions'], key=lambda item: (item['frame'], item['next_frame']))
            if not transitions:
                # A one-frame idle/pose report has no transitions. Its sole absolute
                # value is therefore the complete animation data and must be
                # applied regardless of the multi-frame "Use TXT Start Value"
                # option.
                static_value = section.get('final_value')
                static_frame = section.get('final_frame')
                if static_value is None or static_frame is None:
                    continue
                scene.frame_set(static_frame)
                context.view_layer.update()
                data_path, index = set_pose_component_value(pbone, component, static_value)
                pbone.keyframe_insert(
                    data_path=data_path,
                    index=index,
                    frame=static_frame,
                    group=pbone.name,
                )
                inserted_keys += 1
                applied_sections += 1
                continue

            start_frame = transitions[0]['frame']
            scene.frame_set(start_frame)
            context.view_layer.update()

            if use_text_start:
                current_value = transitions[0]['current_text_value']
                data_path, index = set_pose_component_value(pbone, component, current_value)
            else:
                current_value = get_pose_component_value(pbone, component)
                data_path, index = component_info(component)

            # Preserve/establish the target's starting value as the first key.
            pbone.keyframe_insert(data_path=data_path, index=index, frame=start_frame, group=pbone.name)
            inserted_keys += 1

            current_frame = start_frame

            for transition in transitions:
                # Sections are expected to be sequential. If a manually edited
                # file jumps to another source frame, continue from the current
                # accumulated target value and apply the requested change there.
                if transition['frame'] != current_frame:
                    current_frame = transition['frame']
                    scene.frame_set(current_frame)
                    context.view_layer.update()
                    # Do NOT resample target animation here: the TXT is a change
                    # chain, so the accumulated value remains authoritative.

                current_value += transition['change']
                next_frame = transition['next_frame']
                scene.frame_set(next_frame)
                context.view_layer.update()
                data_path, index = set_pose_component_value(pbone, component, current_value)
                pbone.keyframe_insert(data_path=data_path, index=index, frame=next_frame, group=pbone.name)
                inserted_keys += 1
                current_frame = next_frame

            applied_sections += 1

    finally:
        scene.frame_set(original_frame)
        context.view_layer.update()

    return {
        'applied_sections': applied_sections,
        'inserted_keys': inserted_keys,
        'missing_bones': sorted(missing_bones),
        'errors': errors,
    }


def get_armature(context):
    obj = context.object
    if obj and obj.type == 'ARMATURE':
        return obj
    return None


def get_target_bones(context, obj, scope):
    if scope == 'ALL':
        return list(obj.pose.bones)

    if scope == 'SELECTED':
        # Blender 5.x no longer exposes Bone.select. Use the pose-bone selection
        # supplied by the current context, which is also available in Blender 3.6/4.x.
        selected = getattr(context, "selected_pose_bones_from_active_object", None)
        if selected is None:
            selected = getattr(context, "selected_pose_bones", None)

        selected_names = {
            selected_bone.name
            for selected_bone in selected or ()
            if getattr(selected_bone, "name", "")
        }
        # Preserve the armature's original pose-bone order, matching the older
        # implementation while filtering by the modern context selection.
        return [pbone for pbone in obj.pose.bones if pbone.name in selected_names]

    # ACTIVE
    active_pose_bone = getattr(context, "active_pose_bone", None)
    if active_pose_bone is not None:
        pb = obj.pose.bones.get(active_pose_bone.name)
        if pb is not None:
            return [pb]

    active_data_bone = obj.data.bones.active
    if not active_data_bone:
        return []
    pb = obj.pose.bones.get(active_data_bone.name)
    return [pb] if pb else []


def channel_quaternion(pbone):
    """Return the pose bone's own rotation channel as a quaternion."""
    mode = pbone.rotation_mode

    if mode == 'QUATERNION':
        return pbone.rotation_quaternion.copy()

    if mode == 'AXIS_ANGLE':
        aa = pbone.rotation_axis_angle
        angle = aa[0]
        axis = (aa[1], aa[2], aa[3])
        return Quaternion(axis, angle)

    return pbone.rotation_euler.to_quaternion()


def evaluated_quaternion(pbone):
    """Return evaluated pose orientation in armature/object space."""
    return pbone.matrix.to_quaternion()


def mirror_pose_x(quaternion, location):
    """Mirror pose components across the armature X axis without editing the scene."""
    mirrored_quaternion = quaternion.copy()
    mirrored_quaternion.y = -mirrored_quaternion.y
    mirrored_quaternion.z = -mirrored_quaternion.z

    mirrored_location = location.copy()
    mirrored_location.x = -mirrored_location.x
    return mirrored_quaternion, mirrored_location


def format_number(value, precision, decimal_separator):
    # Avoid visual "-0.000000" noise.
    epsilon = 0.5 * (10.0 ** -precision)
    if abs(value) < epsilon:
        value = 0.0

    s = f"{value:.{precision}f}"
    if decimal_separator == 'COMMA':
        s = s.replace('.', ',')
    return s


def change_word(change, language):
    if change >= 0.0:
        return "más" if language == 'ES' else "plus"
    return "menos" if language == 'ES' else "minus"


def build_component_section(
    bone_name,
    component_name,
    frames,
    values,
    precision,
    decimal_separator,
    language,
):
    first = frames[0]
    last = frames[-1]

    if language == 'ES':
        header = f"{bone_name} {component_name} F{first} a F{last}:"
        frame_word = "frame"
        equals_word = "frame"
    else:
        header = f"{bone_name} {component_name} F{first} to F{last}:"
        frame_word = "frame"
        equals_word = "frame"

    lines = [
        header,
        "*" * max(18, len(header)),
    ]

    for i in range(len(frames) - 1):
        current_frame = frames[i]
        next_frame = frames[i + 1]
        current = values[i]
        nxt = values[i + 1]
        change = nxt - current

        sign_word = change_word(change, language)
        change_abs = format_number(abs(change), precision, decimal_separator)
        current_s = format_number(current, precision, decimal_separator)

        lines.append(
            f"{current_s} ({frame_word} {current_frame}) "
            f"{sign_word} {change_abs} = {equals_word} {next_frame}"
        )

    last_s = format_number(values[-1], precision, decimal_separator)
    lines.append(f"{last_s} ({frame_word} {frames[-1]})")
    lines.append("")
    return "\n".join(lines)


def ensure_quaternion_continuity(quaternions):
    """
    q and -q represent the same orientation.
    Flip signs when needed so component changes do not contain artificial jumps.
    """
    if not quaternions:
        return quaternions

    result = [quaternions[0].copy()]
    previous = result[0]

    for q in quaternions[1:]:
        current = q.copy()
        if previous.dot(current) < 0.0:
            current.negate()
        result.append(current)
        previous = current

    return result


def analyze_transforms(context, reverse=False, text_block_name=TEXT_BLOCK_NAME):
    scene = context.scene
    obj = get_armature(context)

    if not obj:
        raise RuntimeError("Select an Armature object.")

    props = scene.t3tc_settings
    start = props.frame_start
    end = props.frame_end
    step = props.frame_step

    if step < 1:
        raise RuntimeError("Frame step must be at least 1.")

    if end < start:
        start, end = end, start

    frames = list(range(start, end + 1, step))
    if not frames:
        raise RuntimeError("No frames to analyze.")

    bones = get_target_bones(context, obj, props.bone_scope)
    if not bones:
        if props.bone_scope == 'SELECTED':
            raise RuntimeError("No pose bones are selected.")
        if props.bone_scope == 'ACTIVE':
            raise RuntimeError("No active pose bone.")
        raise RuntimeError("No bones found.")

    original_frame = scene.frame_current
    output = []

    source_label = {
        'CHANNEL': "Rotation Channel",
        'EVALUATED': "Evaluated Pose Matrix",
    }[props.rotation_source]

    output.append("T3 TRANSFORM CONVERTER")
    output.append("=" * 22)
    output.append(f"Armature: {obj.name}")
    output.append(f"Frames: {frames[0]} -> {frames[-1]} | Step: {step}")
    output.append(f"Rotation source: {source_label}")
    output.append(
        "Temporal order: REVERSED (last sampled value becomes first frame)"
        if reverse
        else "Temporal order: NORMAL"
    )
    output.append(
        "Quaternion continuity: ON"
        if props.quaternion_continuity
        else "Quaternion continuity: OFF"
    )
    output.append("X mirror: ON" if props.mirror_x else "X mirror: OFF")
    output.append("")
    output.append(
        "Transform change: next frame value - current frame value."
        if props.language == 'EN'
        else "Cambio de transformación: valor del frame siguiente - valor del frame actual."
    )
    output.append("")

    try:
        # Store samples by bone so each frame is evaluated only once.
        samples = {
            pb.name: {
                'quat': [],
                'loc': [],
                'scale': [],
            }
            for pb in bones
        }

        for frame in frames:
            scene.frame_set(frame)
            context.view_layer.update()

            for pb in bones:
                if props.rotation_source == 'EVALUATED':
                    q = evaluated_quaternion(pb)
                else:
                    q = channel_quaternion(pb)

                location = pb.location.copy()
                if props.mirror_x:
                    q, location = mirror_pose_x(q, location)

                samples[pb.name]['quat'].append(q.copy())
                samples[pb.name]['loc'].append(location)
                samples[pb.name]['scale'].append(pb.scale.copy())

        for pb in bones:
            bone_samples = samples[pb.name]

            # Reverse the sampled VALUES while preserving the original ascending
            # frame labels. Example: original F0..F32 becomes value(F32)..value(F0)
            # mapped back onto F0..F32. This creates a true time-reversed report.
            quats = list(bone_samples['quat'])
            locs = list(bone_samples['loc'])
            scales = list(bone_samples['scale'])

            if reverse:
                quats.reverse()
                locs.reverse()
                scales.reverse()

            # Quaternion sign continuity must be evaluated in the OUTPUT temporal
            # direction, especially for reversed animation data.
            if props.quaternion_continuity:
                quats = ensure_quaternion_continuity(quats)

            output.append(f"[{pb.name}]")
            output.append("")

            if props.include_rotation:
                components = {
                    'w': [q.w for q in quats],
                    'x': [q.x for q in quats],
                    'y': [q.y for q in quats],
                    'z': [q.z for q in quats],
                }

                for component_name in ('w', 'x', 'y', 'z'):
                    output.append(
                        build_component_section(
                            pb.name,
                            component_name,
                            frames,
                            components[component_name],
                            props.precision,
                            props.decimal_separator,
                            props.language,
                        )
                    )

            if props.include_location:
                for index, axis in enumerate(('location x', 'location y', 'location z')):
                    output.append(
                        build_component_section(
                            pb.name,
                            axis,
                            frames,
                            [v[index] for v in locs],
                            props.precision,
                            props.decimal_separator,
                            props.language,
                        )
                    )

            if props.include_scale:
                for index, axis in enumerate(('scale x', 'scale y', 'scale z')):
                    output.append(
                        build_component_section(
                            pb.name,
                            axis,
                            frames,
                            [v[index] for v in scales],
                            props.precision,
                            props.decimal_separator,
                            props.language,
                        )
                    )

            output.append("-" * 60)
            output.append("")

    finally:
        scene.frame_set(original_frame)
        context.view_layer.update()

    result = "\n".join(output)

    text = bpy.data.texts.get(text_block_name)
    if text is None:
        text = bpy.data.texts.new(text_block_name)
    else:
        text.clear()
    text.write(result)

    return result, len(bones), len(frames)


class T3TC_Settings(bpy.types.PropertyGroup):
    frame_start: IntProperty(
        name="Start",
        description="First frame to analyze",
        default=0,
    )

    frame_end: IntProperty(
        name="End",
        description="Last frame to analyze",
        default=3,
    )

    frame_step: IntProperty(
        name="Step",
        description="Frame increment",
        default=1,
        min=1,
    )

    bone_scope: EnumProperty(
        name="Bones",
        description="Which pose bones to analyze",
        items=[
            ('ACTIVE', "Active Bone", "Analyze only the active pose bone"),
            ('SELECTED', "Selected Bones", "Analyze selected pose bones"),
            ('ALL', "All Bones", "Analyze all pose bones in the armature"),
        ],
        default='ACTIVE',
    )

    rotation_source: EnumProperty(
        name="Rotation Source",
        description="Choose raw rotation channels or evaluated pose orientation",
        items=[
            (
                'CHANNEL',
                "Rotation Channel",
                "Read the bone's own rotation values; closest to quaternion F-Curve W/X/Y/Z values",
            ),
            (
                'EVALUATED',
                "Evaluated Pose",
                "Read final evaluated orientation from the pose matrix, including parent/constraint effects",
            ),
        ],
        default='CHANNEL',
    )

    include_rotation: BoolProperty(
        name="Quaternion WXYZ",
        default=True,
        description="Include quaternion rotation components",
    )

    include_location: BoolProperty(
        name="Location XYZ",
        default=False,
        description="Include pose-bone location channels",
    )

    include_scale: BoolProperty(
        name="Scale XYZ",
        default=False,
        description="Include pose-bone scale channels",
    )

    quaternion_continuity: BoolProperty(
        name="Prevent Quaternion Sign Flips",
        default=True,
        description="Treat q and -q as equivalent and prevent artificial frame-to-frame jumps",
    )

    mirror_x: BoolProperty(
        name="Mirror X on Export",
        default=False,
        description=(
            "Mirror exported pose values across the armature X axis without changing the scene: "
            "negate location X and quaternion Y/Z; bone names and scale stay unchanged"
        ),
    )

    precision: IntProperty(
        name="Decimals",
        description="Number of decimal places in the report",
        default=6,
        min=1,
        max=15,
    )

    decimal_separator: EnumProperty(
        name="Decimal Separator",
        items=[
            ('DOT', "Dot", "Use 0.123456"),
            ('COMMA', "Comma", "Use 0,123456"),
        ],
        default='DOT',
    )

    language: EnumProperty(
        name="Report Language",
        items=[
            ('ES', "Español", "Use más/menos and Spanish report labels"),
            ('EN', "English", "Use plus/minus and English report labels"),
        ],
        default='ES',
    )

    import_use_text_start: BoolProperty(
        name="Use TXT Start Value",
        description=(
            "If disabled, each target bone keeps its own value at the first frame "
            "and only the TXT frame changes are applied. If enabled, the first absolute "
            "value from the TXT is used as the starting value. One-frame reports "
            "always use their sole absolute TXT value"
        ),
        default=False,
    )


class T3TC_OT_use_timeline_range(Operator):
    bl_idname = "t3tc.use_timeline_range"
    bl_label = "Use Timeline Range"
    bl_description = "Copy the scene playback range into Start and End"

    def execute(self, context):
        props = context.scene.t3tc_settings
        props.frame_start = context.scene.frame_start
        props.frame_end = context.scene.frame_end
        return {'FINISHED'}


class T3TC_OT_analyze(Operator):
    bl_idname = "t3tc.analyze"
    bl_label = "Analyze Transforms"
    bl_description = "Analyze pose-transform changes across the selected frame range"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            _result, bone_count, frame_count = analyze_transforms(context)
        except RuntimeError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        except Exception as exc:
            self.report({'ERROR'}, f"Analysis failed: {exc}")
            return {'CANCELLED'}

        self.report(
            {'INFO'},
            f"Analyzed {bone_count} bone(s), {frame_count} frame(s). "
            f"Result: {TEXT_BLOCK_NAME}",
        )
        return {'FINISHED'}


class T3TC_OT_analyze_reversed(Operator):
    bl_idname = "t3tc.analyze_reversed"
    bl_label = "Analyze Reversed Transforms"
    bl_description = (
        "Analyze the selected frame range in reverse temporal order: "
        "the last sampled transform becomes the first frame"
    )
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            _result, bone_count, frame_count = analyze_transforms(
                context,
                reverse=True,
                text_block_name=REVERSED_TEXT_BLOCK_NAME,
            )
        except RuntimeError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        except Exception as exc:
            self.report({'ERROR'}, f"Reverse analysis failed: {exc}")
            return {'CANCELLED'}

        self.report(
            {'INFO'},
            f"Reversed {bone_count} bone(s), {frame_count} frame(s). "
            f"Result: {REVERSED_TEXT_BLOCK_NAME}",
        )
        return {'FINISHED'}


class T3TC_OT_copy_results(Operator):
    bl_idname = "t3tc.copy_results"
    bl_label = "Copy Results"
    bl_description = "Copy the latest report to the clipboard"

    def execute(self, context):
        text = bpy.data.texts.get(TEXT_BLOCK_NAME)
        if text is None:
            self.report({'ERROR'}, "Run Analyze Transforms first.")
            return {'CANCELLED'}

        context.window_manager.clipboard = text.as_string()
        self.report({'INFO'}, "Results copied to clipboard.")
        return {'FINISHED'}


class T3TC_OT_open_text_editor(Operator):
    bl_idname = "t3tc.open_text_editor"
    bl_label = "Show Results"
    bl_description = "Open the latest result in a Text Editor area"

    def execute(self, context):
        text = bpy.data.texts.get(TEXT_BLOCK_NAME)
        if text is None:
            self.report({'ERROR'}, "Run Analyze Transforms first.")
            return {'CANCELLED'}

        area = context.area
        if area is None:
            return {'CANCELLED'}

        area.type = 'TEXT_EDITOR'
        area.spaces.active.text = text
        return {'FINISHED'}


class T3TC_OT_export_txt(Operator, ExportHelper):
    bl_idname = "t3tc.export_txt"
    bl_label = "Export Transforms as TXT"
    bl_description = "Save the latest report as a text file"

    filename_ext = ".txt"

    filter_glob: StringProperty(
        default="*.txt",
        options={'HIDDEN'},
    )

    def execute(self, context):
        text = bpy.data.texts.get(TEXT_BLOCK_NAME)
        if text is None:
            self.report({'ERROR'}, "Run Analyze Transforms first.")
            return {'CANCELLED'}

        try:
            with open(self.filepath, "w", encoding="utf-8", newline="\n") as f:
                f.write(text.as_string())
        except OSError as exc:
            self.report({'ERROR'}, f"Could not save file: {exc}")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Saved: {self.filepath}")
        return {'FINISHED'}



class T3TC_OT_export_reversed_txt(Operator, ExportHelper):
    bl_idname = "t3tc.export_reversed_txt"
    bl_label = "Export Reversed Transforms as TXT"
    bl_description = (
        "Export a time-reversed report directly: frame labels stay ascending, "
        "but transform values are mapped from the last sampled frame to the first"
    )

    filename_ext = ".txt"

    filter_glob: StringProperty(
        default="*.txt",
        options={'HIDDEN'},
    )

    def execute(self, context):
        try:
            result, bone_count, frame_count = analyze_transforms(
                context,
                reverse=True,
                text_block_name=REVERSED_TEXT_BLOCK_NAME,
            )
        except RuntimeError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        except Exception as exc:
            self.report({'ERROR'}, f"Reverse export failed: {exc}")
            return {'CANCELLED'}

        try:
            with open(self.filepath, "w", encoding="utf-8", newline="\n") as f:
                f.write(result)
        except OSError as exc:
            self.report({'ERROR'}, f"Could not save reversed TXT: {exc}")
            return {'CANCELLED'}

        self.report(
            {'INFO'},
            f"Saved reversed animation: {bone_count} bone(s), "
            f"{frame_count} frame(s) -> {self.filepath}",
        )
        return {'FINISHED'}


class T3TC_OT_copy_reversed_results(Operator):
    bl_idname = "t3tc.copy_reversed_results"
    bl_label = "Copy Reversed Results"
    bl_description = "Copy the latest reversed report to the clipboard"

    def execute(self, context):
        text = bpy.data.texts.get(REVERSED_TEXT_BLOCK_NAME)
        if text is None:
            self.report({'ERROR'}, "Run Analyze Reversed Transforms first.")
            return {'CANCELLED'}

        context.window_manager.clipboard = text.as_string()
        self.report({'INFO'}, "Reversed results copied to clipboard.")
        return {'FINISHED'}


class T3TC_OT_open_reversed_text_editor(Operator):
    bl_idname = "t3tc.open_reversed_text_editor"
    bl_label = "Show Reversed Results"
    bl_description = "Open the latest reversed result in a Text Editor area"

    def execute(self, context):
        text = bpy.data.texts.get(REVERSED_TEXT_BLOCK_NAME)
        if text is None:
            self.report({'ERROR'}, "Run Analyze Reversed Transforms first.")
            return {'CANCELLED'}

        area = context.area
        if area is None:
            return {'CANCELLED'}

        area.type = 'TEXT_EDITOR'
        area.spaces.active.text = text
        return {'FINISHED'}


class T3TC_OT_import_apply_txt(Operator, ImportHelper):
    bl_idname = "t3tc.import_apply_txt"
    bl_label = "Import / Apply Transform TXT"
    bl_description = (
        "Read an edited T3 Transform TXT and apply its plus/minus changes, "
        "or its absolute value for a one-frame pose, to the named bones"
    )
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".txt"

    filter_glob: StringProperty(
        default="*.txt",
        options={'HIDDEN'},
    )

    def execute(self, context):
        try:
            with open(self.filepath, "r", encoding="utf-8-sig") as f:
                text = f.read()
        except (OSError, UnicodeError) as exc:
            self.report({'ERROR'}, f"Could not read TXT: {exc}")
            return {'CANCELLED'}

        try:
            sections = parse_transform_report(text)
            result = apply_transform_sections(
                context,
                sections,
                use_text_start=context.scene.t3tc_settings.import_use_text_start,
            )
        except RuntimeError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        except Exception as exc:
            self.report({'ERROR'}, f"Import failed: {exc}")
            return {'CANCELLED'}

        messages = [
            f"Applied {result['applied_sections']} section(s), "
            f"inserted {result['inserted_keys']} keyframe value(s)."
        ]

        if result['missing_bones']:
            messages.append("Missing bones: " + ", ".join(result['missing_bones'][:8]))
            if len(result['missing_bones']) > 8:
                messages.append(f"(+{len(result['missing_bones']) - 8} more)")

        if result['errors']:
            messages.append("Skipped: " + "; ".join(result['errors'][:3]))
            if len(result['errors']) > 3:
                messages.append(f"(+{len(result['errors']) - 3} more)")

        report_type = {'WARNING'} if (result['missing_bones'] or result['errors']) else {'INFO'}
        self.report(report_type, " ".join(messages))
        return {'FINISHED'}


class T3TC_PT_panel(Panel):
    bl_label = "T3 Transform Converter"
    bl_idname = "T3TC_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Animation"

    def draw(self, context):
        layout = self.layout
        props = context.scene.t3tc_settings

        obj = get_armature(context)

        if obj:
            box = layout.box()
            box.label(text=f"Armature: {obj.name}", icon='ARMATURE_DATA')
            active = obj.data.bones.active
            if active:
                box.label(text=f"Active Bone: {active.name}", icon='BONE_DATA')
        else:
            box = layout.box()
            box.label(text="Select an Armature", icon='ERROR')

        range_box = layout.box()
        range_box.label(text="Frame Range")
        row = range_box.row(align=True)
        row.prop(props, "frame_start")
        row.prop(props, "frame_end")
        range_box.prop(props, "frame_step")
        range_box.operator("t3tc.use_timeline_range", icon='PREVIEW_RANGE')

        layout.prop(props, "bone_scope")
        layout.prop(props, "rotation_source")

        values_box = layout.box()
        values_box.label(text="Values")
        values_box.prop(props, "include_rotation")
        values_box.prop(props, "include_location")
        values_box.prop(props, "include_scale")

        options_box = layout.box()
        options_box.label(text="Output")
        options_box.prop(props, "mirror_x")
        options_box.prop(props, "quaternion_continuity")
        options_box.prop(props, "precision")
        options_box.prop(props, "decimal_separator")
        options_box.prop(props, "language")

        layout.separator()

        normal_box = layout.box()
        normal_box.label(text="Normal Export", icon='GRAPH')
        normal_box.operator("t3tc.analyze", icon='GRAPH')

        text_exists = bpy.data.texts.get(TEXT_BLOCK_NAME) is not None
        col = normal_box.column(align=True)
        col.enabled = text_exists
        col.operator("t3tc.copy_results", icon='COPYDOWN')
        col.operator("t3tc.export_txt", icon='EXPORT')
        col.operator("t3tc.open_text_editor", icon='TEXT')

        reverse_box = layout.box()
        reverse_box.label(text="Reverse Frame Export", icon='FILE_REFRESH')
        reverse_box.label(text="Last frame values become first frame values.")
        reverse_box.operator("t3tc.analyze_reversed", icon='GRAPH')
        # This button analyzes and exports in one operation; no previous analyze is required.
        reverse_box.operator("t3tc.export_reversed_txt", icon='EXPORT')

        reversed_exists = bpy.data.texts.get(REVERSED_TEXT_BLOCK_NAME) is not None
        reversed_col = reverse_box.column(align=True)
        reversed_col.enabled = reversed_exists
        reversed_col.operator("t3tc.copy_reversed_results", icon='COPYDOWN')
        reversed_col.operator("t3tc.open_reversed_text_editor", icon='TEXT')

        layout.separator()
        import_box = layout.box()
        import_box.label(text="Apply Edited Transform TXT", icon='IMPORT')
        import_box.prop(props, "import_use_text_start")
        import_box.operator("t3tc.import_apply_txt", icon='IMPORT')
        import_box.label(text="Bone names come from each section header.")


classes = (
    T3TC_Settings,
    T3TC_OT_use_timeline_range,
    T3TC_OT_analyze,
    T3TC_OT_analyze_reversed,
    T3TC_OT_copy_results,
    T3TC_OT_open_text_editor,
    T3TC_OT_export_txt,
    T3TC_OT_export_reversed_txt,
    T3TC_OT_copy_reversed_results,
    T3TC_OT_open_reversed_text_editor,
    T3TC_OT_import_apply_txt,
    T3TC_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.t3tc_settings = bpy.props.PointerProperty(type=T3TC_Settings)


def unregister():
    del bpy.types.Scene.t3tc_settings

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
