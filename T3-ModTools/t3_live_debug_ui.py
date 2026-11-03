"""Tk controls for read-only capture. Workers communicate exclusively via queues."""
from pathlib import Path
import math
import queue
import threading
import tkinter as tk
from tkinter import ttk

from t3_live_debug import capture, GlobalHotkey, context_paths
from t3_modding import open_in_file_manager


STRINGS = {
    'en': dict(title='Live debug', duration='Duration (seconds)', interval='Sample interval (ms)',
        hotkey='Enable global shortcut: Ctrl+Shift+', start='Start capture', stop='Stop capture',
        folder='Open report folder', ready='Ready. Open a match, then press the shortcut.',
        note='Technical records only. Keep this panel open; you can minimize ModTools. '
             'Sampling can miss short events. Assigned audio channels do not prove audible playback.',
        armed='Shortcut available.', unarmed='Shortcut disabled; the capture button still works.',
        conflict='Shortcut unavailable. Choose another key or use the button.',
        starting='Connecting to the game…', stopping='Stopping and saving…',
        progress='{elapsed:.0f} / {duration:g} seconds — {samples} samples',
        done='Capture finished: {reason}. {samples} samples.',
        error='Capture failed: {error}', invalid='Use 1–3600 seconds and 50–2000 ms.',
        busy='Wait for the current ModTools operation to finish.',
        duration_reason='duration reached', stopped='manual stop', game_closed='game closed',
        size_limit='128 MiB limit reached', read_errors='repeated read errors', error_reason='error'),
    'es': dict(title='Debug en vivo', duration='Duración (segundos)', interval='Intervalo de muestreo (ms)',
        hotkey='Activar atajo global: Ctrl+Shift+', start='Iniciar captura', stop='Detener captura',
        folder='Abrir carpeta del registro', ready='Listo. Abrí una partida y pulsá el atajo.',
        note='Solo registro técnico. Dejá este panel abierto; podés minimizar ModTools. '
             'El muestreo puede omitir eventos breves. Un canal de audio asignado no confirma que se escuche.',
        armed='Atajo disponible.', unarmed='Atajo desactivado; podés usar el botón de captura.',
        conflict='Atajo no disponible. Elegí otra tecla o usá el botón.',
        starting='Conectando con el juego…', stopping='Deteniendo y guardando…',
        progress='{elapsed:.0f} / {duration:g} segundos — {samples} muestras',
        done='Captura finalizada: {reason}. {samples} muestras.',
        error='Falló la captura: {error}', invalid='Usá 1–3600 segundos y 50–2000 ms.',
        busy='Esperá a que termine la operación actual de ModTools.',
        duration_reason='duración cumplida', stopped='parada manual', game_closed='juego cerrado',
        size_limit='límite de 128 MiB', read_errors='errores de lectura repetidos', error_reason='error'),
    'pt': dict(title='Debug ao vivo', duration='Duração (segundos)', interval='Intervalo de amostragem (ms)',
        hotkey='Ativar atalho global: Ctrl+Shift+', start='Iniciar captura', stop='Parar captura',
        folder='Abrir pasta do registro', ready='Pronto. Abra uma partida e pressione o atalho.',
        note='Somente registro técnico. Mantenha este painel aberto; pode minimizar o ModTools. '
             'A amostragem pode perder eventos curtos. Um canal atribuído não confirma áudio audível.',
        armed='Atalho disponível.', unarmed='Atalho desativado; use o botão de captura.',
        conflict='Atalho indisponível. Escolha outra tecla ou use o botão.',
        starting='Conectando ao jogo…', stopping='Parando e salvando…',
        progress='{elapsed:.0f} / {duration:g} segundos — {samples} amostras',
        done='Captura concluída: {reason}. {samples} amostras.',
        error='Falha na captura: {error}', invalid='Use 1–3600 segundos e 50–2000 ms.',
        busy='Aguarde a operação atual do ModTools terminar.',
        duration_reason='duração atingida', stopped='parada manual', game_closed='jogo fechado',
        size_limit='limite de 128 MiB', read_errors='erros de leitura repetidos', error_reason='erro'),
    'ru': dict(title='Отладка в игре', duration='Длительность (секунды)', interval='Интервал опроса (мс)',
        hotkey='Глобальное сочетание: Ctrl+Shift+', start='Начать запись', stop='Остановить запись',
        folder='Открыть папку отчёта', ready='Готово. Откройте матч и нажмите сочетание клавиш.',
        note='Только технический журнал. Оставьте панель открытой; ModTools можно свернуть. '
             'Опрос может пропускать короткие события. Назначенный аудиоканал не подтверждает слышимость.',
        armed='Сочетание доступно.', unarmed='Сочетание отключено; используйте кнопку записи.',
        conflict='Сочетание недоступно. Выберите другую клавишу или используйте кнопку.',
        starting='Подключение к игре…', stopping='Остановка и сохранение…',
        progress='{elapsed:.0f} / {duration:g} секунд — {samples} снимков',
        done='Запись завершена: {reason}. Снимков: {samples}.',
        error='Ошибка записи: {error}', invalid='Допустимо: 1–3600 секунд и 50–2000 мс.',
        busy='Дождитесь завершения текущей операции ModTools.',
        duration_reason='время истекло', stopped='остановлено вручную', game_closed='игра закрыта',
        size_limit='лимит 128 МиБ', read_errors='повторные ошибки чтения', error_reason='ошибка'),
}


