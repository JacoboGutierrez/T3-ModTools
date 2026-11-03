"""Bounded, read-only live diagnostics for the verified T3 1.16 memory layout.

No injected code, process writes, debugger attachment, input hooks, or focus changes.
Polling records observations, not a lossless trace of every shot or audible sample.
"""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import threading
import time
import uuid

PRISTINE_SHA256 = '52f68d5df4912aba662f0371a06ae0b1ec447ef4b7338460224b20904eb0f061'
MANAGER = 0x6907B8
SCENE_ACTORS = 0x10DF98C
SCENE_ACTOR_STRIDE = 0x14108
MAX_CAPTURE_BYTES = 128 * 1024 * 1024
HOTKEY_ID = 0x5433


def u32(data, offset=0):
    return struct.unpack_from('<I', data, offset)[0]


def text(data):
    return data.split(b'\0', 1)[0].decode('latin1')


def vector(data, offset=0):
    return [x if math.isfinite(x) else None for x in struct.unpack_from('<fff', data, offset)]


def scalar(data, offset=0):
    value = struct.unpack_from('<f', data, offset)[0]
    return value if math.isfinite(value) else None


def matrix(data, offset=0):
    return [x if math.isfinite(x) else None for x in struct.unpack_from('<16f', data, offset)]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def context_paths(game, mods=None):
    """Mirror ModManager's context paths without creating or migrating any files."""
    game = Path(game).expanduser().resolve()
    mods = Path(mods).expanduser().resolve() if mods else game/'mods'
    data = game/'modtools_data'
    state = data
    if mods != (game/'mods').resolve():
        identity = os.path.normcase(str(mods)).encode('utf-8')
        state = data/'load_orders'/hashlib.sha256(identity).hexdigest()[:16]
    return [state/'load_order.json', data/'.compiled/build_manifest.json', data/'.compiled/loader_manifest.json']


class DebugError(RuntimeError):
    pass


