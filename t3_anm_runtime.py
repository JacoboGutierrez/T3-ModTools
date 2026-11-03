"""Native patches owned by the compiler's verified ANM compatibility profile.

Aim rules live in the loader's newly allocated RX section. Original binaries
remain pristine; historical per-mod ANM patches are recognized by exact digest.
"""
from __future__ import annotations
import hashlib
import json
import struct

from t3_anm_compat import AimRule, CompatibilityPlan
import t3_anm_variants

T3_SHA256='52f68d5df4912aba662f0371a06ae0b1ec447ef4b7338460224b20904eb0f061'
AI_SHA256='817ba995212c4daed24c5205bfbbe575ff9f28a6ddcc4fc494141d73934d66ae'
BIND_RAW=0x1232EA
BIND_ORIGINAL=bytes.fromhex('F3 A5 8B 50 44 B9 10 00 00 00 8D 7C 24 74 8D 74 1A 0C F3 A5')
BIND_FIXED=bytes.fromhex('F3 A5 8B 50 44 B1 10 8D 7C 24 74 8D B4 1A 98 00 00 00 F3 A5')
AIM_HOOK_VA=0x542781
AIM_HOOK=bytes.fromhex('E8 3A FF FB FF 8B 08 53 89 4C 24 64')
NAV_VA=0x10129F00
NAV_END=0x1012A000
NAV_NATIVE_VA=0x1000F750
NAV_HOOK_VA=0x1000E998
NAV_HOOK=bytes.fromhex('E8 B3 0D 00 00 8A 86 17 01 00 00 83 C4 08')
NAV_ANCHOR=bytes.fromhex('B8 08 E4 13 10 E9 44 B5 F7 FF')
NAV_ANCHOR_VA=0x10129873
PITCH_HOOK_VA=0x1000F0E2
PITCH_NATIVE_VA=0x1000FB30
PITCH_HOOK=bytes.fromhex('E8 49 0A 00 00 8A 44 24 23 83 C4 10 D9 5C 24 14')


def _build_navigation():
    """PIC body heading and neutral look pitch outside alert.

    Heavy Assault's spawn reservation ends at NAV_VA. The old T900S-only helper
    remains historical migration input; this compiler owns the expanded helper.
    """
    code,labels,fixups=bytearray(),{},[]
    def emit(value):code.extend(bytes.fromhex(value))
    def label(name):labels[name]=len(code)
    def branch(op,target,size=4):
        emit(op);fixups.append((len(code),target,size));code.extend(bytes(size))
    def call(va):
        at=NAV_VA+len(code);emit('E8');code.extend(struct.pack('<i',va-at-5))
    emit('80 BE 17 01 00 00 00');branch('0F 85','native')
    emit('80 BE 14 01 00 00 00');branch('0F 84','native')
    branch('E8','cast');emit('85 C0');branch('0F 84','native')
    label('body');emit('55 8B EC 83 EC 0C')
    emit('FF 75 0C FF 75 08');call(NAV_NATIVE_VA);emit('83 C4 08')
    emit('8B 46 08 8B 40 48 8B 40 2C 8B 40 7C 8D 55 F4 52 83 C0 48 50')
    call(NAV_NATIVE_VA);emit('83 C4 08')
    emit('8B 45 0C 8B 55 F8 89 50 04 8B E5 5D C3')
    label('native');at=NAV_VA+len(code);emit('E9');code.extend(struct.pack('<i',NAV_NATIVE_VA-at-5))
    # Process's pitch AngleDelta must neutralize the *look control*, not the
    # animated muzzle. Otherwise raised-rifle poses drive the torso downward.
    # Alert actors use original clips and native aiming. Relaxed actors may
    # use raised-rifle variants; return their look control to neutral.
    label('pitch')
    emit('80 BE 17 01 00 00 00');branch('75','pitch_native',1)
    # Preserve Process's mounted/vehicle path (caller local byte +0x13,
    # now +0x27 after four cdecl arguments and this CALL's return address).
    emit('80 7C 24 27 00');branch('75','pitch_native',1)
    # Variant library belongs to T900S. Heavy Assault keeps native vertical
    # control for all its unrelated dual-WM20 animations, even when relaxed.
    emit('8B 46 04 8B 40 04 81 38 54 39 30 30');branch('75','pitch_native',1)
    emit('66 81 78 04 53 00');branch('75','pitch_native',1)
    emit('8B 46 08 8B 40 48 8B 40 2C')
    # GetUpDown and Vector2Angles use the SAME pitch sign. Process negates
    # AngleDelta, then cHumanControl::Aim negates its pitch argument again.
    # Delta(0, degrees(GetUpDown)) therefore converges toward zero.
    # Keep constants on the stack to remain PIC at arbitrary A2.dll bases.
    emit('68 00 00 34 43 D9 80 E8 08 00 00 D8 0C 24 D9 EB DE F9 D9 1C 24')
    emit('6A 00');call(PITCH_NATIVE_VA);emit('83 C4 08 C3')
    label('pitch_native');at=NAV_VA+len(code);emit('E9');code.extend(struct.pack('<i',PITCH_NATIVE_VA-at-5))
    label('cast')
    emit('8B 46 04 8B 40 04 81 38 54 39 30 30');branch('75','no',1)
    emit('66 81 78 04 53 00');branch('74','yes',1)
    emit('81 78 04 48 65 61 76');branch('75','no',1)
    emit('81 78 08 79 41 73 73');branch('75','no',1)
    emit('81 78 0C 61 75 6C 74');branch('75','no',1)
    emit('80 78 10 00');branch('75','no',1)
    label('yes');emit('B8 01 00 00 00 C3')
    label('no');emit('31 C0 C3')
    for offset,target,size in fixups:struct.pack_into('<i' if size==4 else '<b',code,offset,labels[target]-offset-size)
    if NAV_VA+len(code)>NAV_END:raise ValueError('ANM navigation exceeds its reserved code region')
    return bytes(code),NAV_VA+labels['pitch']


