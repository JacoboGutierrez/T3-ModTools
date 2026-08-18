#!/usr/bin/env python3
"""Rigged glTF exporter and T3 ANM helpers for T3-ModTools.

This module intentionally uses only the Python standard library.
"""
from __future__ import annotations

import json
import math
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterable, Optional

NUMBER_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")


def safe_name(value: str, fallback: str = "unnamed") -> str:
    value = value.strip().strip('"').replace("|", "_").replace("/", "_").replace("\\", "_")
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_.")
    return value[:120] or fallback


def quoted_value(text: str, key: str, default: str = "") -> str:
    match = re.search(rf"\b{re.escape(key)}\b\s*[\t ]*\"([^\"]*)\"", text)
    if match:
        return match.group(1)
    match = re.search(rf"\b{re.escape(key)}\b\s*[\t ]*([^\s{{}}]+)", text)
    return match.group(1).strip('"') if match else default


def numeric_value(text: str, key: str, default: float = 0.0) -> float:
    match = re.search(rf"\b{re.escape(key)}\b\s*[\t ]*\"?({NUMBER_RE.pattern})\"?", text)
    return float(match.group(1)) if match else default


def brace_end(text: str, opening_brace: int, limit: Optional[int] = None) -> int:
    depth = 0
    end = len(text) if limit is None else min(limit, len(text))
    in_quote = False
    escaped = False
    for index in range(opening_brace, end):
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


def iter_blocks(text: str, token: str) -> Iterable[tuple[int, int, str]]:
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
        yield match.start(), closing + 1, text[opening + 1 : closing]
        position = closing + 1



def iter_numbered_blocks(text: str, token: str) -> Iterable[tuple[int, int, int, str]]:
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
        yield match.start(), closing + 1, int(match.group(1)), text[opening + 1 : closing]
        position = closing + 1

def data_block(text: str, key: str) -> str:
    match = re.search(rf"(?<![A-Za-z0-9_]){re.escape(key)}\s*\{{", text)
    if not match:
        return ""
    opening = text.find("{", match.start())
    closing = brace_end(text, opening)
    return text[opening + 1 : closing] if closing >= 0 else ""


def float_values(text: str, count: Optional[int] = None) -> list[float]:
    values = [float(item) for item in NUMBER_RE.findall(text)]
    return values[:count] if count is not None else values


def float_tuples(text: str, width: int, count: Optional[int] = None) -> list[tuple[float, ...]]:
    values = float_values(text)
    available = len(values) // width
    if count is not None:
        available = min(available, count)
    return [tuple(values[index * width : (index + 1) * width]) for index in range(available)]


def int_tuples(text: str, width: int, count: Optional[int] = None) -> list[tuple[int, ...]]:
    values = [int(float(item)) for item in NUMBER_RE.findall(text)]
    available = len(values) // width
    if count is not None:
        available = min(available, count)
    return [tuple(values[index * width : (index + 1) * width]) for index in range(available)]


@dataclass
class RigMaterial:
    name: str
    base_texture: str = ""
    shader_type: str = ""


@dataclass
class RigPrimitive:
    name: str
    material: RigMaterial
    vertices: list[tuple[float, float, float]]
    normals: list[tuple[float, float, float]]
    uv0: list[tuple[float, float]]
    triangles: list[tuple[int, int, int]]
    weightmaps: dict[str, list[float]] = field(default_factory=dict)


@dataclass
class BoneDef:
    full_name: str
    short_name: str
    world_matrix: list[list[float]]
    parent_full_name: Optional[str]


@dataclass
class RiggedExportResult:
    source: str
    gltf: Optional[str]
    binary: Optional[str]
    vertices: int = 0
    triangles: int = 0
    bones: int = 0
    weighted_vertices: int = 0
    uv_primitives: int = 0
    textured_materials: int = 0
    winding_corrections: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class AnimationSummary:
    source: str
    name: str
    fps: float
    max_time: int
    frame_count: int
    joint_count: int