class WindowsReader:
    """Own one PROCESS_VM_READ | QUERY_LIMITED_INFORMATION handle."""
    def __init__(self, game):
        if os.name != 'nt':
            raise DebugError('Live capture requires Windows.')
        self.game = Path(game).resolve()
        self.handle = None
        self.kernel = C.WinDLL('kernel32', use_last_error=True)
        self.user = C.WinDLL('user32', use_last_error=True)
        signatures = {
            'OpenProcess': ([W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
            'CloseHandle': ([W.HANDLE], W.BOOL),
            'ReadProcessMemory': ([W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)], W.BOOL),
            'QueryFullProcessImageNameW': ([W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)], W.BOOL),
            'GetExitCodeProcess': ([W.HANDLE, C.POINTER(W.DWORD)], W.BOOL),
            'CreateToolhelp32Snapshot': ([W.DWORD, W.DWORD], W.HANDLE),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.kernel, name); fn.argtypes = args; fn.restype = result
        self.user.GetForegroundWindow.restype = W.HWND
        self.user.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
        self.user.GetWindowThreadProcessId.restype = W.DWORD

    def attach(self):
        original = self.game / 'T3.exe'
        if not original.is_file() or sha256(original) != PRISTINE_SHA256:
            raise DebugError('Unsupported T3.exe: this capture profile requires the verified T3 1.16 build.')

        class ProcessEntry(C.Structure):
            _fields_ = [('size', W.DWORD), ('usage', W.DWORD), ('pid', W.DWORD),
                ('heap', C.c_size_t), ('module', W.DWORD), ('threads', W.DWORD),
                ('parent', W.DWORD), ('priority', W.LONG), ('flags', W.DWORD), ('name', W.WCHAR * 260)]

        first, next_ = self.kernel.Process32FirstW, self.kernel.Process32NextW
        for fn in (first, next_):
            fn.argtypes = [W.HANDLE, C.POINTER(ProcessEntry)]; fn.restype = W.BOOL
        snapshot = self.kernel.CreateToolhelp32Snapshot(2, 0)
        if snapshot == C.c_void_p(-1).value:
            raise C.WinError(C.get_last_error())
        candidates = []
        try:
            entry = ProcessEntry(); entry.size = C.sizeof(entry)
            ok = first(snapshot, C.byref(entry))
            while ok:
                if entry.name.lower() in ('t3.exe', 't3_modded.exe'):
                    handle = self.kernel.OpenProcess(0x1010, False, entry.pid)
                    if handle:
                        path = C.create_unicode_buffer(32768); size = W.DWORD(len(path))
                        try:
                            if self.kernel.QueryFullProcessImageNameW(handle, 0, path, C.byref(size)):
                                executable = Path(path.value).resolve()
                                if executable.parent == self.game:
                                    candidates.append((entry.pid, executable))
                        finally:
                            self.kernel.CloseHandle(handle)
                ok = next_(snapshot, C.byref(entry))
        finally:
            self.kernel.CloseHandle(snapshot)
        if len(candidates) != 1:
            raise DebugError(f'Expected one running T3 game in {self.game}; found {len(candidates)}. Open a match first (same Windows privilege level as ModTools).')
        self.pid, executable = candidates[0]
        self.handle = self.kernel.OpenProcess(0x1010, False, self.pid)
        if not self.handle:
            raise C.WinError(C.get_last_error())
        try:
            # Immutable function starts establish the supported layout in memory.
            raw = original.read_bytes()
            for address, length in ((0x40E6C0, 16), (0x418040, 16),
                                    (0x48ACD0, 16), (0x4F8950, 13)):
                if self.read(address, length) != raw[address-0x400000:address-0x400000+length]:
                    raise DebugError('Live executable layout differs from the supported capture profile.')
            # Verify live audio hooks against the selected file, detecting a rebuilt
            # executable on disk while an older game instance is still running.
            installed = executable.read_bytes()
            for address, length in ((0x4183A6, 6), (0x4185A5, 7), (0x41E841, 16)):
                if self.read(address, length) != installed[address-0x400000:address-0x400000+length]:
                    raise DebugError('Running game differs from the executable on disk. Restart the game before capturing.')
            return dict(pid=self.pid, executable=str(executable), disk_executable_sha256=sha256(executable),
                pristine_sha256=PRISTINE_SHA256, profile='T3-1.16-x86-readonly-v1',
                live_audio_hooks_match_disk=True,
                disk_a2_sha256=sha256(self.game/'A2.dll') if (self.game/'A2.dll').is_file() else None)
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle); self.handle = None

    def alive(self):
        code = W.DWORD()
        return bool(self.handle and self.kernel.GetExitCodeProcess(self.handle, C.byref(code)) and code.value == 259)

    def read(self, address, length):
        if not 0 <= length <= 1024 * 1024 or not 0x10000 <= address < 0x100000000 - length:
            raise DebugError('Out-of-range live memory request.')
        buffer = C.create_string_buffer(length); got = C.c_size_t()
        if not self.kernel.ReadProcessMemory(self.handle, address, buffer, length, C.byref(got)) or got.value != length:
            raise C.WinError(C.get_last_error())
        return buffer.raw

    def uint(self, address):
        return u32(self.read(address, 4))

    def animation_snapshot(self, human):
        """Sample the Heavy's controller and pose, without assuming sound ID = scene slot.

        These reads are not frame-atomic. Owner checks reject respawn/reuse races;
        they cannot freeze animation evaluation between individual reads.
        """
        table = self.uint(SCENE_ACTORS)
        if not table:
            raise DebugError('Scene actor table is not initialized.')
        actor = None
        for slot in range(64):
            candidate = table + slot * SCENE_ACTOR_STRIDE
            if self.uint(candidate + 0x1405C) == human:
                actor = candidate
                break
        if actor is None:
            raise DebugError('Human has no matching scene actor in the 64 supported slots.')
        controller = actor + 0x0C
        bone_controller = actor + 0xD0
        state = self.read(controller + 0x13A88, 0xF0)
        channels = self.read(bone_controller, 0x360)
        library, count = u32(channels, 0x350), u32(channels, 0x358)
        if count > 4096 or (count and not library):
            raise DebugError('Invalid animation library during snapshot.')

        def record(index):
            if index >= count:
                return None
            raw = self.read(library + index * 0xA8, 0xA8)
            return dict(id=u32(raw), path=text(raw[8:136]))

        result = dict(scene_slot=slot, movement_state=self.uint(human + 0x0C),
            previous_movement_state=u32(state, 0x98), speed=scalar(state, 0xB8),
            in_motion=bool(state[0x94]), left_right=scalar(state), up_down=scalar(state, 4),
            world_matrix=matrix(state, 8), upper_body_id=u32(state, 0xB0),
            spine_id=u32(state, 0xB4), channels=[], bones=[])
        for index, role in enumerate(('legs', 'spine', 'hands')):
            offset = index * 0x64
            current, target = u32(channels, offset + 0x64), u32(channels, offset + 0x60)
            result['channels'].append(dict(channel=index, role=role,
                current_index=current, target_index=target, fading=bool(channels[offset + 0x74]),
                current=record(current), target=record(target)))
        primitive = u32(state, 0xEC)
        if primitive:
            header = self.read(primitive + 0x40, 8)
            bone_count, bones = u32(header), u32(header, 4)
            result['bone_count'] = bone_count
            # This profile is restricted to the Heavy's verified 32-bone skeleton.
            if bone_count == 32 and bones:
                raw = self.read(bones, bone_count * 0x278)
                for index in range(bone_count):
                    offset = index * 0x278
                    name = u32(raw, offset + 8)
                    result['bones'].append(dict(index=index,
                        name=text(self.read(name, 256)) if name else None,
                        global_matrix=matrix(raw, offset + 0x58)))
            else:
                result['pose_unavailable'] = 'Expected the Heavy 32-bone skeleton.'
        else:
            result['pose_unavailable'] = 'Character primitive is not initialized.'
        if self.uint(SCENE_ACTORS) != table or self.uint(actor + 0x1405C) != human:
            raise DebugError('Scene actor ownership changed during animation snapshot.')
        return result

    def add_animation_snapshot(self, actor, human):
        if human and actor.get('stable') and actor.get('cast') == 'T900HeavyAssault':
            try:
                actor['animation'] = self.animation_snapshot(human)
            except (OSError, DebugError) as exc:
                actor['animation_read_error'] = str(exc)

    def snapshot(self):
        foreground_pid = W.DWORD()
        self.user.GetWindowThreadProcessId(self.user.GetForegroundWindow(), C.byref(foreground_pid))
        result = dict(tick=self.uint(0x114C1E8), foreground=foreground_pid.value == self.pid)
        # Menus and loading screens may have no initialized actor/sample tables.
        data = self.read(MANAGER, 0x4DB00)
        result.update(sound_enabled=bool(data[0x1E724]), sound_engine_active=bool(data[0x1E725]),
            effects_volume=u32(data, 0x1E6BC), listener=vector(data, 0x1E72C))
        sample_table = self.uint(0x1160CB0)
        samples = {}
        if sample_table:
            raw = self.read(sample_table, 512 * 0xAC)
            samples = {i: dict(pointer=u32(raw, i*0xAC), path=text(raw[i*0xAC+4:i*0xAC+132]))
                for i in range(512) if u32(raw, i*0xAC)}
        result['samples'] = samples
        result['banks'] = [dict(slot=i, subtype=u32(data, 0x14514+i*0x58),
            name=text(data[0x144D4+i*0x58:0x14514+i*0x58]))
            for i in range(32) if data[0x144D0+i*0x58]]
        actors = []
        for slot in range(32):
            at = 0xD114 + slot*0xB4
            if not data[at]:
                continue
            actor = dict(slot=slot, id=u32(data, at+0x28), cast=text(data[at+0x74:at+0xB4]),
                native_audible=bool(data[at+1]), position=vector(data, at+0x2C))
            try:
                count = u32(data, at+0x1C)
                if count > 4096:
                    raise DebugError('Invalid actor sound count during snapshot.')
                actor['sound_samples'] = list(struct.unpack('<'+'i'*count, self.read(u32(data, at+8), count*4))) if count else []
                # Fire records connect a per-actor sample selection to its weapon
                # sound bank, volume and distance settings. Bound unusual tables.
                records_count = min(count, 512)
                records = self.read(u32(data, at+4), records_count*0x430) if records_count else b''
                actor['fire_sounds'] = []
                if count > records_count: actor['sound_records_truncated'] = True
                for index in range(records_count):
                    record = records[index*0x430:(index+1)*0x430]
                    if record[0] in (6, 7):
                        sample_id = actor['sound_samples'][index]
                        actor['fire_sounds'].append(dict(kind=record[0], bank=u32(record, 0x2B0),
                            sample_id=sample_id, path=samples.get(sample_id, {}).get('path'),
                            volume=u32(record, 0x290), distance_min=scalar(record, 0x2A8),
                            distance_max=scalar(record, 0x2AC)))
                human = u32(data, at+0x24)
                if human:
                    control = self.uint(human+0x2C)
                    selected = self.uint(human+0x40)
                    if control and selected < 8:
                        definition = self.uint(human+0x48+selected*8)
                        actor['weapon'] = text(self.read(self.uint(definition+4), 128)) if definition else None
                        actor['fire_requested'] = list(self.read(control+0x28, 2))
                        actor['modes'] = []
                        for offset in (0x84, 0x88):
                            option = self.uint(control+offset)
                            if not option:
                                actor['modes'].append(None); continue
                            raw = self.read(option, 0x70)
                            actor['modes'].append(dict(subtype=u32(raw, 0x20), ammo=u32(raw, 8),
                                dual_marker=u32(raw, 0x40) == 0x80000000,
                                cooldown=scalar(raw), state=u32(raw, 0x6C)))
                    actor['stable'] = self.uint(MANAGER+at+0x24) == human
                    self.add_animation_snapshot(actor, human)
            except (OSError, DebugError) as exc:
                actor['read_error'] = str(exc)
            actors.append(actor)
        result['actors'] = actors
        head = u32(data, 0x4D8C0)
        result['queue_head'] = head
        result['recent_events'] = []
        if head < 1024:
            for distance in range(1, 17):
                slot = (head-distance) % 1024; at = 0x328C0+slot*0x6C
                result['recent_events'].append(dict(slot=slot, pending=bool(data[at+4]),
                    accepted=bool(data[at+5]), kind=u32(data, at+8), tick=u32(data, at+12),
                    owner=u32(data, at+20), subtype=u32(data, at+88)))
        fmod = self.uint(0x6755E0)
        if fmod:
            count = self.uint(fmod+0xAD4)
            if not 0 <= count <= 2048:
                raise DebugError('Invalid FMOD channel count during snapshot.')
            raw = self.read(self.uint(fmod+0xAA8), count*0x1B8) if count else b''
            sample_names = {s['pointer']: s['path'] for s in samples.values()}
            result['audio'] = dict(capacity=count, software=self.uint(fmod+0xAD8),
                hardware=self.uint(fmod+0xADC), master_volume=self.uint(fmod+0x10), assigned_channels=[])
            for i in range(count):
                at = i*0x1B8; sample = u32(raw, at+0x5C)
                if sample:
                    flags = u32(raw, at+0x3C)
                    software_backend = u32(raw, at+0x19C) == 0x589956
                    result['audio']['assigned_channels'].append(dict(slot=i, handle=u32(raw, at+0x14),
                        sample=sample_names.get(sample), priority=u32(raw, at+0x38), flags=flags,
                        volume=u32(raw, at+0x1C), muted=bool(flags & 2), paused=bool(flags & 16),
                        software_backend=software_backend,
                        software_volume=u32(raw, at+0x28) if software_backend else None,
                        software_mix_gains=[u32(raw, at+offset) for offset in (0x6C, 0x70, 0x74)] if software_backend else None,
                        position=vector(raw, at+0x44)))
        return result