NAV_CODE,PITCH_VA=_build_navigation()


def build_navigation() -> bytes:
    return _build_navigation()[0]

LEGACY={
 'anm_missing_joint_local_bind':('T3.exe','429c760d5c6ed8dd190363ff33f0f463f3458eb239c6fbd3dbaa06cf62e9279d'),
 'anm_aim_tls_executable':('T3.exe','00a0b620cb29216047ac66170b96d804ceddafa547bfe846a9a8b32f5c6e6337'),
 'anm_wm20_aim_compositor':('T3.exe','86069dd432e2a74c57ef404ee4f2a5a9e805a554c7090bf2440e897e030d2a24'),
 'anm_wm20_aim_hook':('T3.exe','57c6ae15a5afb8e08e39980edff7b88a54eb3521d1bed2a9bfc861d096dc3177'),
 'anm_t900s_navigation_heading':('Ai.Dll','9f4d7376c19a43600a3ea6394e90e38d99e6ff849608a9d814fb136bb248d076'),
 'anm_t900s_navigation_hook':('Ai.Dll','1ff50fe6d1350153e858566e813c5b0fa942576c436b3f9a65d5d40ba2b249cb'),
}


def is_legacy_patch(patch):
    if patch.get('id') not in LEGACY:return False
    target,digest=LEGACY[patch['id']]
    identity={k:patch[k] for k in ['type','pattern','replacement','write_offset','expected_fill','expected_matches','section'] if k in patch}
    actual=hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if actual!=digest or patch.get('target','T3.exe')!=target:
        raise ValueError(f"Modified legacy ANM patch {patch['id']}: cannot replace it automatically")
    return True


def aim_hook(code_va):
    return b'\xE8'+struct.pack('<i',code_va-AIM_HOOK_VA-5)+AIM_HOOK[5:]


