"""Plan the T3 archive loader in an exclusively owned PE section.

Zero-filled bytes in an existing section may belong to live engine globals.  This
module never treats them as code or data caves: its trampoline and constant
strings are stored in a new read/execute section appended to the original file.
The caller applies every planned write through its patch-ownership checks.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Callable, Optional


_SECTION_NAME = b".t3ldr"
_CODE_SIZE = 64
_UINT32_MAX = 0xFFFFFFFF
_IMAGE_SCN_CNT_CODE = 0x00000020
_IMAGE_SCN_MEM_EXECUTE = 0x20000000
_IMAGE_SCN_MEM_READ = 0x40000000


@dataclass(frozen=True)
class LoaderPatchPlan:
    writes: list[tuple[int, bytes, str]]
    final_size: int
    code_offset: int
    data_offset: int
    entry_offset: int
    entry_original: bytes
    extension_offset: Optional[int] = None
    extension_va: Optional[int] = None


@dataclass(frozen=True)
class _Section:
    name: bytes
    virtual_size: int
    rva: int
    raw_size: int
    raw_offset: int
    characteristics: int

    @property
    def mapped_end(self) -> int:
        return self.rva + max(self.virtual_size, self.raw_size)


def _unsupported(reason: str) -> ValueError:
    return ValueError(f"Unsupported T3.exe: {reason}")


def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) & ~(alignment - 1)


def _unique(data: bytes, pattern: bytes, start: int, end: int, label: str) -> int:
    offset = data.find(pattern, start, end)
    if offset < 0 or data.find(pattern, offset + 1, end) >= 0:
        raise _unsupported(f"expected exactly one {label}.")
    return offset


def _rel32(target: int, next_instruction: int) -> bytes:
    displacement = target - next_instruction
    if not -(1 << 31) <= displacement < (1 << 31):
        raise _unsupported("loader branch exceeds the signed 32-bit range.")
    return struct.pack("<i", displacement)


def build_loader_patch(
    original: bytes, pack_path: bytes, marker: bytes,
    *, extension: Optional[Callable[[int], bytes]] = None,
) -> LoaderPatchPlan:
    """Return a checked write plan without modifying or writing any file.

    ``pack_path`` and ``marker`` are individually NUL-terminated byte strings.
    The final file must first be zero-extended to ``final_size`` by the caller.
    Existing section contents remain untouched except for the six-byte archive
    loader entry hook; no original globals or executable padding are reused.
    """
    for label, value in (("pack path", pack_path), ("loader marker", marker)):
        if not isinstance(value, bytes) or len(value) < 2 or value[-1:] != b"\0":
            raise ValueError(f"The {label} must be a nonempty NUL-terminated byte string.")
        if b"\0" in value[:-1]:
            raise ValueError(f"The {label} must not contain embedded NUL bytes.")
    if len(original) < 0x40 or original[:2] != b"MZ":
        raise _unsupported("DOS header is missing or truncated.")
    pe_offset = struct.unpack_from("<I", original, 0x3C)[0]
    if pe_offset < 0x40 or pe_offset + 24 > len(original):
        raise _unsupported("PE header is outside the file.")
    if original[pe_offset:pe_offset + 4] != b"PE\0\0":
        raise _unsupported("PE signature is missing.")
    machine, section_count = struct.unpack_from("<HH", original, pe_offset + 4)
    optional_size = struct.unpack_from("<H", original, pe_offset + 20)[0]
    optional_offset = pe_offset + 24
    if machine != 0x14C or not 1 <= section_count < 96:
        raise _unsupported("expected an x86 image with room for another section.")
    if optional_size < 96 or optional_offset + optional_size > len(original):
        raise _unsupported("optional header is missing or truncated.")
    if struct.unpack_from("<H", original, optional_offset)[0] != 0x10B:
        raise _unsupported("expected a PE32 optional header.")

    image_base = struct.unpack_from("<I", original, optional_offset + 28)[0]
    section_alignment, file_alignment = struct.unpack_from("<II", original, optional_offset + 32)
    size_of_image, size_of_headers = struct.unpack_from("<II", original, optional_offset + 56)
    directory_count = struct.unpack_from("<I", original, optional_offset + 92)[0]
    if directory_count > (optional_size - 96) // 8:
        raise _unsupported("data directories exceed the optional header.")
    dll_characteristics = struct.unpack_from("<H", original, optional_offset + 70)[0]
    if dll_characteristics & 0x0040:
        raise _unsupported("ASLR images require relocation-aware loader generation.")
    if directory_count > 5:
        relocation_rva, relocation_size = struct.unpack_from("<II", original, optional_offset + 96 + 5 * 8)
        if relocation_rva or relocation_size:
            # New absolute operands need relocations, and a relocation for the
            # replaced PUSH operand would corrupt the entry JMP displacement.
            raise _unsupported("relocatable images require relocation-aware loader generation.")
    for alignment in (section_alignment, file_alignment):
        if not alignment or alignment & (alignment - 1):
            raise _unsupported("PE alignments must be positive powers of two.")
    # Sub-page images require additional PE loader rules that this patcher does
    # not implement. The supported T3 image uses 0x1000 for both alignments.
    if not 0x200 <= file_alignment <= 0x10000 or section_alignment < 0x1000:
        raise _unsupported("PE alignment values are outside the supported range.")
    if section_alignment < file_alignment:
        raise _unsupported("section alignment is smaller than file alignment.")
    if not size_of_headers or size_of_headers % file_alignment or size_of_headers > len(original):
        raise _unsupported("SizeOfHeaders is invalid.")
    if directory_count > 4:
        certificate_offset, certificate_size = struct.unpack_from("<II", original, optional_offset + 96 + 4 * 8)
        if certificate_offset or certificate_size:
            raise _unsupported("signed images cannot be extended without invalidating their certificate.")

    section_table = optional_offset + optional_size
    new_header = section_table + section_count * 40
    if new_header + 40 > size_of_headers:
        raise _unsupported("there is no spare section-header slot.")
    if any(original[new_header:new_header + 40]):
        raise _unsupported("the next section-header slot is not empty.")
    sections: list[_Section] = []
    for index in range(section_count):
        offset = section_table + index * 40
        name = original[offset:offset + 8].rstrip(b"\0")
        virtual_size, rva, raw_size, raw_offset = struct.unpack_from("<IIII", original, offset + 8)
        characteristics = struct.unpack_from("<I", original, offset + 36)[0]
        if name.lower() == _SECTION_NAME:
            raise _unsupported("a generated loader section already exists; use the pristine executable.")
        if rva % section_alignment or rva < _align(size_of_headers, section_alignment):
            raise _unsupported("a section has an invalid virtual address.")
        if raw_size and (
            raw_offset < size_of_headers or raw_offset % file_alignment
            or raw_size % file_alignment or raw_offset + raw_size > len(original)
        ):
            raise _unsupported("a section has invalid raw-file bounds or alignment.")
        section = _Section(name, virtual_size, rva, raw_size, raw_offset, characteristics)
        if section.mapped_end > _UINT32_MAX:
            raise _unsupported("a section exceeds the 32-bit virtual address space.")
        sections.append(section)
    raw_sections = sorted((s for s in sections if s.raw_size), key=lambda s: s.raw_offset)
    if not raw_sections or new_header + 40 > raw_sections[0].raw_offset:
        raise _unsupported("the new section header would overlap section data.")
    for previous, current in zip(raw_sections, raw_sections[1:]):
        if previous.raw_offset + previous.raw_size > current.raw_offset:
            raise _unsupported("existing section raw-file ranges overlap.")
    virtual_sections = sorted(sections, key=lambda s: s.rva)
    for previous, current in zip(virtual_sections, virtual_sections[1:]):
        if _align(previous.mapped_end, section_alignment) > current.rva:
            raise _unsupported("existing section virtual ranges overlap.")
    last_virtual_end = max(s.mapped_end for s in sections)
    if _align(size_of_image, section_alignment) < _align(last_virtual_end, section_alignment):
        raise _unsupported("SizeOfImage does not contain all existing sections.")
    if image_base + _align(last_virtual_end, section_alignment) > _UINT32_MAX:
        raise _unsupported("the image does not fit in the 32-bit address space.")
    for index in range(directory_count):
        if index == 4:  # The certificate directory uses file offsets, not RVAs.
            continue
        rva, size = struct.unpack_from("<II", original, optional_offset + 96 + index * 8)
        if size and rva < new_header + 40 and rva + size > new_header:
            raise _unsupported("a data directory occupies the spare section-header slot.")

    def file_to_va(offset: int, length: int = 1) -> int:
        for section in sections:
            if section.raw_offset <= offset and offset + length <= section.raw_offset + section.raw_size:
                return image_base + section.rva + offset - section.raw_offset
        raise _unsupported("a loader anchor is outside mapped section data.")

    text_sections = [s for s in sections if s.name == b".text"]
    if len(text_sections) != 1 or not text_sections[0].characteristics & _IMAGE_SCN_MEM_EXECUTE:
        raise _unsupported("expected one executable .text section.")
    text = text_sections[0]
    language_string = b"Language.cod\0"
    language_offset = _unique(original, language_string, 0, len(original), "Language.cod string")
    language_va = file_to_va(language_offset, len(language_string))
    entry_original = b"\x53\x68" + struct.pack("<I", language_va)
    entry_offset = _unique(
        original, entry_original, text.raw_offset, text.raw_offset + text.raw_size,
        "package-loading sequence",
    )
    call_offset = entry_offset + len(entry_original)
    if call_offset + 5 > text.raw_offset + text.raw_size or original[call_offset] != 0xE8:
        raise _unsupported("AddPack CALL is not in the expected location.")
    call_va = file_to_va(call_offset, 5)
    add_pack_va = call_va + 5 + struct.unpack_from("<i", original, call_offset + 1)[0]
    if not image_base + text.rva <= add_pack_va < image_base + text.rva + text.raw_size:
        raise _unsupported("AddPack CALL target is outside the executable .text section.")

    payload_size = _CODE_SIZE + len(pack_path) + len(marker)
    raw_offset = _align(len(original), file_alignment)
    section_rva = _align(max(last_virtual_end, size_of_image), section_alignment)
    extension_relative = _align(payload_size, 16)
    extension_va = image_base + section_rva + extension_relative
    extension_bytes = extension(extension_va) if extension is not None else b''
    if not isinstance(extension_bytes, bytes) or len(extension_bytes) > 1024*1024:
        raise _unsupported("invalid or oversized loader extension.")
    if extension_bytes:
        payload_size = extension_relative + len(extension_bytes)
    raw_size = _align(payload_size, file_alignment)
    final_size = raw_offset + raw_size
    final_image_size = _align(section_rva + max(payload_size, raw_size), section_alignment)
    original_code_size = struct.unpack_from("<I", original, optional_offset + 4)[0]
    if (
        final_size > _UINT32_MAX or final_image_size > _UINT32_MAX
        or image_base + final_image_size > _UINT32_MAX
        or original_code_size + raw_size > _UINT32_MAX
    ):
        raise _unsupported("the generated section exceeds PE32 size limits.")
    code_va = image_base + section_rva
    data_va = code_va + _CODE_SIZE
    code = bytearray()
    code += b"\x68\0\0\0\0\x68" + struct.pack("<I", data_va)
    code += b"\xE8" + _rel32(add_pack_va, code_va + len(code) + 5)
    code += b"\x83\xC4\x08" + entry_original
    code += b"\xE9" + _rel32(call_va, code_va + len(code) + 5)
    if len(code) > _CODE_SIZE:
        raise _unsupported("the loader trampoline exceeds its reserved space.")
    code += b"\x90" * (_CODE_SIZE - len(code))
    entry_hook = b"\xE9" + _rel32(code_va, file_to_va(entry_offset, 6) + 5) + b"\x90"
    section_header = struct.pack(
        "<8sIIIIIIHHI", _SECTION_NAME, payload_size, section_rva, raw_size, raw_offset,
        0, 0, 0, 0, _IMAGE_SCN_CNT_CODE | _IMAGE_SCN_MEM_EXECUTE | _IMAGE_SCN_MEM_READ,
    )
    # This section is classified as code, including its read-only constants;
    # SizeOfInitializedData is therefore left untouched. Existing aggregate
    # header values are preserved rather than recomputed from legacy sections.
    writes = [
        (pe_offset + 6, struct.pack("<H", section_count + 1), "T3-ModTools loader:section count"),
        (optional_offset + 4, struct.pack("<I", original_code_size + raw_size), "T3-ModTools loader:code size"),
        (optional_offset + 56, struct.pack("<I", final_image_size), "T3-ModTools loader:image size"),
        # Normal user-mode executables do not require a PE checksum. Clear any
        # previous checksum rather than retaining one for different bytes.
        (optional_offset + 64, b"\0" * 4, "T3-ModTools loader:checksum"),
        (new_header, section_header, "T3-ModTools loader:section header"),
        (entry_offset, entry_hook, "T3-ModTools loader:entry"),
        (raw_offset, bytes(code), "T3-ModTools loader:code"),
        (raw_offset + _CODE_SIZE, pack_path + marker, "T3-ModTools loader:data"),
    ]
    if extension_bytes:
        writes.append((raw_offset + extension_relative, extension_bytes, "T3-ModTools ANM:compositor"))
    return LoaderPatchPlan(
        writes=writes, final_size=final_size, code_offset=raw_offset,
        data_offset=raw_offset + _CODE_SIZE, entry_offset=entry_offset,
        entry_original=entry_original,
        extension_offset=raw_offset + extension_relative if extension_bytes else None,
        extension_va=extension_va if extension_bytes else None,
    )
