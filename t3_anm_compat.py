"""Read-only ANM compatibility analysis of the effective mod/vanilla filesystem.

The automatic profile is the verified 32-bone T900S TPS rig and matching casts. Animation
roles come from Anim.lib, not filename heuristics or Blender keyframe counts.
"""
from __future__ import annotations

import hashlib
import math
import re
import zipfile
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from t3_rig_export import iter_blocks, iter_numbered_blocks, quoted_value, numeric_value, data_block, float_values, mat_mul, mat_inverse

LIBRARY = 'ca/casts/t900s/tps/anim.lib'
MODEL = 'ca/casts/t900s/tps/model.lod'
ROOT = '|human_root|body_root|root|spinebone1|spinebone2'
SUPPORTED_JOINTS = {ROOT: 2, ROOT+'|spinebone3': 3, ROOT+'|spinebone3|head': 23}
# Verified Heavy Assault overlay roles use the WM20 channel contract. Do not
# guess references by stripping arbitrary words from role or animation names.
ROLE_REFERENCES = {'HAND_WM20_DUAL_'+suffix: 'HAND_WM20_'+suffix for suffix in
                   ('IDLE','WALK','RUNNING','FIRE','SECOUNDARY_FIRE','CHANGE_BACK','CHANGE_GO')}
# Private WM32 run uses the same native 516 channel contract, selected only for
# its equipped TPS weapon. Keep UPDOWN composition for its inherited torso keys.
ROLE_REFERENCES['HAND_WM32_DUAL_RUNNING'] = 'HAND_WM20_RUNNING'


def internal_path(value: str) -> str:
    value = value.replace('\\', '/')
    parts = PurePosixPath(value).parts
    if not parts or value.startswith('/') or any(p in ('..', '.') for p in parts) or ':' in value or '\0' in value:
        raise ValueError(f'Unsafe ANM asset path: {value!r}')
    return '/'.join(parts).lower()


def source_text(data: bytes) -> str:
    text = data.decode('utf-8-sig') if data.startswith(b'\xef\xbb\xbf') else data.decode('latin1')
    # Preserve quoted strings, including original DCC paths containing //.
    text = re.sub(r'"[^"\r\n]*"|//[^\r\n]*|/\*[\s\S]*?\*/',
                  lambda m: m[0] if m[0].startswith('"') else ' ', text)
    depth = 0
    for token in re.findall(r'"[^"\r\n]*"|[{}]', text):
        depth += (token == '{') - (token == '}')
        if depth < 0:
            raise ValueError('Unbalanced asset braces')
    if depth or text.count('"') % 2:
        raise ValueError('Unbalanced asset braces/quotes')
    return text


@dataclass
class Animation:
    names: tuple[str, ...]
    frames: list[dict[str, list[list[float]]]]


def parse_anm(data: bytes) -> Animation:
    text = source_text(data)
    animations = list(iter_blocks(text, 'Animation'))
    if len(animations) != 1:
        raise ValueError('Expected one Animation block')
    block = animations[0][2]
    frames = []
    names = ()
    for _, _, index, frame in iter_numbered_blocks(block, 'Time'):
        if index != len(frames):
            raise ValueError('ANM frames must be consecutive from zero')
        joints = {}
        for _, _, joint in iter_blocks(frame, 'Joint'):
            name = quoted_value(joint, 'Name')
            values = float_values(data_block(joint, 'TransformationMatrix'))
            if not name.startswith('|') or name in joints:
                raise ValueError('Missing, duplicate or noncanonical ANM joint')
            if len(values) != 16 or not all(math.isfinite(v) for v in values):
                raise ValueError(f'Invalid matrix for {name}')
            if max(abs(values[i]-v) for i,v in [(3,0),(7,0),(11,0),(15,1)]) > 1e-4:
                raise ValueError(f'Non-affine matrix for {name}')
            joints[name] = [values[i:i+4] for i in range(0,16,4)]
        if not joints or frames and tuple(joints) != names:
            raise ValueError('ANM joint order/set changes between frames')
        names = tuple(joints)
        frames.append(joints)
    if not frames or numeric_value(block,'MaxTimeValue',-1) != len(frames) or numeric_value(block,'Fps',0) <= 0:
        raise ValueError('Invalid ANM frame count/Fps')
    return Animation(names,frames)


