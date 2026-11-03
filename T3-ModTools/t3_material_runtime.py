"""Opt-in model transparency for the fingerprinted T3 renderer.

T3Transparency is an extension token (0..255 transparency). ShaderLoader stores
tagged opacity in the three padding bytes after cShaderData.basetexture_uvset.
Color belongs to native shadow rendering and must never hold persistent data.
The draw wrapper saves/restores all modified D3D state. No global render patch.
"""
import hashlib
import re
import struct

SHA256 = '52f68d5df4912aba662f0371a06ae0b1ec447ef4b7338460224b20904eb0f061'
PARSER = 0x554FFC
DRAW_SITES = (0x517F53, 0x5182CE, 0x5184DB)  # BASE, DIFFUSE, DIFFUSE_SPECULAR
TAG = 0x54330000
UV_INIT = 0x554FE0
METADATA_OFFSET = 12  # native UV byte, opacity byte, 16-bit extension tag
DRAW_OFFSET = 0x200
# PDB cShaderData: Shader=0, ShaderSave=4, basetexture=8, Color=40.
# IDirect3DDevice8 vtable: Set/GetRenderState C8/CC, Get/SetTSS F8/FC,
# DrawIndexedPrimitive 11C. All calls use stdcall and restore their arguments.
RS = (27, 19, 20, 15, 14, 60)
TSS = ((0,4), (0,5), (0,6), (1,4), (1,5))


def required(files):
    from t3_rig_export import iter_blocks, quoted_value
    found=False
    for key, (path, _owner) in files.items():
        if key.lower().endswith(('.sca', '.lod')):
            data=path.read_bytes()
            if b'T3Transparency' not in data:continue
            for _,_,shader in iter_blocks(data.decode('latin1'),'Shader'):
                if not re.search(r'\bT3Transparency\b',shader):continue
                values=re.findall(r'\bT3Transparency\s+([^\s}]+)',shader)
                if (len(values)!=1 or not re.fullmatch(r'\d+',values[0]) or
                    not 0<=int(values[0])<=255 or
                    quoted_value(shader,'Type') not in ('BASE','DIFFUSE','DIFFUSE_SPECULAR')):
                    raise ValueError(f'{key}: invalid T3Transparency; expected 0..255 with BASE/DIFFUSE/DIFFUSE_SPECULAR')
                found=True
    return found


class Code:
    def __init__(self, va):
        self.va=va; self.data=bytearray(); self.labels={}; self.fixups=[]
    def emit(self, data):
        self.data.extend(bytes.fromhex(data) if isinstance(data,str) else data)
    def label(self, name): self.labels[name]=len(self.data)
    def branch(self, opcode, target):
        self.emit(opcode); at=len(self.data);self.emit(bytes(4));self.fixups.append((at,target))
    def finish(self):
        for at,target in self.fixups:
            address=self.va+self.labels[target] if isinstance(target,str) else target
            struct.pack_into('<i',self.data,at,address-self.va-at-4)
        return bytes(self.data)