def parse_rigged_sca(text: str) -> tuple[list[RigPrimitive], list[BoneDef], str]:
    texture_library = quoted_value(text[:20000], "TextureLibrary", "")
    primitives: list[RigPrimitive] = []
    for mesh_index, (_, _, mesh_block) in enumerate(iter_blocks(text, "cMesh")):
        first_submesh = re.search(r"(?<![A-Za-z0-9_])cSubMesh\s*\{", mesh_block)
        header = mesh_block[: first_submesh.start()] if first_submesh else mesh_block
        mesh_name = quoted_value(header, "Name", f"mesh_{mesh_index}")
        for sub_index, (_, _, submesh) in enumerate(iter_blocks(mesh_block, "cSubMesh")):
            vertex_count = int(numeric_value(submesh, "VertexNumber", 0))
            vertices = [tuple(item) for item in float_tuples(data_block(submesh, "Coordinates"), 3, vertex_count or None)]
            normals = [tuple(item) for item in float_tuples(data_block(submesh, "Normals"), 3, vertex_count or None)]
            uv0 = [tuple(item) for item in float_tuples(data_block(submesh, "Textcoord0"), 2, vertex_count or None)]
            index_count = int(numeric_value(submesh, "IndexNumber", 0))
            triangles = [tuple(item) for item in int_tuples(data_block(submesh, "Indices"), 3, (index_count // 3) if index_count else None)]
            if not vertices or not triangles:
                continue
            shader_block = next(iter_blocks(submesh, "Shader"), None)
            shader_text = shader_block[2] if shader_block else submesh
            base_texture = quoted_value(shader_text, "BaseTexture", "")
            shader_type = quoted_value(shader_text, "Type", "")
            material = RigMaterial(
                name=safe_name(f"{PurePosixPath(base_texture).stem or 'material'}_{mesh_index}_{sub_index}", "material"),
                base_texture=base_texture,
                shader_type=shader_type,
            )
            weightmaps: dict[str, list[float]] = {}
            for _, _, weightmap in iter_blocks(submesh, "Weightmap"):
                bone_name = quoted_value(weightmap, "BoneName", "")
                if not bone_name:
                    continue
                weights = float_values(data_block(weightmap, "Weights"), len(vertices))
                if len(weights) < len(vertices):
                    weights.extend([0.0] * (len(vertices) - len(weights)))
                weightmaps[bone_name] = weights
            primitives.append(RigPrimitive(
                name=safe_name(f"{mesh_name}_{quoted_value(submesh, 'Name', str(sub_index))}", f"primitive_{len(primitives)}"),
                material=material,
                vertices=vertices,
                normals=normals,
                uv0=uv0,
                triangles=triangles,
                weightmaps=weightmaps,
            ))

    raw_bones: list[tuple[str, list[list[float]]]] = []
    for _, _, bone_block in iter_blocks(text, "cBone"):
        full_name = quoted_value(bone_block, "Name", "")
        values = float_values(data_block(bone_block, "Matrix"), 16)
        if not full_name or len(values) != 16:
            continue
        matrix = [values[row * 4 : row * 4 + 4] for row in range(4)]
        raw_bones.append((full_name, matrix))
    names = {name for name, _ in raw_bones}
    bones: list[BoneDef] = []
    for full_name, matrix in raw_bones:
        parent = full_name.rsplit("|", 1)[0] if "|" in full_name else ""
        if parent not in names:
            parent = None
        short = full_name.rsplit("|", 1)[-1] or "bone"
        bones.append(BoneDef(full_name, short, matrix, parent))
    return primitives, bones, texture_library


def parse_animation_summary(text: str, source: str) -> AnimationSummary:
    animation_block = next(iter_blocks(text, "Animation"), None)
    body = animation_block[2] if animation_block else text
    name = quoted_value(body, "Name", PurePosixPath(source).stem)
    fps = numeric_value(body, "Fps", 0.0)
    max_time = int(numeric_value(body, "MaxTimeValue", 0))
    times = list(iter_numbered_blocks(body, "Time"))
    joint_names: set[str] = set()
    for _, _, _, time_block in times[:1]:
        for _, _, joint in iter_blocks(time_block, "Joint"):
            joint_name = quoted_value(joint, "Name", "")
            if joint_name:
                joint_names.add(joint_name)
    return AnimationSummary(source, name, fps, max_time, len(times), len(joint_names))


def mat_identity() -> list[list[float]]:
    return [[1.0 if row == col else 0.0 for col in range(4)] for row in range(4)]


def mat_mul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [[sum(a[row][k] * b[k][col] for k in range(4)) for col in range(4)] for row in range(4)]


def mat_transpose(matrix: list[list[float]]) -> list[list[float]]:
    return [[matrix[col][row] for col in range(4)] for row in range(4)]


def mat_inverse(matrix: list[list[float]]) -> list[list[float]]:
    augmented = [list(row) + identity_row for row, identity_row in zip(matrix, mat_identity())]
    for column in range(4):
        pivot = max(range(column, 4), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ValueError("Singular bind matrix")
        if pivot != column:
            augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        augmented[column] = [value / scale for value in augmented[column]]
        for row in range(4):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor:
                augmented[row] = [augmented[row][index] - factor * augmented[column][index] for index in range(8)]
    return [row[4:] for row in augmented]


def determinant3(matrix: list[list[float]]) -> float:
    return (
        matrix[0][0] * (matrix[1][1] * matrix[2][2] - matrix[1][2] * matrix[2][1])
        - matrix[0][1] * (matrix[1][0] * matrix[2][2] - matrix[1][2] * matrix[2][0])
        + matrix[0][2] * (matrix[1][0] * matrix[2][1] - matrix[1][1] * matrix[2][0])
    )


def quaternion_from_rotation(rotation: list[list[float]]) -> tuple[float, float, float, float]:
    trace = rotation[0][0] + rotation[1][1] + rotation[2][2]
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * s
        x = (rotation[2][1] - rotation[1][2]) / s
        y = (rotation[0][2] - rotation[2][0]) / s
        z = (rotation[1][0] - rotation[0][1]) / s
    elif rotation[0][0] > rotation[1][1] and rotation[0][0] > rotation[2][2]:
        s = math.sqrt(max(0.0, 1.0 + rotation[0][0] - rotation[1][1] - rotation[2][2])) * 2.0
        w = (rotation[2][1] - rotation[1][2]) / s if s else 1.0
        x = 0.25 * s
        y = (rotation[0][1] + rotation[1][0]) / s if s else 0.0
        z = (rotation[0][2] + rotation[2][0]) / s if s else 0.0
    elif rotation[1][1] > rotation[2][2]:
        s = math.sqrt(max(0.0, 1.0 + rotation[1][1] - rotation[0][0] - rotation[2][2])) * 2.0
        w = (rotation[0][2] - rotation[2][0]) / s if s else 1.0
        x = (rotation[0][1] + rotation[1][0]) / s if s else 0.0
        y = 0.25 * s
        z = (rotation[1][2] + rotation[2][1]) / s if s else 0.0
    else:
        s = math.sqrt(max(0.0, 1.0 + rotation[2][2] - rotation[0][0] - rotation[1][1])) * 2.0
        w = (rotation[1][0] - rotation[0][1]) / s if s else 1.0
        x = (rotation[0][2] + rotation[2][0]) / s if s else 0.0
        y = (rotation[1][2] + rotation[2][1]) / s if s else 0.0
        z = 0.25 * s
    length = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    return x / length, y / length, z / length, w / length


def decompose_column_matrix(matrix: list[list[float]]) -> tuple[list[float], list[float], list[float]]:
    translation = [matrix[0][3], matrix[1][3], matrix[2][3]]
    columns = [[matrix[row][column] for row in range(3)] for column in range(3)]
    scales = [math.sqrt(sum(value * value for value in column)) or 1.0 for column in columns]
    rotation = [[matrix[row][column] / scales[column] for column in range(3)] for row in range(3)]
    if determinant3(rotation) < 0.0:
        largest = max(range(3), key=lambda index: abs(scales[index]))
        scales[largest] *= -1.0
        for row in range(3):
            rotation[row][largest] *= -1.0
    quaternion = list(quaternion_from_rotation(rotation))
    return translation, quaternion, scales


def flatten_column_major(matrix: list[list[float]]) -> list[float]:
    return [matrix[row][column] for column in range(4) for row in range(4)]


class BinaryBuilder:
    COMPONENT_FLOAT = 5126
    COMPONENT_U16 = 5123
    COMPONENT_U32 = 5125
    TARGET_ARRAY_BUFFER = 34962
    TARGET_ELEMENT_ARRAY_BUFFER = 34963

    def __init__(self) -> None:
        self.data = bytearray()
        self.buffer_views: list[dict[str, object]] = []
        self.accessors: list[dict[str, object]] = []

    def align(self, alignment: int = 4) -> None:
        while len(self.data) % alignment:
            self.data.append(0)

    def add_bytes(self, payload: bytes, target: Optional[int] = None, byte_stride: Optional[int] = None) -> int:
        self.align(4)
        offset = len(self.data)
        self.data.extend(payload)
        view: dict[str, object] = {"buffer": 0, "byteOffset": offset, "byteLength": len(payload)}
        if target is not None:
            view["target"] = target
        if byte_stride is not None:
            view["byteStride"] = byte_stride
        self.buffer_views.append(view)
        return len(self.buffer_views) - 1

    def add_accessor(
        self,
        payload: bytes,
        component_type: int,
        type_name: str,
        count: int,
        target: Optional[int] = None,
        minimum: Optional[list[float]] = None,
        maximum: Optional[list[float]] = None,
        normalized: bool = False,
    ) -> int:
        view_index = self.add_bytes(payload, target=target)
        accessor: dict[str, object] = {
            "bufferView": view_index,
            "componentType": component_type,
            "count": count,
            "type": type_name,
        }
        if minimum is not None:
            accessor["min"] = minimum
        if maximum is not None:
            accessor["max"] = maximum
        if normalized:
            accessor["normalized"] = True
        self.accessors.append(accessor)
        return len(self.accessors) - 1


def pack_floats(values: Iterable[float]) -> bytes:
    values_list = list(values)
    return struct.pack("<" + "f" * len(values_list), *values_list)


def pack_u16(values: Iterable[int]) -> bytes:
    values_list = list(values)
    return struct.pack("<" + "H" * len(values_list), *values_list)


def pack_u32(values: Iterable[int]) -> bytes:
    values_list = list(values)
    return struct.pack("<" + "I" * len(values_list), *values_list)


def build_vertex_influences(
    primitive: RigPrimitive,
    bone_indices: dict[str, int],
    fallback_bone: int,
) -> tuple[list[int], list[float], int]:
    joints: list[int] = []
    weights: list[float] = []
    weighted_vertices = 0
    for vertex_index in range(len(primitive.vertices)):
        influences: list[tuple[float, int]] = []
        for bone_name, values in primitive.weightmaps.items():
            weight = values[vertex_index] if vertex_index < len(values) else 0.0
            if weight > 1e-8 and bone_name in bone_indices:
                influences.append((weight, bone_indices[bone_name]))
        influences.sort(reverse=True)
        influences = influences[:4]
        total = sum(weight for weight, _ in influences)
        if total <= 1e-8:
            influences = [(1.0, fallback_bone)]
            total = 1.0
        else:
            weighted_vertices += 1
        normalized = [(weight / total, joint) for weight, joint in influences]
        while len(normalized) < 4:
            normalized.append((0.0, fallback_bone))
        for weight, joint in normalized:
            joints.append(joint)
            weights.append(weight)
    return joints, weights, weighted_vertices


def _sub3(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross3(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot3(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def orient_triangle_to_vertex_normals(
    triangle: tuple[int, int, int],
    vertices: list[tuple[float, float, float]],
    normals: list[tuple[float, float, float]],
) -> tuple[tuple[int, int, int], bool]:
    """Keep source winding unless it conflicts with the supplied vertex normals.

    The global X mirror is represented by a negative-determinant glTF node transform.
    glTF defines winding from that determinant, so triangle indices must not be reversed
    again merely because the parent node mirrors X.
    """
    a, b, c = triangle
    if min(a, b, c) < 0 or max(a, b, c) >= len(vertices):
        return triangle, False
    if len(normals) != len(vertices):
        return triangle, False
    edge_ab = _sub3(vertices[b], vertices[a])
    edge_ac = _sub3(vertices[c], vertices[a])
    face_normal = _cross3(edge_ab, edge_ac)
    average_normal = (
        normals[a][0] + normals[b][0] + normals[c][0],
        normals[a][1] + normals[b][1] + normals[c][1],
        normals[a][2] + normals[b][2] + normals[c][2],
    )
    # Degenerate triangles or zero-length normals do not provide a reliable direction.
    if _dot3(face_normal, face_normal) <= 1e-20 or _dot3(average_normal, average_normal) <= 1e-20:
        return triangle, False
    if _dot3(face_normal, average_normal) < 0.0:
        return (a, c, b), True
    return triangle, False


def export_rigged_gltf(
    text: str,
    source: str,
    output_dir: Path,
    texture_mapping: Optional[dict[str, str]] = None,
    flip_v: bool = False,
    z_up: bool = False,
) -> RiggedExportResult:
    warnings: list[str] = []
    primitives, bones, _ = parse_rigged_sca(text)
    if not primitives:
        return RiggedExportResult(source, None, None, warnings=["No triangulated mesh data was found."])
    if not bones:
        return RiggedExportResult(source, None, None, warnings=["No cBone skeleton was found."])
    if not any(primitive.weightmaps for primitive in primitives):
        return RiggedExportResult(source, None, None, warnings=["No Weightmap skin data was found."])

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = safe_name(PurePosixPath(source).stem, "model") + "_rigged"
    gltf_path = output_dir / f"{stem}.gltf"
    bin_path = output_dir / f"{stem}.bin"

    builder = BinaryBuilder()
    bone_index_by_full = {bone.full_name: index for index, bone in enumerate(bones)}
    parent_index: list[Optional[int]] = [bone_index_by_full.get(bone.parent_full_name) for bone in bones]
    root_bones = [index for index, parent in enumerate(parent_index) if parent is None]
    fallback_bone = root_bones[0] if root_bones else 0

    # Nodes 0..len(bones)-1 are joints. Their local bind transforms are decomposed to TRS.
    nodes: list[dict[str, object]] = []
    for index, bone in enumerate(bones):
        local_row = bone.world_matrix
        parent = parent_index[index]
        if parent is not None:
            local_row = mat_mul(bone.world_matrix, mat_inverse(bones[parent].world_matrix))
        local_column = mat_transpose(local_row)
        translation, rotation, scale = decompose_column_matrix(local_column)
        node: dict[str, object] = {
            "name": safe_name(bone.short_name, f"bone_{index}"),
            "translation": translation,
            "rotation": rotation,
            "scale": scale,
            "extras": {"t3_full_name": bone.full_name},
        }
        child_indices = [child for child, parent_value in enumerate(parent_index) if parent_value == index]
        if child_indices:
            node["children"] = child_indices
        nodes.append(node)

    inverse_bind_values: list[float] = []
    for bone in bones:
        inverse_column = mat_transpose(mat_inverse(bone.world_matrix))
        inverse_bind_values.extend(flatten_column_major(inverse_column))
    inverse_bind_accessor = builder.add_accessor(
        pack_floats(inverse_bind_values),
        BinaryBuilder.COMPONENT_FLOAT,
        "MAT4",
        len(bones),
    )

    material_indices: dict[str, int] = {}
    materials: list[dict[str, object]] = []
    images: list[dict[str, object]] = []
    textures: list[dict[str, object]] = []
    image_index_by_uri: dict[str, int] = {}
    texture_index_by_uri: dict[str, int] = {}
    mesh_primitives: list[dict[str, object]] = []
    total_vertices = 0
    total_triangles = 0
    total_weighted = 0
    uv_primitive_count = 0
    textured_material_count = 0
    winding_corrections = 0
    texture_mapping = texture_mapping or {}

    for primitive_index, primitive in enumerate(primitives):
        positions_flat = [value for vertex in primitive.vertices for value in vertex]
        mins = [min(vertex[axis] for vertex in primitive.vertices) for axis in range(3)]
        maxs = [max(vertex[axis] for vertex in primitive.vertices) for axis in range(3)]
        position_accessor = builder.add_accessor(
            pack_floats(positions_flat), BinaryBuilder.COMPONENT_FLOAT, "VEC3", len(primitive.vertices),
            target=BinaryBuilder.TARGET_ARRAY_BUFFER, minimum=mins, maximum=maxs,
        )
        attributes: dict[str, int] = {"POSITION": position_accessor}
        if len(primitive.normals) == len(primitive.vertices):
            normal_accessor = builder.add_accessor(
                pack_floats(value for normal in primitive.normals for value in normal),
                BinaryBuilder.COMPONENT_FLOAT, "VEC3", len(primitive.normals),
                target=BinaryBuilder.TARGET_ARRAY_BUFFER,
            )
            attributes["NORMAL"] = normal_accessor
        if len(primitive.uv0) == len(primitive.vertices):
            uv_values: list[float] = []
            for u, v in primitive.uv0:
                uv_values.extend((u, 1.0 - v if flip_v else v))
            uv_accessor = builder.add_accessor(
                pack_floats(uv_values), BinaryBuilder.COMPONENT_FLOAT, "VEC2", len(primitive.uv0),
                target=BinaryBuilder.TARGET_ARRAY_BUFFER,
            )
            attributes["TEXCOORD_0"] = uv_accessor
            uv_primitive_count += 1
        else:
            warnings.append(
                f"{primitive.name}: UV0 count {len(primitive.uv0)} does not match "
                f"vertex count {len(primitive.vertices)}; TEXCOORD_0 was not written."
            )

        joints, weights, weighted = build_vertex_influences(primitive, bone_index_by_full, fallback_bone)
        total_weighted += weighted
        joint_accessor = builder.add_accessor(
            pack_u16(joints), BinaryBuilder.COMPONENT_U16, "VEC4", len(primitive.vertices),
            target=BinaryBuilder.TARGET_ARRAY_BUFFER,
        )
        weight_accessor = builder.add_accessor(
            pack_floats(weights), BinaryBuilder.COMPONENT_FLOAT, "VEC4", len(primitive.vertices),
            target=BinaryBuilder.TARGET_ARRAY_BUFFER,
        )
        attributes["JOINTS_0"] = joint_accessor
        attributes["WEIGHTS_0"] = weight_accessor

        # Keep glTF source winding. The negative-determinant parent transform already
        # defines mirrored primitives as clockwise according to the glTF 2.0 specification.
        # Only repair individual source triangles that conflict with their vertex normals.
        indices: list[int] = []
        primitive_winding_corrections = 0
        for triangle in primitive.triangles:
            a, b, c = triangle
            if min(a, b, c) < 0 or max(a, b, c) >= len(primitive.vertices):
                continue
            oriented, corrected = orient_triangle_to_vertex_normals(
                triangle, primitive.vertices, primitive.normals
            )
            indices.extend(oriented)
            primitive_winding_corrections += int(corrected)
        winding_corrections += primitive_winding_corrections
        index_accessor = builder.add_accessor(
            pack_u32(indices), BinaryBuilder.COMPONENT_U32, "SCALAR", len(indices),
            target=BinaryBuilder.TARGET_ELEMENT_ARRAY_BUFFER,
            minimum=[min(indices)] if indices else [0], maximum=[max(indices)] if indices else [0],
        )

        material_key = primitive.material.name
        if material_key not in material_indices:
            extras: dict[str, object] = {
                "t3_shader_type": primitive.material.shader_type,
                "t3_base_texture": primitive.material.base_texture,
            }
            pbr: dict[str, object] = {
                "baseColorFactor": [1.0, 1.0, 1.0, 1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 1.0,
            }
            mapped_texture = texture_mapping.get(primitive.material.base_texture.lower()) if primitive.material.base_texture else None
            if mapped_texture:
                texture_uri = mapped_texture.replace("\\", "/")
                extras["copied_texture"] = texture_uri
                extension = PurePosixPath(texture_uri).suffix.lower()
                if extension in {".png", ".jpg", ".jpeg"}:
                    if texture_uri not in image_index_by_uri:
                        image: dict[str, object] = {"uri": texture_uri}
                        if extension == ".png":
                            image["mimeType"] = "image/png"
                        elif extension in {".jpg", ".jpeg"}:
                            image["mimeType"] = "image/jpeg"
                        images.append(image)
                        image_index_by_uri[texture_uri] = len(images) - 1
                    if texture_uri not in texture_index_by_uri:
                        textures.append({
                            "name": safe_name(PurePosixPath(texture_uri).stem, "texture"),
                            "sampler": 0,
                            "source": image_index_by_uri[texture_uri],
                        })
                        texture_index_by_uri[texture_uri] = len(textures) - 1
                    pbr["baseColorTexture"] = {
                        "index": texture_index_by_uri[texture_uri],
                        "texCoord": 0,
                    }
                    extras["gltf_uv_attribute"] = "TEXCOORD_0"
                    textured_material_count += 1
                else:
                    warnings.append(
                        f"{primitive.material.name}: texture {texture_uri} was copied but could not be "
                        "linked as a core glTF image. Convert it to PNG or JPEG."
                    )
            materials.append({
                "name": primitive.material.name,
                "pbrMetallicRoughness": pbr,
                "doubleSided": False,
                "alphaMode": "OPAQUE",
                "extras": extras,
            })
            material_indices[material_key] = len(materials) - 1

        mesh_primitives.append({
            "attributes": attributes,
            "indices": index_accessor,
            "material": material_indices[material_key],
            "mode": 4,
            "extras": {"t3_submesh": primitive.name},
        })
        total_vertices += len(primitive.vertices)
        total_triangles += len(indices) // 3

    mesh_index = 0
    mesh_node_index = len(nodes)
    nodes.append({"name": stem, "mesh": mesh_index, "skin": 0})
    transform_root_index = len(nodes)
    if z_up:
        # Parent transform equivalent to OBJ mapping: (x, y, z) -> (-x, -z, y).
        # glTF matrices are stored column-major.
        transform_node: dict[str, object] = {
            "name": "T3_Global_Mirror_X_Z_Up",
            "matrix": [
                -1.0, 0.0, 0.0, 0.0,
                 0.0, 0.0, 1.0, 0.0,
                 0.0, -1.0, 0.0, 0.0,
                 0.0, 0.0, 0.0, 1.0,
            ],
            "children": [mesh_node_index] + root_bones,
            "extras": {
                "description": "Global X mirror plus optional T3 Y-up to Blender Z-up conversion."
            },
        }
    else:
        transform_node = {
            "name": "T3_Global_Mirror_X",
            "scale": [-1.0, 1.0, 1.0],
            "children": [mesh_node_index] + root_bones,
            "extras": {"description": "Global X mirror requested by T3-ModTools."},
        }
    nodes.append(transform_node)

    gltf: dict[str, object] = {
        "asset": {"version": "2.0", "generator": "T3-ModTools rig exporter"},
        "scene": 0,
        "scenes": [{"name": "Scene", "nodes": [transform_root_index]}],
        "nodes": nodes,
        "meshes": [{"name": stem, "primitives": mesh_primitives}],
        "skins": [{
            "name": f"{stem}_skin",
            "inverseBindMatrices": inverse_bind_accessor,
            "joints": list(range(len(bones))),
            "skeleton": root_bones[0] if root_bones else 0,
        }],
        "materials": materials,
        "buffers": [{"uri": bin_path.name, "byteLength": len(builder.data)}],
        "bufferViews": builder.buffer_views,
        "accessors": builder.accessors,
        "extras": {
            "source": source,
            "global_mirror_x": True,
            "native_t3_orientation": not z_up,
            "z_up_conversion": z_up,
            "texture_note": "Compatible DDS/TGA base textures are converted to PNG and connected through baseColorTexture using TEXCOORD_0.",
            "uv_v_flipped": flip_v,
            "winding_note": "The negative-determinant mirror node defines clockwise glTF winding; indices are not globally reversed. Source triangles conflicting with vertex normals are repaired individually.",
            "winding_corrections": winding_corrections,
        },
    }
    if textures:
        gltf["samplers"] = [{
            "magFilter": 9729,
            "minFilter": 9987,
            "wrapS": 10497,
            "wrapT": 10497,
        }]
        gltf["images"] = images
        gltf["textures"] = textures

    bin_path.write_bytes(bytes(builder.data))
    gltf_path.write_text(json.dumps(gltf, indent=2, ensure_ascii=False), encoding="utf-8")
    return RiggedExportResult(
        source=source,
        gltf=str(gltf_path),
        binary=str(bin_path),
        vertices=total_vertices,
        triangles=total_triangles,
        bones=len(bones),
        weighted_vertices=total_weighted,
        uv_primitives=uv_primitive_count,
        textured_materials=textured_material_count,
        winding_corrections=winding_corrections,
        warnings=warnings,
    )
