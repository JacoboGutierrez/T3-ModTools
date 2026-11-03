"""Explicit animation pairs and native selection at locomotion transitions."""
from __future__ import annotations
import hashlib
import json
import re
import struct

SEARCH_VA=0x543440
HOOK_VA=0x54382A
HOOK=bytes.fromhex('E8 11 FC FF FF 8B D0 83 FA FF')
START_HOOK_VA=0x5432F0
START_HOOK=bytes.fromhex('E8 4B 01 00 00 8B F8 83 FF FF')
GUARD_VA=0x489CFB
GUARD=bytes.fromhex('39 AB 38 3B 01 00 74 2F')
OUTER_RETURN=0x489D1A
GET_MODULE_HANDLE_IAT=0x62F1B4


def prepare(projects, effective, files, report):
    from t3_anm_compat import internal_path, source_text, library_roles
    from t3_rig_export import iter_blocks, quoted_value
    pairs={};configs=[]
    for project in reversed([p for p in projects if p.enabled]):
        path=project.folder/'anm_variants.json'
        if not path.is_file():continue
        data=path.read_bytes();config=json.loads(data)
        if config.get('format_version')!=1:raise ValueError(f'{path}: unsupported ANM variants format')
        if config.get('library')!='ca/casts/t900s/tps/anim.lib':
            raise ValueError(f'{path}: NPC variants require the verified T900S TPS library')
        configs.append({'file':str(path.resolve()),'sha256':hashlib.sha256(data).hexdigest()})
        for item in config['pairs']:
            base,alt=(internal_path(item[k]) for k in ('base','alternative'))
            if base==alt or not base.endswith('.anm') or not alt.endswith('.anm') or alt not in files:
                raise ValueError(f'{path}: missing/invalid alternative {alt}')
            if any(len(p)>127 or not p.isascii() for p in (base,alt)):
                raise ValueError('Variant path exceeds native ANM filename capacity')
            pairs[base]=alt
    if not pairs:return {},[]
    if len(pairs)>32:raise ValueError('Too many NPC variant pairs')
    library='ca/casts/t900s/tps/anim.lib'
    original=effective(library);roles=library_roles(original)
    source=source_text(original);blocks=list(iter_blocks(source,'AnimationLib'))
    if len(blocks)!=1:raise ValueError('Expected one NPC animation library')
    additions=[];found=set()
    for _,_,block in iter_blocks(blocks[0][2],'Anim'):
        role=quoted_value(block,'Name').upper();base=internal_path(quoted_value(block,'File'))
        if base not in pairs:continue
        if not role.startswith('HAND_') or not role.endswith(('_IDLE','_WALK','_RUNNING')):
            raise ValueError(f'Variant source is used by a non-locomotion role: {role}')
        alt=pairs[base];found.add(base)
        additions.append('Anim {\n'+re.sub(r'(\bFile\s+")[^"\r\n]*(")',
            lambda m:m[1]+alt+m[2],block,count=1)+'\n}')
    if found!=set(pairs):raise ValueError('NPC variant source is not registered in the effective library')
    body=blocks[0][2]
    body,n=re.subn(r'\bAnimNum\s+\d+',f'AnimNum {len(roles)+len(additions)}',body,count=1)
    if n!=1:raise ValueError('Missing AnimNum in NPC library')
    generated=('AnimationLib {\n'+body+'\n'+'\n'.join(additions)+'\n}\n').encode('latin1')
    report['variant_configuration_inputs']=configs
    report['variants']=[{'base':b,'alternative':a,'chance_percent':50} for b,a in sorted(pairs.items())]
    # Derive continuity from library roles, never from filename conventions.
    # Shared WM20 clips in other weapon roles naturally deduplicate these links.
    links=set();normal_sources=set()
    for role,idle in roles.items():
        if not role.endswith('_IDLE') or idle not in pairs:continue
        for suffix in ('_WALK','_RUNNING'):
            source=roles.get(role[:-5]+suffix)
            if source in pairs:links.add((idle,source,pairs[source]))
        # Keep the weapon's normal aiming pose after either fire animation.
        # SECOUNDARY is the original engine/library spelling.
        for suffix in ('_FIRE','_SECOUNDARY_FIRE'):
            source=roles.get(role[:-5]+suffix)
            if source:normal_sources.add((idle,source))
    report['variant_idle_links']=[{'idle':i,'source':s,'source_alternative':a} for i,s,a in sorted(links)]
    report['variant_condition']='player_or_npc_without_alert'
    report['variant_idle_policy']='inherit_previous_locomotion_variant'
    report['variant_post_fire_idle']='normal'
    report['variant_idle_normal_sources']=[{'idle':i,'source':s} for i,s in sorted(normal_sources)]
    return {library:generated},list(sorted(pairs.items()))