def capture(game, duration, interval_ms, stop, emit=lambda event: None, reader_factory=WindowsReader,
            context_files=None):
    """Run on a worker. Always finalize a readable partial report on failure/stop."""
    duration, interval_ms = float(duration), int(interval_ms)
    if not math.isfinite(duration) or not 1 <= duration <= 3600 or not 50 <= interval_ms <= 2000:
        raise ValueError('Duration: 1..3600 seconds; interval: 50..2000 milliseconds.')
    game = Path(game).resolve()
    if not (game/'T3.exe').is_file():
        raise DebugError('Select the game installation folder first.')
    directory = game/'modtools_data/debug'/f'{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}'
    directory.mkdir(parents=True)
    metadata = dict(format_version=1, audio_detail_version=2, animation_detail_version=1,
        started_utc=datetime.now(timezone.utc).isoformat(),
        duration_seconds=duration, interval_ms=interval_ms, read_only=True,
        limitations=['Polling can miss short events and does not count every shot.',
                    'Assigned FMOD channels do not prove audible playback.',
                    'Immediate fire dispatch can bypass the native event queue.',
                    'Hashes describe files on disk; only selected live code signatures/hooks are compared.',
                    'Heavy animation channels and bone matrices are sampled, not frame-atomic.',
                    'Asynchronous actor changes and loading screens can produce partial snapshots.'])
    summary = dict(samples=0, read_errors=0, actor_read_errors=0, animation_read_errors=0, max_read_ms=0,
                   reason='error', weapons={}, elapsed_seconds=0)
    reader = None; start = time.monotonic()
    try:
        paths = context_files if context_files is not None else context_paths(game)
        metadata['context_sources'] = {}
        for path in map(Path, paths):
            if path.is_file() and path.stat().st_size <= 4*1024*1024:
                (directory/path.name).write_bytes(path.read_bytes())
                metadata['context_sources'][path.name] = str(path)
        reader = reader_factory(game)
        metadata.update(reader.attach())
        (directory/'metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        emit(dict(state='capturing', directory=str(directory)))
        start = time.monotonic(); consecutive_errors = 0; previous = {}
        with (directory/'samples.jsonl').open('w', encoding='utf-8') as stream:
            while not stop.is_set() and time.monotonic()-start < duration:
                if not reader.alive():
                    summary['reason'] = 'game_closed'; break
                read_start = time.monotonic()
                try:
                    row = reader.snapshot(); consecutive_errors = 0
                    summary['actor_read_errors'] += sum(bool(a.get('read_error')) for a in row.get('actors', []))
                    summary['animation_read_errors'] += sum(bool(a.get('animation_read_error')) for a in row.get('actors', []))
                    current = {}
                    for actor in row.get('actors', []):
                        name = actor.get('weapon')
                        if not name or actor.get('stable') is False or actor.get('read_error'):
                            continue
                        item = summary['weapons'].setdefault(name, dict(observations=0, ammo_decreases=0, actors=[]))
                        item['observations'] += 1
                        if actor['id'] not in item['actors']: item['actors'].append(actor['id'])
                        modes = actor.get('modes') or []
                        for mode, option in enumerate(modes):
                            if not option: continue
                            key = (actor['id'], name, mode); ammo = option['ammo']
                            if key in previous and ammo < previous[key]: item['ammo_decreases'] += previous[key]-ammo
                            current[key] = ammo
                    previous = current
                except (OSError, DebugError) as exc:
                    row = dict(read_error=str(exc)); summary['read_errors'] += 1; consecutive_errors += 1
                    previous = {}
                row['elapsed_seconds'] = round(time.monotonic()-start, 4)
                row['read_ms'] = round((time.monotonic()-read_start)*1000, 3)
                summary['max_read_ms'] = max(summary['max_read_ms'], row['read_ms'])
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n'); stream.flush()
                summary['samples'] += 1
                if stream.tell() >= MAX_CAPTURE_BYTES:
                    summary['reason'] = 'size_limit'; break
                if consecutive_errors >= 20:
                    summary['reason'] = 'read_errors'; break
                if summary['samples'] % max(1, 1000//interval_ms) == 0:
                    emit(dict(state='progress', elapsed=row['elapsed_seconds'], samples=summary['samples']))
                stop.wait(min(interval_ms/1000, max(0, duration-(time.monotonic()-start))))
            else:
                summary['reason'] = 'stopped' if stop.is_set() else 'duration'
    except Exception as exc:
        summary['error'] = str(exc)
    finally:
        if reader:
            try: reader.close()
            except OSError as exc: summary['close_error'] = str(exc)
        summary['elapsed_seconds'] = round(time.monotonic()-start, 4)
        metadata['finished_utc'] = datetime.now(timezone.utc).isoformat()
        (directory/'metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        # Bounded tail only; never copy profiles, unrelated files or full dumps.
        log = game/'debug.log'
        try:
            if log.is_file():
                with log.open('rb') as source:
                    source.seek(max(0, log.stat().st_size-256*1024))
                    (directory/'debug_tail.log').write_bytes(source.read(256*1024))
        except OSError as exc: summary['log_error'] = str(exc)
        (directory/'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        emit(dict(state='finished', directory=str(directory), summary=summary))
    return directory, summary


class GlobalHotkey:
    """Register one OS hotkey on its own message-loop thread; no keyboard hooks."""
    def __init__(self, events, function_key='F9'):
        self.events = events; self.function_key = function_key
        self.stop_event = threading.Event(); self.thread = None

    def start(self):
        if self.function_key not in ('F8', 'F9', 'F10', 'F11'):
            raise ValueError('Unsupported capture hotkey.')
        self.thread = threading.Thread(target=self._run, name='T3 debug hotkey', daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread: self.thread.join(timeout=1)

    def _run(self):
        try:
            self._message_loop()
        except Exception as exc:
            self.events.put(dict(state='hotkey_error', error=str(exc)))

    def _message_loop(self):
        if os.name != 'nt':
            self.events.put(dict(state='hotkey_error', error='Global hotkeys require Windows.')); return
        user = C.WinDLL('user32', use_last_error=True)
        user.RegisterHotKey.argtypes = [W.HWND, C.c_int, W.UINT, W.UINT]
        user.RegisterHotKey.restype = W.BOOL
        user.UnregisterHotKey.argtypes = [W.HWND, C.c_int]
        user.UnregisterHotKey.restype = W.BOOL
        user.PeekMessageW.argtypes = [C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT, W.UINT]
        user.PeekMessageW.restype = W.BOOL
        key = 0x70 + int(self.function_key[1:])-1
        if not user.RegisterHotKey(None, HOTKEY_ID, 0x4000 | 2 | 4, key):
            self.events.put(dict(state='hotkey_error', error='Hotkey unavailable. Choose another function key.')); return
        self.events.put(dict(state='hotkey_ready'))
        try:
            message = W.MSG()
            while not self.stop_event.wait(0.05):
                while user.PeekMessageW(C.byref(message), None, 0x312, 0x312, 1):
                    if message.wParam == HOTKEY_ID:
                        self.events.put(dict(state='toggle'))
        finally:
            user.UnregisterHotKey(None, HOTKEY_ID)