def build_compositor(rules: list[AimRule], code_va: int) -> bytes:
    if not rules:return b''
    if len(rules)>1024:raise ValueError('Too many automatic ANM rules')
    code,labels,fixups=bytearray(),{},[]
    def emit(value):code.extend(bytes.fromhex(value))
    def label(name):labels[name]=len(code)
    def ref(op,target,absolute=False):
        emit(op);fixups.append((len(code),target,absolute));code.extend(bytes(4))
    def call(va):
        at=code_va+len(code);emit('E8');code.extend(struct.pack('<i',va-at-5))
    def file_pointer(channel):
        shift=channel*0x64
        emit('8B 97');code.extend(struct.pack('<I',shift+0x64))
        emit('80 BF');code.extend(struct.pack('<I',shift+0x74));emit('00 74 06 8B 97')
        code.extend(struct.pack('<I',shift+0x60))
        emit('3B 97 58 03 00 00');ref('0F 83','fallback')
        emit('69 D2 A8 00 00 00 8B 87 50 03 00 00 8D 44 10 08')
    emit('83 FD 02');ref('0F 85','native')
    emit('81 BF 5C 03 00 00 20 00 00 00');ref('0F 85','native')
    emit('55 8B EC 53 56 57 83 EC 30')
    emit('8B 5D 7C 83 FB 20');ref('0F 83','fallback')
    emit('80 BF DA 00 00 00 00');ref('0F 84','fallback')
    emit('8B 87 F0 00 00 00 80 3C 18 00');ref('0F 84','fallback')
    emit('6B D3 3C 03 97 94 00 00 00 80 3A 00');ref('0F 84','fallback')
    file_pointer(1);emit('89 45 F0')  # Temporary aim/clip pointers precede quaternion scratch.
    file_pointer(2);emit('89 45 EC')
    ref('BE','table',True)
    label('rule');emit('8B 4E 08 85 C9');ref('0F 84','fallback')
    emit('0F A3 D9');ref('0F 83','next')  # BT mask, bone; JNC.
    emit('8B 45 F0 8B 0E');ref('E8','equal_ci');emit('85 C0');ref('0F 84','next')
    emit('8B 45 EC 8B 4E 04');ref('E8','equal_ci');emit('85 C0');ref('0F 85','compose')
    label('next');emit('83 C6 0C');ref('E9','rule')
    label('compose')
    emit('8B 47 28 8B 40 44 69 D3 78 02 00 00 8D 84 10 A4 01 00 00')
    emit('D9 00 D9 E0 D9 5D E4 D9 40 04 D9 E0 D9 5D E8')
    emit('D9 40 08 D9 E0 D9 5D EC 8B 40 0C 89 45 F0')
    emit('8D 45 E4 50 8D 45 D4 50 8B 4D 0C');call(0x5021C0)
    emit('FF 75 10 8D 45 C4 50 8D 4D D4');call(0x5021C0)
    emit('FF 75 14 8D 45 C4 50 FF 75 0C FF 75 08');call(0x5026C0)
    emit('83 C4 10 83 C4 30 5F 5E 5B 5D C3')
    label('fallback');emit('83 C4 30 5F 5E 5B 5D')
    label('native');at=code_va+len(code);emit('E9');code.extend(struct.pack('<i',0x5026C0-at-5))
    label('equal_ci');emit('53')
    label('compare');emit('8A 19 8A 10 84 DB');ref('0F 84','end_string')
    # The asset filesystem accepts either separator. Fold ASCII letters only;
    # bitwise folding of punctuation would equate '[' with '{', for example.
    emit('80 FB 5C 75 02 B3 2F 80 FA 5C 75 02 B2 2F')
    emit('80 FB 41 72 08 80 FB 5A 77 03 80 CB 20')
    emit('80 FA 41 72 08 80 FA 5A 77 03 80 CA 20')
    emit('38 DA');ref('0F 85','different');emit('40 41');ref('E9','compare')
    label('end_string');emit('84 D2');ref('0F 85','different');emit('B8 01 00 00 00 5B C3')
    label('different');emit('31 C0 5B C3')
    while len(code)%4:emit('90')
    label('table')
    strings={}
    for rule in rules:
        if not rule.mask or rule.mask & ~((1<<2)|(1<<3)|(1<<23)):
            raise ValueError('Unvalidated automatic ANM joint mask')
        for path in [rule.aim,rule.clip]:
            if not path or len(path)>127 or '\0' in path:raise ValueError('Invalid runtime ANM path')
            path.encode('ascii')
            name=strings.setdefault(path,'string'+str(len(strings)))
            ref('',name,True)
        code.extend(struct.pack('<I',rule.mask))
    code.extend(bytes(12))
    for path,name in strings.items():label(name);code.extend(path.encode('ascii')+b'\0')
    for offset,target,absolute in fixups:
        value=code_va+labels[target] if absolute else labels[target]-offset-4
        struct.pack_into('<I' if absolute else '<i',code,offset,value)
    return bytes(code)