class LiveDebugPanel:
    def __init__(self, root, game, mods, language='en', busy=lambda: False,
                 set_busy=lambda value: None, capture_fn=capture, hotkey_factory=GlobalHotkey):
        self.root = root; self.game = game; self.mods = mods
        self.busy = busy; self.set_busy = set_busy
        self.capture_fn = capture_fn; self.hotkey_factory = hotkey_factory
        self.strings = STRINGS.get(language, STRINGS['en'])
        self.events = queue.Queue(); self.hotkey_events = queue.Queue()
        self.hotkey = None; self.worker = None; self.stop_event = threading.Event()
        self.active = False; self.closed = False; self.closing = False; self.directory = None
        self.window = tk.Toplevel(root); self.window.title(self.t('title'))
        self.window.resizable(False, False)
        frame = ttk.Frame(self.window, padding=16); frame.grid()
        self.duration = tk.StringVar(value='120'); self.interval = tk.StringVar(value='100')
        self.key = tk.StringVar(value='F9'); self.enabled = tk.BooleanVar(value=True)
        self.controls = []
        for row, (label, variable, low, high) in enumerate((
                ('duration', self.duration, 1, 3600), ('interval', self.interval, 50, 2000))):
            ttk.Label(frame, text=self.t(label)).grid(row=row, column=0, sticky='w', pady=4)
            control = ttk.Spinbox(frame, from_=low, to=high, textvariable=variable, width=12)
            control.grid(row=row, column=1, sticky='w'); self.controls.append(control)
        self.check = ttk.Checkbutton(frame, text=self.t('hotkey'), variable=self.enabled,
                                     command=self.configure_hotkey)
        self.check.grid(row=2, column=0, sticky='w', pady=8)
        self.key_box = ttk.Combobox(frame, textvariable=self.key, values=('F8', 'F9', 'F10', 'F11'),
                                   state='readonly', width=10)
        self.key_box.grid(row=2, column=1, sticky='w')
        self.key_box.bind('<<ComboboxSelected>>', lambda event: self.configure_hotkey())
        self.hotkey_status = tk.StringVar()
        ttk.Label(frame, textvariable=self.hotkey_status, wraplength=530).grid(row=3, column=0, columnspan=2, sticky='w')
        ttk.Label(frame, text=self.t('note'), wraplength=530).grid(row=4, column=0, columnspan=2, pady=12, sticky='w')
        self.status = tk.StringVar(value=self.t('ready'))
        ttk.Label(frame, textvariable=self.status, wraplength=530).grid(row=5, column=0, columnspan=2, sticky='w')
        self.path_label = tk.StringVar()
        ttk.Label(frame, textvariable=self.path_label, wraplength=530).grid(row=6, column=0, columnspan=2, pady=8, sticky='w')
        self.start_button = ttk.Button(frame, text=self.t('start'), command=self.toggle)
        self.start_button.grid(row=7, column=0, sticky='w', pady=4)
        self.folder_button = ttk.Button(frame, text=self.t('folder'), command=self.open_folder, state='disabled')
        self.folder_button.grid(row=7, column=1, sticky='w')
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.configure_hotkey()
        self.after_id = self.root.after(100, self.poll)

    def t(self, key, **values):
        return self.strings[key].format(**values)

    def show(self):
        if not self.closing:
            self.window.deiconify(); self.window.lift()

    def configure_hotkey(self):
        if self.hotkey: self.hotkey.close()
        self.hotkey = None; self.hotkey_events = queue.Queue()
        self.hotkey_status.set(self.t('unarmed'))
        if self.enabled.get():
            self.hotkey = self.hotkey_factory(self.hotkey_events, self.key.get())
            self.hotkey.start()

    def toggle(self):
        if self.closed or self.closing: return
        if self.active:
            self.stop_event.set(); self.status.set(self.t('stopping'))
            return
        if self.busy():
            self.status.set(self.t('busy')); return
        try:
            duration = float(self.duration.get()); interval = int(self.interval.get())
            if not math.isfinite(duration) or not 1 <= duration <= 3600 or not 50 <= interval <= 2000:
                raise ValueError()
        except ValueError:
            self.status.set(self.t('invalid')); return
        # Snapshot settings on the UI thread. Never read Tk variables from a worker.
        try:
            game = Path(self.game()).expanduser().resolve()
            context = context_paths(game, self.mods())
        except (OSError, ValueError) as exc:
            self.status.set(self.t('error', error=str(exc))); return
        self.capture_duration = duration
        self.active = True; self.stop_event = threading.Event(); self.set_busy(True)
        for widget in self.controls: widget.configure(state='disabled')
        self.start_button.configure(text=self.t('stop'))
        self.status.set(self.t('starting'))

        def work():
            try:
                self.capture_fn(game, duration, interval, self.stop_event, self.events.put, context_files=context)
            except Exception as exc:
                self.events.put(dict(state='failed', error=str(exc)))
        self.worker = threading.Thread(target=work, name='T3 live capture', daemon=False)
        self.worker.start()

    def poll(self):
        if self.closed: return
        for source in (self.hotkey_events, self.events):
            while True:
                try: event = source.get_nowait()
                except queue.Empty: break
                state = event['state']
                if state == 'toggle': self.toggle()
                elif state == 'hotkey_ready': self.hotkey_status.set(self.t('armed'))
                elif state == 'hotkey_error': self.hotkey_status.set(self.t('conflict'))
                elif state == 'capturing':
                    self.directory = event['directory']; self.path_label.set(self.directory)
                    self.folder_button.configure(state='normal')
                    self.status.set(self.t('progress', elapsed=0, duration=self.capture_duration, samples=0))
                elif state == 'progress' and not self.stop_event.is_set():
                    self.status.set(self.t('progress', duration=self.capture_duration, **{k:event[k] for k in ('elapsed','samples')}))
                elif state in ('finished', 'failed'):
                    self.active = False; self.set_busy(False)
                    for widget in self.controls: widget.configure(state='normal')
                    self.start_button.configure(text=self.t('start'))
                    summary = event.get('summary', {})
                    if event.get('directory'):
                        self.directory = event['directory']; self.path_label.set(self.directory)
                        self.folder_button.configure(state='normal')
                    error = event.get('error') or summary.get('error')
                    if error: self.status.set(self.t('error', error=error))
                    else:
                        reason = summary['reason']
                        label = reason+'_reason' if reason in ('duration', 'error') else reason
                        self.status.set(self.t('done', reason=self.strings.get(label, reason), samples=summary['samples']))
                    if self.closing:
                        self.dispose(); return
        self.after_id = self.root.after(100, self.poll)

    def open_folder(self):
        if self.directory:
            try: open_in_file_manager(Path(self.directory))
            except OSError as exc: self.status.set(self.t('error', error=str(exc)))

    def close(self):
        self.closing = True; self.stop_event.set()
        if self.hotkey: self.hotkey.close(); self.hotkey = None
        if self.active:
            self.window.withdraw()  # Poll until the partial report is saved, then release busy state.
        else: self.dispose()

    def dispose(self):
        if self.closed: return
        self.closed = True; self.stop_event.set()
        if self.hotkey: self.hotkey.close(); self.hotkey = None
        try:
            self.root.after_cancel(self.after_id); self.window.destroy()
        except tk.TclError: pass