def library_roles(data: bytes, *, variants: bool = False) -> dict[str, str]:
    result = {}
    for _,_,block in iter_blocks(source_text(data),'Anim'):
        role = quoted_value(block,'Name').upper()
        if role in result and variants:
            base=role;index=1
            while role in result:
                role=f'{base}#variant{index}';index+=1
        if not role or role in result:
            raise ValueError('Missing/duplicate animation role')
        result[role] = internal_path(quoted_value(block,'File'))
    if not result:
        raise ValueError('Empty animation library')
    return result


def model_bones(data: bytes) -> dict[str, list[list[float]]]:
    result = {}
    for _,_,block in iter_blocks(source_text(data),'cBone'):
        name = quoted_value(block,'Name')
        values = float_values(data_block(block,'Matrix'))
        if not name or name in result or len(values)!=16 or not all(math.isfinite(v) for v in values):
            raise ValueError('Invalid skeleton bone')
        result[name] = [values[i:i+4] for i in range(0,16,4)]
    return result


def matrix_error(a,b):
    return max(abs(a[r][c]-b[r][c]) for r in range(4) for c in range(4))


def rotation_is_rigid(m):
    error=max(abs(sum(m[r][k]*m[c][k] for k in range(3))-(r==c)) for r in range(3) for c in range(3))
    det=(m[0][0]*(m[1][1]*m[2][2]-m[1][2]*m[2][1])
         -m[0][1]*(m[1][0]*m[2][2]-m[1][2]*m[2][0])
         +m[0][2]*(m[1][0]*m[2][1]-m[1][1]*m[2][0]))
    return error < 0.002 and abs(det-1) < 0.002


@dataclass(frozen=True)
class AimRule:
    clip: str
    aim: str
    mask: int


@dataclass
class CompatibilityPlan:
    rules: list[AimRule] = field(default_factory=list)
    local_bind: bool = False
    navigation: bool = False
    variants: list[tuple[str,str]] = field(default_factory=list)
    variant_idle_links: list[tuple[str,str,str]] = field(default_factory=list)
    variant_idle_normal_sources: list[tuple[str,str]] = field(default_factory=list)
    generated_files: dict[str,bytes] = field(default_factory=dict)
    report: dict = field(default_factory=lambda: {'format_version':1,'profile':'T900S TPS / 32 bones','animations':[],'vanilla_catalog':[],'archives':[]})


def effective_mod_files(projects) -> dict[str, tuple[Path,str]]:
    result = {}
    for project in reversed([p for p in projects if p.enabled]):
        seen = set()
        if not project.files_path.is_dir():
            continue
        for file in sorted(project.files_path.rglob('*')):
            if file.is_file():
                key = internal_path(file.relative_to(project.files_path).as_posix())
                if key in seen:
                    raise ValueError(f'{project.id}: duplicate case-insensitive asset {key}')
                seen.add(key)
                result[key] = (file,project.id)
    return result