def validate_targets(plan: CompatibilityPlan, t3: bytes, ai: bytes | None):
    if plan.local_bind or plan.rules or plan.variants:
        if hashlib.sha256(t3).hexdigest()!=T3_SHA256:raise ValueError('Automatic ANM correction requires the validated pristine T3.exe')
        for raw,anchor in [(BIND_RAW,BIND_ORIGINAL),(AIM_HOOK_VA-0x400000,AIM_HOOK)]:
            if t3.count(anchor)!=1 or t3.find(anchor)!=raw:raise ValueError('ANM instruction anchor changed')
    if plan.variants:
        for address,h in [(t3_anm_variants.HOOK_VA,t3_anm_variants.HOOK),
                          (t3_anm_variants.START_HOOK_VA,t3_anm_variants.START_HOOK),
                          (t3_anm_variants.GUARD_VA,t3_anm_variants.GUARD)]:
            if t3.count(h)!=1 or t3.find(h)!=address-0x400000:
                raise ValueError('NPC animation lookup anchor changed')
    if plan.navigation or plan.variants:
        if ai is None or hashlib.sha256(ai).hexdigest()!=AI_SHA256:raise ValueError('Automatic ANM navigation requires the validated pristine Ai.dll')
        for va,anchor in [(NAV_HOOK_VA,NAV_HOOK),(NAV_ANCHOR_VA,NAV_ANCHOR),
                          (PITCH_HOOK_VA,PITCH_HOOK)]:
            if ai.count(anchor)!=1 or ai.find(anchor)!=va-0x10000000:raise ValueError('Navigation instruction anchor changed')
        if ai[NAV_VA-0x10000000:NAV_END-0x10000000]!=bytes(NAV_END-NAV_VA):
            raise ValueError('Navigation reservation is occupied')


def variant_offset(plan):
    return (len(build_compositor(plan.rules,0x1000000))+15)&~15


def build_extension(plan,va):
    code=build_compositor(plan.rules,va)
    if plan.variants:
        offset=variant_offset(plan)
        code+=b'\x90'*(offset-len(code))+t3_anm_variants.build_selector(
            plan.variants,va+offset,plan.variant_idle_links,plan.variant_idle_normal_sources)
    return code


def patches(plan: CompatibilityPlan, code_va: int | None) -> list[dict]:
    def replace(id,target,original,replacement):
        return {'id':id,'target':target,'type':'aob_replace','section':'.text','expected_matches':1,
                'pattern':original.hex(' ').upper(),'replacement':replacement.hex(' ').upper()}
    result=[]
    if plan.local_bind:result.append(replace('anm_missing_joint_local_bind','T3.exe',BIND_ORIGINAL,BIND_FIXED))
    if plan.rules:
        if code_va is None:raise ValueError('Missing ANM compositor allocation')
        result.append(replace('anm_automatic_aim_hook','T3.exe',AIM_HOOK,aim_hook(code_va)))
    if plan.variants:
        if code_va is None:raise ValueError('Missing NPC variant allocation')
        result.append(replace('anm_npc_variant_lookup','T3.exe',t3_anm_variants.HOOK,
                              t3_anm_variants.hook(code_va+variant_offset(plan))))
        result.append(replace('anm_npc_variant_instant_lookup','T3.exe',t3_anm_variants.START_HOOK,
                              t3_anm_variants.hook(code_va+variant_offset(plan),start=True)))
        result.append(replace('anm_npc_variant_alert_guard','T3.exe',t3_anm_variants.GUARD,
                              t3_anm_variants.guard_hook(t3_anm_variants.guard_address(
                                  plan.variants,code_va+variant_offset(plan),plan.variant_idle_links,
                                  plan.variant_idle_normal_sources))))
    if plan.navigation:
        result.append({'id':'anm_automatic_navigation_heading','target':'Ai.Dll','type':'aob_write','section':'.text',
                       'expected_matches':1,'pattern':NAV_ANCHOR.hex(' ').upper(),
                       'write_offset':hex(NAV_VA-NAV_ANCHOR_VA),'expected_fill':'00','replacement':NAV_CODE.hex(' ').upper()})
        result.append(replace('anm_automatic_navigation_hook','Ai.Dll',NAV_HOOK,
                              b'\xE8'+struct.pack('<i',NAV_VA-NAV_HOOK_VA-5)+NAV_HOOK[5:]))
    if plan.variants:
        result.append(replace('anm_npc_relaxed_pitch_hook','Ai.Dll',PITCH_HOOK,
                              b'\xE8'+struct.pack('<i',PITCH_VA-PITCH_HOOK_VA-5)+PITCH_HOOK[5:]))
    return result