def build(va):
    c=Code(va)
    c.emit('8B 7D 04 60')  # original mov edi,[ebp+4], pushad
    token=b'T3Transparency\0'
    # Compare bytewise: short native tokens may end at a page boundary.
    for offset,value in enumerate(token):
        c.emit(bytes.fromhex('80 7F')+bytes([offset,value]));c.branch('0F 85','native')
    c.emit('6A 01 8B CD');c.branch('E8',0x527340)  # scanner NextToken(true)
    c.emit('84 C0');c.branch('0F 84','next')
    c.emit('FF 75 04');c.branch('E8',0x62B8A2)  # atoi
    c.emit('83 C4 04 85 C0');c.branch('0F 89','nonnegative')
    c.emit('31 C0')
    c.label('nonnegative');c.emit('3D FF 00 00 00');c.branch('0F 8E','clamped')
    c.emit('B8 FF 00 00 00')
    # Preserve the native UV selector and every other named shader field.
    c.label('clamped');c.emit('34 FF 8B 94 24 3C 08 00 00 88 42 0D 66 C7 42 0E 33 54')
    c.label('next');c.emit('61');c.branch('E9',0x555526)
    c.label('native');c.emit('61 BE DC AE 65 00');c.branch('E9',PARSER+8)
    parser=c.finish()
    if len(parser)>DRAW_OFFSET:raise ValueError('Material parser exceeds allocation')
    c=Code(va+DRAW_OFFSET)
    c.emit('55 8B EC 53 56 57 83 EC 2C 8B 75 08') # device=esi, 11 saved states
    c.emit('66 81 7F 0E 33 54');c.branch('0F 85','native')
    c.emit('80 7F 0D FF');c.branch('0F 84','native')  # 0% transparency = native
    # Snapshot before modifying anything. Failed queries fall back to native.
    for i,state in enumerate(RS):
        c.emit(bytes.fromhex('8D 44 24')+bytes([i*4])+bytes.fromhex('50 6A')+bytes([state]))
        c.emit('56 8B 06 FF 90 CC 00 00 00 85 C0');c.branch('0F 88','native')
    for i,(stage,state) in enumerate(TSS,start=len(RS)):
        c.emit(bytes.fromhex('8D 44 24')+bytes([i*4])+bytes.fromhex('50 6A')+bytes([state])+b'\x6A'+bytes([stage]))
        c.emit('56 8B 06 FF 90 F8 00 00 00 85 C0');c.branch('0F 88','native')
    def set_rs(state,value):
        c.emit('68');c.emit(struct.pack('<I',value));c.emit(b'\x6A'+bytes([state]));c.emit('56 8B 06 FF 90 C8 00 00 00')
    for state,value in ((27,1),(19,5),(20,6),(15,0),(14,0)):
        set_rs(state,value)
    c.emit('0F B6 47 0D C1 E0 18 0D FF FF FF 00 50 6A 3C 56 8B 06 FF 90 C8 00 00 00')
    for (stage,state),value in zip(TSS,(4,2,3,2,1)):
        c.emit(b'\x6A'+bytes([value])+b'\x6A'+bytes([state])+b'\x6A'+bytes([stage]));c.emit('56 8B 06 FF 90 FC 00 00 00')
    c.branch('E8','draw');c.emit('8B D8')  # preserve HRESULT through restore
    for i,state in enumerate(RS):
        c.emit(bytes.fromhex('FF 74 24')+bytes([i*4])+b'\x6A'+bytes([state]));c.emit('56 8B 06 FF 90 C8 00 00 00')
    for i,(stage,state) in enumerate(TSS,start=len(RS)):
        c.emit(bytes.fromhex('FF 74 24')+bytes([i*4])+b'\x6A'+bytes([state])+b'\x6A'+bytes([stage]));c.emit('56 8B 06 FF 90 FC 00 00 00')
    c.emit('8B C3');c.branch('E9','done')
    c.label('native');c.branch('E8','draw')
    c.label('done');c.emit('83 C4 2C 5F 5E 5B 5D C2 18 00')
    c.label('draw')
    for offset in (28,24,20,16,12,8):c.emit(bytes.fromhex('FF 75')+bytes([offset]))
    c.emit('8B 06 FF 90 1C 01 00 00 C3')
    return parser+b'\x90'*(DRAW_OFFSET-len(parser))+c.finish()


def patches(original, va):
    if hashlib.sha256(original).hexdigest()!=SHA256:
        raise ValueError('Transparency: unsupported T3.exe fingerprint')
    result=[]
    for i,site in enumerate((PARSER,*DRAW_SITES)):
        size=8 if i==0 else 6
        offset=site-0x400000
        expected=original[offset:offset+size]
        if i==0:
            assert expected==bytes.fromhex('8B 7D 04 BE DC AE 65 00')
        else:
            assert expected[:2] in (b'\xFF\x90',b'\xFF\x91',b'\xFF\x92') and expected[2:]==b'\x1C\x01\0\0'
        target=va if i==0 else va+DRAW_OFFSET
        replacement=(b'\xE9' if i==0 else b'\xE8')+struct.pack('<i',target-site-5)+b'\x90'*(size-5)
        result.append(dict(id=f'material_transparency_{i}',target='T3.exe',type='aob_write',section='.text',
                           expected_matches=1,pattern=original[offset-48:offset+size+24].hex(' '),
                           write_offset=48,expected=expected.hex(' '),replacement=replacement.hex(' ')))
    # Widen the loader's zero initialization to include its padding. Native
    # BaseTextureUVSet assignments remain byte-sized (0x5554B7). The PDB's
    # next field starts at +16; Clone and operator= copy all 44 bytes.
    offset=UV_INIT-0x400000
    expected=bytes.fromhex('88 58 0C')
    assert original[offset:offset+3]==expected
    result.append(dict(id='material_transparency_padding_init',target='T3.exe',
                       type='aob_write',section='.text',expected_matches=1,
                       pattern=original[offset-24:offset+27].hex(' '),write_offset=24,
                       expected=expected.hex(' '),replacement='89 58 0c'))
    return result