def hook(code_va, *, start=False):
    address,original=(START_HOOK_VA,START_HOOK) if start else (HOOK_VA,HOOK)
    return b'\xe8'+struct.pack('<i',code_va-address-5)+original[5:]


def guard_hook(code_va):
    return b'\xe8'+struct.pack('<i',code_va-GUARD_VA-5)+b'\x90'+GUARD[6:]


def _build_selector(pairs,va,idle_links=(),idle_normal_sources=()):
    """Search wrapper: no mutable globals, RNG state or animation-state changes.

    The caller already gates state changes. Keep the original state ID and
    select a different loaded record for scene actors on channel 2. AI-owned
    actors additionally require no alert. Idle inherits the active move variant,
    but always returns to normal after a configured fire animation.
    """
    code=bytearray();labels={};fixups=[]
    def e(s):code.extend(bytes.fromhex(s))
    def u(v):code.extend(struct.pack('<I',v))
    def label(s):labels[s]=len(code)
    def ref(op,s,absolute=False):e(op);fixups.append((len(code),s,absolute));u(0)
    def call(target):e('E8');code.extend(struct.pack('<i',target-(va+len(code)+4)))
    # Saved pushad layout: EDI,ESI,EBP,ESP,EBX,EDX,ECX,EAX,flags,return,state.
    e('9C 60 FF 74 24 28');call(SEARCH_VA);e('89 44 24 1C 83 F8 FF');ref('0F 84','done')
    e('81 7C 24 24');u(HOOK_VA+5);ref('0F 85','instant')
    e('81 7C 24 40');u(OUTER_RETURN);ref('0F 85','done')
    e('83 7C 24 44 02');ref('0F 85','done');ref('E9','qualified')
    # CrossFade with zero duration delegates to StartPlay. Match that exact
    # call chain too, never other StartPlay users such as firing or initialization.
    label('instant');e('81 7C 24 3C 1B 38 54 00');ref('0F 85','done')
    e('81 7C 24 60');u(OUTER_RETURN);ref('0F 85','done')
    e('83 7C 24 64 02');ref('0F 85','done')
    label('qualified')
    e('8B 7C 24 18 81 BF 5C 03 00 00 20 00 00 00');ref('0F 85','done')
    ref('E8','find_actor');e('85 C0');ref('0F 84','done')
    ref('E8','find_npc');e('85 C0');ref('0F 84','eligible')
    e('80 B8 17 01 00 00 00');ref('0F 85','done')
    label('eligible')
    e('8B 87 50 03 00 00 85 C0');ref('0F 84','done')
    e('8B 54 24 1C 69 D2 A8 00 00 00 8D 5C 10 08')
    ref('BE','table',True)
    label('pair');e('8B 0E 85 C9');ref('0F 84','done');e('8B C3');ref('E8','equal')
    e('85 C0');ref('0F 85','find_alt');e('83 C6 08');ref('E9','pair')
    label('find_alt');e('31 DB 8B AF 50 03 00 00')
    label('scan');e('3B 9F 58 03 00 00');ref('0F 83','done')
    e('8B 44 24 28 39 45 00');ref('0F 85','next_record')
    e('8D 45 08 8B 4E 04');ref('E8','equal');e('85 C0');ref('0F 85','choose')
    label('next_record');e('43 81 C5 A8 00 00 00');ref('E9','scan')
    label('choose')
    ref('E8','inherit_idle');e('85 C0');ref('0F 84','done')
    e('83 F8 01');ref('0F 84','select_alt')
    # Cosmetic pseudo-random bit from time, actor identity and requested state.
    e('A1 E8 C1 14 01 33 C7 33 44 24 28 8B D0 C1 EA 10 33 C2')
    e('69 C0 2D 35 EB 7F 8B D0 C1 EA 0F 33 C2 69 C0 8B A6 6C 84')
    e('8B D0 C1 EA 10 33 C2 A8 01');ref('0F 84','done')
    label('select_alt');e('89 5C 24 1C')
    label('done');e('61 9D C2 04 00')

    # Return -1 when no configured movement->idle link applies, otherwise
    # 0 for the normal clip or 1 for its alternative. Preserve candidate EBX.
    # The native lookup runs before CrossFade/StartPlay replaces the old index.
    label('inherit_idle');e('53 56 8B 1E')
    e('8B 97 2C 01 00 00 80 BF 3C 01 00 00 00 74 06 8B 97 28 01 00 00')
    e('3B 97 58 03 00 00');ref('0F 83','inherit_unknown')
    e('69 D2 A8 00 00 00 03 97 50 03 00 00 8D 6A 08')
    ref('BE','idle_table',True)
    label('idle_link');e('8B 0E 85 C9');ref('0F 84','inherit_unknown')
    e('8B C3');ref('E8','equal');e('85 C0');ref('0F 84','next_link')
    e('8B C5 8B 4E 04');ref('E8','equal');e('85 C0');ref('0F 85','inherit_normal')
    e('8B C5 8B 4E 08');ref('E8','equal');e('85 C0');ref('0F 85','inherit_done')
    label('next_link');e('83 C6 0C');ref('E9','idle_link')
    label('inherit_unknown');e('B8 FF FF FF FF');ref('E9','inherit_done')
    label('inherit_normal');e('31 C0')
    label('inherit_done');e('5E 5B C3')

    # Preserve the original state comparison. If alert begins during an active
    # variant, permit one normal CrossFade even when the state ID did not change.
    # No persistent flag, animation index or state ID is written by this guard.
    label('guard');e('39 AB 38 3B 01 00 9C 60');ref('0F 85','guard_done')
    e('8D BB C4 00 00 00 81 BF 5C 03 00 00 20 00 00 00');ref('0F 85','guard_done')
    ref('E8','find_npc');e('85 C0');ref('0F 84','guard_done')
    e('80 B8 17 01 00 00 00');ref('0F 84','guard_done')
    # Prefer the destination while fading. Once it is original, stop forcing
    # transitions so the normal fade can finish without resetting every frame.
    e('8B 97 2C 01 00 00 80 BF 3C 01 00 00 00 74 06 8B 97 28 01 00 00')
    e('3B 97 58 03 00 00');ref('0F 83','guard_done')
    e('8B 87 50 03 00 00 85 C0');ref('0F 84','guard_done')
    e('69 D2 A8 00 00 00 01 D0 8B 54 24 08 39 10');ref('0F 85','guard_done')
    e('8D 58 08');ref('BE','table',True)
    label('guard_pair');e('8B 4E 04 85 C9');ref('0F 84','guard_done')
    e('8B C3');ref('E8','equal');e('85 C0');ref('0F 85','force_original')
    e('83 C6 08');ref('E9','guard_pair')
    label('force_original');e('83 64 24 20 BF')  # Clear saved ZF only.
    label('guard_done');e('61 9D C3')

    # EDI = controller. Return EAX = matching agent or zero; preserve EDI.
    label('find_npc')
    ref('E8','find_actor');e('85 C0');ref('0F 84','no_npc')
    ref('E9','find_agent')
    label('find_actor')
    # Verify controller belongs to one of the 64 scene actor slots.
    e('A1 8C F9 0D 01 85 C0');ref('0F 84','no_npc')
    e('8B D7 81 EA D0 00 00 00 2B D0');ref('0F 82','no_npc')
    e('8B C2 31 D2 B9 08 41 01 00 F7 F1 85 D2');ref('0F 85','no_npc')
    e('83 F8 40');ref('0F 83','no_npc')
    # Scene actor's human pointer: controller - D0 + 1405C.
    e('8B AF 8C 3F 01 00 85 ED');ref('0F 84','no_npc')
    e('8B C5 C3')
    label('find_agent')
    ref('68','dll',True);e('FF 15');u(GET_MODULE_HANDLE_IAT);e('85 C0');ref('0F 85','ai_loaded')
    ref('68','original_dll',True);e('FF 15');u(GET_MODULE_HANDLE_IAT);e('85 C0');ref('0F 84','no_npc')
    label('ai_loaded')
    e('8B 80 D0 0B 16 00 85 C0');ref('0F 84','no_npc')
    e('8B B0 88 07 00 00 BB 80 00 00 00')  # Bounded team/agent traversal.
    label('team');e('85 F6');ref('0F 84','no_npc')
    e('4B');ref('0F 88','no_npc');e('8B 46 08 85 C0');ref('0F 84','no_npc')
    e('8B 48 0C')
    label('agent');e('85 C9');ref('0F 84','next_team')
    e('4B');ref('0F 88','no_npc');e('8B 41 08 85 C0');ref('0F 84','no_npc')
    e('8B 50 08 85 D2');ref('0F 84','no_npc');e('39 6A 48');ref('0F 84','npc')
    e('8B 09');ref('E9','agent')
    label('next_team');e('8B 36');ref('E9','team')
    label('npc');e('C3')
    label('no_npc');e('31 C0 C3')
    label('equal');e('52')  # ASCII case-insensitive path comparison.
    label('chars');e('8A 10 8A 31 80 FA 5C 75 02 B2 2F 80 FE 5C 75 02 B6 2F')
    e('80 FA 41 72 08 80 FA 5A 77 03 80 CA 20 80 FE 41 72 08 80 FE 5A 77 03 80 CE 20')
    e('38 F2');ref('0F 85','different');e('84 D2');ref('0F 84','same')
    e('40 41');ref('E9','chars')
    label('different');e('31 C0 5A C3')
    label('same');e('B8 01 00 00 00 5A C3')
    label('dll');code.extend(b'A2.dll\0')
    label('original_dll');code.extend(b'Ai.dll\0')
    while len(code)%4:e('90')
    label('table')
    strings={}
    for pair in pairs:
        for path in pair:ref('',strings.setdefault(path,'path'+str(len(strings))),True)
    u(0);u(0)
    label('idle_table')
    for link in idle_links:
        for path in link:ref('',strings.setdefault(path,'path'+str(len(strings))),True)
    # The same source in both columns can only take inherit_normal: that
    # comparison runs first. Reuse the verified reader/ABI with no new hook.
    for idle,source in idle_normal_sources:
        for path in (idle,source,source):ref('',strings.setdefault(path,'path'+str(len(strings))),True)
    u(0);u(0);u(0)
    for path,s in strings.items():label(s);code.extend(path.encode('ascii')+b'\0')
    for offset,s,absolute in fixups:struct.pack_into('<I' if absolute else '<i',code,offset,va+labels[s] if absolute else labels[s]-offset-4)
    return bytes(code),va+labels['guard']


def build_selector(pairs,va,idle_links=(),idle_normal_sources=()):
    return _build_selector(pairs,va,idle_links,idle_normal_sources)[0]


def guard_address(pairs,va,idle_links=(),idle_normal_sources=()):
    return _build_selector(pairs,va,idle_links,idle_normal_sources)[1]