def analyze(game_folder: Path, projects) -> CompatibilityPlan:
    plan = CompatibilityPlan()
    files = effective_mod_files(projects)
    candidates = sorted(k for k in files if k.endswith('.anm'))
    if not candidates:
        return plan
    with ExitStack() as stack:
        vanilla = {}
        for filename in ['Game.cod','Patch116.Cod','Language.cod']:
            path = game_folder / filename
            if not path.is_file():
                continue
            archive = stack.enter_context(zipfile.ZipFile(path))
            # Stream hashes without keeping the large vanilla archive in memory.
            h=hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
            plan.report['archives'].append({'name':filename,'sha256':h.hexdigest()})
            for info in archive.infolist():
                if info.is_dir():continue
                key=internal_path(info.filename)
                vanilla[key]=(archive,info,filename)
        if not vanilla:
            raise ValueError('ANM compatibility analysis requires the installed original COD archives')
        plan.report['vanilla_catalog']=[{'path':k,'archive':v[2],'crc32':f'{v[1].CRC:08x}','size':v[1].file_size}
                                        for k,v in sorted(vanilla.items()) if k.endswith('.anm')]
        def original(key):
            z,info,_=vanilla[key]
            return z.read(info)
        effective_cache={}
        def effective(key):
            if key not in effective_cache:
                effective_cache[key]=files[key][0].read_bytes() if key in files else original(key)
            return effective_cache[key]
        original_cache={}
        def original_anm(key):
            if key not in original_cache:original_cache[key]=parse_anm(original(key))
            return original_cache[key]
        from t3_anm_variants import prepare
        plan.generated_files,plan.variants=prepare(projects,effective,files,plan.report)
        plan.variant_idle_links=[(v['idle'],v['source'],v['source_alternative'])
                                 for v in plan.report.get('variant_idle_links',[])]
        plan.variant_idle_normal_sources=[(v['idle'],v['source'])
                                          for v in plan.report.get('variant_idle_normal_sources',[])]
        def effective_library(key):
            return plan.generated_files[key] if key in plan.generated_files else effective(key)
        base_roles = library_roles(original(LIBRARY)) if LIBRARY in vanilla else {}
        role_paths={}
        libraries=sorted(k for k in vanilla.keys() | files.keys()
                         if k.startswith('ca/casts/') and k.endswith('/anim.lib'))
        plan.report['libraries']=[]
        for library_path in libraries:
            roles=library_roles(effective_library(library_path),variants=library_path in plan.generated_files)
            if not set(roles.values()).intersection(candidates):continue
            context={'library':library_path,'aim':roles.get('UPDOWN'),'error':None}
            references=library_roles(original(library_path)) if library_path in vanilla else base_roles
            try:
                if not library_path.endswith('/tps/anim.lib'):raise ValueError('Not a TPS library')
                model_path=library_path.rsplit('/',1)[0]+'/model.lod'
                old_bones=model_bones(original(MODEL));bones=model_bones(effective(model_path))
                if len(bones)!=32 or list(bones)!=list(old_bones):raise ValueError('T900S TPS skeleton/order changed')
                if any(matrix_error(bones[n],old_bones[n])>2e-5 for n in bones):raise ValueError('T900S TPS bind pose changed')
                aim=parse_anm(effective(roles['UPDOWN']));reference_aim=original_anm(base_roles['UPDOWN'])
                if aim.names!=reference_aim.names or len(aim.frames)!=25:raise ValueError('UPDOWN contract changed')
                for name,index in SUPPORTED_JOINTS.items():
                    if list(bones)[index]!=name:raise ValueError('Unexpected T900S joint index')
                    local=mat_mul(bones[name],mat_inverse(bones[name.rsplit('|',1)[0]]))
                    if matrix_error(local,aim.frames[12][name])>2e-5:raise ValueError('UPDOWN neutral differs from local bind')
                    if any(matrix_error(a[name],b[name])>2e-5 for a,b in zip(aim.frames,reference_aim.frames)):
                        raise ValueError('UPDOWN rotations/translations changed')
                context['bones']=set(bones)
            except (KeyError,ValueError,IndexError) as exc:
                context['error']=str(exc)
            plan.report['libraries'].append({k:v for k,v in context.items() if k!='bones'})
            for role,path in roles.items():
                baseline=references.get(role.split('#variant',1)[0]) if library_path.endswith('/tps/anim.lib') else None
                if baseline is None and role in ROLE_REFERENCES and library_path.endswith('/tps/anim.lib'):
                    baseline=base_roles.get(ROLE_REFERENCES[role])
                if baseline is None and '#variant' in role:
                    source_path=roles[role.split('#variant',1)[0]]
                    if source_path in vanilla:baseline=source_path
                # A custom weapon can reuse an existing vanilla asset (e.g.
                # WM27 -> WM20 run). Its exact original path is a reference too.
                if baseline is None and path in vanilla and library_path.endswith('/tps/anim.lib'):
                    baseline=path
                role_paths.setdefault(path,[]).append((role,baseline,context))
        for path in candidates:
            source,mod=files[path]
            current_data=effective(path)
            row={'path':path,'mod':mod,'sha256':hashlib.sha256(current_data).hexdigest(),
                 'roles':sorted({r for r,_,_ in role_paths.get(path,[])}),
                 'libraries':sorted({c['library'] for _,_,c in role_paths.get(path,[])}),
                 'added_joints':[],'corrected_joints':[]}
            plan.report['animations'].append(row)
            try:
                current=parse_anm(current_data)
                entries=role_paths.get(path,[])
                # Runtime dispatch identifies (clip, UPDOWN). An incompatible
                # library using a different UPDOWN cannot collide with this key.
                invalid_aims={c['aim'] for _,_,c in entries if c['error']}
                eligible=[e for e in entries if not e[2]['error'] and e[2]['aim'] not in invalid_aims]
                row['excluded_libraries']=sorted({c['library'] for _,_,c in entries if c['error'] or c['aim'] in invalid_aims})
                if entries and not eligible:
                    row.update(status='outside_profile',reason=next((c['error'] for _,_,c in entries if c['error']),
                               'Shared clip/UPDOWN has an incompatible library'))
                    continue
                comparisons=[]
                # A renamed replacement inherits the vanilla reference of its role.
                for role,baseline,context in eligible:
                    if baseline in vanilla:comparisons.append((role,baseline,context))
                if not comparisons and path in vanilla:comparisons=[('',path,None)]
                if not comparisons:
                    row.update(status='needs_reference',reason='No vanilla path or original Anim.lib role identifies the source')
                    continue
                additions=set()
                overlay_additions=set()
                overlay_sets=[]
                references=[]
                for role,reference,context in comparisons:
                    added=set(current.names)-set(original_anm(reference).names)
                    additions.update(added)
                    if role.startswith('HAND_'):
                        overlay_additions.update(added)
                        overlay_sets.append(added)
                    references.append({'role':role,'path':reference,'archive':vanilla[reference][2],
                                       'library':context['library'] if context else None})
                row['references']=references
                row['added_joints']=sorted(additions)
                if not additions:
                    row['status']='unchanged_joint_set'
                    continue
                if not row['roles']:
                    row.update(status='outside_profile',reason='Not referenced by a compatible TPS library')
                    continue
                contexts=[c for _,_,c in eligible]
                if any(not set(current.names)<=c['bones'] for c in contexts):
                    row.update(status='outside_profile',reason='ANM joint paths do not match the T900S TPS skeleton')
                    continue
                plan.local_bind=True
                selected=overlay_additions & SUPPORTED_JOINTS.keys()
                if selected and any(r.startswith('HAND_') and b not in vanilla for r,b,c in eligible):
                    row.update(status='outside_profile',reason='Shared clip has an overlay role without a verified reference')
                    continue
                if selected and any(not selected <= added for added in overlay_sets):
                    row.update(status='outside_profile',reason='Shared clip has conflicting original joint sets between overlay roles')
                    continue
                if selected and any(not rotation_is_rigid(f[n]) for f in current.frames for n in selected):
                    row.update(status='outside_profile',reason='Added aiming joint contains scale/shear/reflection')
                    continue
                if selected:
                    mask=sum(1<<SUPPORTED_JOINTS[n] for n in selected)
                    for aim_path in sorted({c['aim'] for r,_,c in comparisons if r.startswith('HAND_')}):
                        plan.rules.append(AimRule(path,aim_path,mask))
                    plan.navigation=True
                    row['corrected_joints']=sorted(selected)
                    row['status']='aim_composition'
                else:
                    row['status']='local_bind_only'
            except (ValueError,KeyError,IndexError) as exc:
                # Never silently ship a structurally malformed replacement.
                raise ValueError(f'{mod}/{path}: ANM compatibility analysis failed: {exc}') from exc
        plan.report['inputs']=[{'path':k,'mod':files[k][1],'sha256':hashlib.sha256(v).hexdigest()}
                               for k,v in sorted(effective_cache.items()) if k in files]
    # Raised-rifle variants can alter existing joints only (e.g. idle), and
    # still need the AI to avoid cancelling their authored pose outside combat.
    plan.navigation=plan.navigation or bool(plan.variants)
    plan.report['rules']=[{'clip':r.clip,'aim':r.aim,'mask':r.mask} for r in plan.rules]
    plan.report['local_bind']=plan.local_bind
    plan.report['navigation']=plan.navigation
    plan.report['navigation_casts']=['T900S','T900HeavyAssault'] if plan.navigation else []
    plan.report['relaxed_pitch_casts']=['T900S'] if plan.variants else []
    plan.report['relaxed_pitch_condition']='on_foot_without_alert' if plan.variants else None
    for _,alt in plan.variants:
        row=next(a for a in plan.report['animations'] if a['path']==alt)
        if row['status'] not in ('aim_composition','unchanged_joint_set','local_bind_only'):
            raise ValueError(f'NPC variant outside the verified profile: {alt}: {row}')
    plan.report['generated_libraries']=[{'path':k,'sha256':hashlib.sha256(v).hexdigest()}
                                        for k,v in sorted(plan.generated_files.items())]
    return plan
