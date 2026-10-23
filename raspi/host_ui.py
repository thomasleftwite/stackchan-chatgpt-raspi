"""Linux host controls and communication monitor; no private event payloads."""
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from raspi.host import make_service, make_device_preview_service, public_event
from raspi.voice_ui import VoiceUi
from raspi.voice_preview import generate_sample, play_pcm
from raspi.key_store import KeyStore

LABELS = {
    'ready': '待受中。端末からの接続を受け付けます。',
    'device-online': '端末からの通信を確認しました。',
    'session-busy': '質問・回答を処理しています。',
    'session-idle': '待受中。',
    'turn-complete': '回答の生成が完了しました。端末へ送信しています。',
    'voice-played': '端末から再生完了を受信しました。',
    'turn-failed': '応答に失敗しました。APIキー・利用制限・接続状態を確認してください。',
    'failed': '起動・実行に失敗しました。AP・Node環境・APIキーを確認してください。',
    'stopped': '停止しました。',
    'voice-selected': '声の変更を受け付けました。次の質問から反映します。',
    'voice-failed': '声を変更できませんでした。選択とモデルを確認してください。',
}
FAILURE_LABELS = {'AUTH': 'APIキーの認証に失敗しました。', 'QUOTA': 'APIの利用制限に達しました。',
    'MODEL': '指定したモデルを利用できません。', 'TIMEOUT': '応答が時間切れになりました。'}


class HostWindow(VoiceUi):
    def __init__(self, root, factory=make_service, clock=time.monotonic, *, settings=None,
                 generator=generate_sample, player=play_pcm, device_factory=make_device_preview_service, key_store=None):
        self.root = root; self.factory = factory; self.clock = clock
        self.worker = None; self.closing = False; self.stopping = False
        self.init_voices(settings, generator, player, device_factory)
        self.events = queue.Queue(); self.commands = queue.Queue(maxsize=32)
        self.stop = threading.Event(); self.request_id = 0
        self.last_seen = None; self.host_ready = False; self.failed = False
        root.title('スタックちゃん — Raspberry Piホスト'); root.geometry('760x760')
        frame = ttk.Frame(root, padding=24); frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='端末専用APでホストを起動します。有線インターネットを使用します。').pack(anchor='w')
        self.fixture = tk.BooleanVar(value=True)
        self.fixture_box = ttk.Checkbutton(frame, text='APIを使わず接続だけ確認（無音応答）',
            variable=self.fixture, command=self.controls)
        self.fixture_box.pack(anchor='w', pady=12)
        self.key_store = key_store if key_store is not None else KeyStore()
        self.key = tk.StringVar(); self.model = tk.StringVar(value='gemini-3.8-live')
        self.key_status = tk.StringVar()
        try:
            self.key.set(self.key_store.load())
            self.key_status.set('保存済みキーを復元しました。' if self.key.get() else '入力後に保存、または開始・試聴時に自動保存します。')
        except Exception: self.key_status.set('保存キーを復元できません。権限を確認するか、保存キーを削除して再設定してください。')
        ttk.Label(frame, text='Gemini APIキー（Pi内に暗号化保存・次回起動時に復元）').pack(anchor='w')
        self.key_box = ttk.Entry(frame, textvariable=self.key, show='●'); self.key_box.pack(fill='x', pady=5)
        key_buttons = ttk.Frame(frame); key_buttons.pack(anchor='w')
        self.save_key_button = ttk.Button(key_buttons, text='APIキーを保存・更新', command=self.save_key)
        self.save_key_button.pack(side='left')
        self.clear_key_button = ttk.Button(key_buttons, text='保存キーを削除', command=self.clear_key)
        self.clear_key_button.pack(side='left', padx=8)
        ttk.Label(frame, textvariable=self.key_status, wraplength=700).pack(anchor='w')
        ttk.Label(frame, text='Gemini Liveモデル').pack(anchor='w')
        self.model_box = ttk.Entry(frame, textvariable=self.model); self.model_box.pack(fill='x', pady=5)
        self.model.trace_add('write', lambda *_: self.refresh_voices())
        ttk.Label(frame, text='声（サービス既定、または日本語の採用済み）').pack(anchor='w')
        self.voice = tk.StringVar(value=self.settings.selected(self.model.get()) or 'サービス既定')
        self.voice_box = ttk.Combobox(frame, textvariable=self.voice, state='readonly')
        self.voice_box.pack(fill='x', pady=5)
        self.voice_box.bind('<<ComboboxSelected>>', self.choose_voice)
        self.voice_status = tk.StringVar(value='採用した声と選択を保存します。音声は保存しません。')
        ttk.Label(frame, textvariable=self.voice_status, wraplength=700).pack(anchor='w')
        self.review_button = ttk.Button(frame, text='声を試聴・採用・保存', command=self.review_voices)
        self.review_button.pack(anchor='w', pady=5)
        if self.settings.load_error:
            self.voice_status.set('声設定を読み込めません。原本を保持し、明示的な再評価で復旧できます。')
        ttk.Label(frame, text='接続確認を外すと、端末からの質問時にGemini APIを使用します。').pack(anchor='w', pady=8)
        buttons = ttk.Frame(frame); buttons.pack(anchor='w')
        self.start_button = ttk.Button(buttons, text='ホストサービスを開始', command=self.start)
        self.start_button.pack(side='left', padx=(0, 8))
        self.stop_button = ttk.Button(buttons, text='停止', command=self.request_stop); self.stop_button.pack(side='left')
        self.status = tk.StringVar(value='停止中。接続確認、またはAPIキーを指定して開始してください。')
        ttk.Label(frame, textvariable=self.status, wraplength=700).pack(anchor='w', pady=10)
        monitor = ttk.LabelFrame(frame, text='端末の状態モニター', padding=10); monitor.pack(fill='x')
        self.host_status = tk.StringVar(value='ホスト：停止中')
        self.device_status = tk.StringVar(value='端末：ホスト停止中')
        self.session_status = tk.StringVar(value='会話：待機')
        for value in (self.host_status, self.device_status, self.session_status):
            ttk.Label(monitor, textvariable=value).pack(anchor='w')
        self.history = tk.Text(frame, height=7, state='disabled', wrap='word')
        self.history.pack(fill='both', expand=True, pady=(10, 0))
        self.refresh_voices(); self.controls()
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.after_id = root.after(100, self.pump)
        root.bind('<Destroy>', self.destroyed, add='+')

    def running(self):
        return self.worker is not None and self.worker.is_alive()

    def refresh_voices(self):
        values = ('サービス既定',) + self.settings.approved(self.model.get())
        self.voice_box.configure(values=values)
        if self.voice.get() not in values: self.voice.set(self.settings.selected(self.model.get()) or 'サービス既定')

    def controls(self):
        busy = self.running(); locked = self.closing or self.stopping or self.preview_running() or self.preview_job is not None
        self.start_button.configure(state='disabled' if busy or locked else 'normal')
        self.stop_button.configure(state='normal' if busy and not locked else 'disabled')
        self.fixture_box.configure(state='disabled' if busy or locked else 'normal')
        state = 'disabled' if busy or self.fixture.get() or locked else 'normal'
        self.key_box.configure(state=state); self.model_box.configure(state=state)
        self.clear_key_button.configure(state='disabled' if busy or locked else 'normal')
        self.save_key_button.configure(state='disabled' if busy or locked else 'normal')
        if self.preview_key_box is not None and self.preview_key_box.winfo_exists():
            self.preview_key_box.configure(state='disabled' if busy or locked else 'normal')
        if self.preview_target_box is not None and self.preview_target_box.winfo_exists():
            self.preview_target_box.configure(state='disabled' if busy or locked else 'readonly')
        self.voice_box.configure(state='disabled' if self.fixture.get() or locked else 'readonly')
        self.review_button.configure(state='disabled' if self.closing else 'normal')
        # The provider's default cannot be restored by a voice command; restart to use it.
        self.voice_box.configure(values=self.settings.approved(self.model.get()) if busy else
            ('サービス既定',) + self.settings.approved(self.model.get()))

    def choose_voice(self, _event=None):
        if self.preview_running() or self.preview_job is not None or self.closing or self.stopping: return
        voice = '' if self.voice.get() == 'サービス既定' else self.voice.get()
        try: self.settings.select(self.model.get(), voice)
        except Exception:
            self.voice_status.set('声の選択を保存できません。採用評価と設定ファイルの権限を確認してください。'); return
        if not self.running():
            self.voice_status.set('選択した声を次のホスト起動で使用します。'); return
        if self.stopping or self.closing: return
        self.request_id += 1
        try: self.commands.put_nowait({'id': self.request_id, 'voice': self.voice.get()})
        except queue.Full:
            self.voice_status.set('変更待ちが多いため受け付けられません。少し待って選び直してください。'); return
        self.voice_status.set('声の変更を送信中です。進行中の回答の声は変わりません。')

    def save_key(self):
        if self.running() or self.preview_running() or self.preview_job is not None or self.closing: return False
        try: self.key_store.save(self.key.get().strip())
        except Exception:
            self.key_status.set('APIキーを保存できません。入力と保存先の権限を確認してください。処理は開始していません。')
            return False
        self.key.set(self.key.get().strip())
        self.key_status.set('APIキーを暗号化して保存しました。変更・削除するまで再利用します。')
        return True

    def clear_key(self):
        if self.running() or self.preview_running() or self.preview_job is not None or self.closing: return
        try: self.key_store.delete()
        except Exception:
            self.key_status.set('保存キーを削除できません。保存先の権限を確認してください。'); return
        self.key.set(''); self.key_status.set('保存キーを削除しました。')

    def start(self):
        if self.running() or self.closing or self.preview_running() or self.preview_job is not None: return
        # Finish handling the previous run before resetting the monitor.
        while True:
            try: self.handle_event(self.events.get_nowait())
            except queue.Empty: break
        fixture = self.fixture.get(); key = self.key.get() if not fixture else ''; model = self.model.get()
        voice = '' if self.voice.get() == 'サービス既定' else self.voice.get()
        if not fixture and voice and voice not in self.settings.approved(model):
            self.status.set('声を試聴して採用するか、サービス既定を選択してください。'); return
        if not fixture and not self.settings.load_error:
            try: self.settings.select(model, voice)
            except Exception:
                self.status.set('声の選択を保存できませんでした。設定ファイルの権限を確認してください。'); return
        if not fixture and not self.save_key():
            self.status.set('APIキーを保存できないため開始していません。'); return
        if not fixture: key = self.key.get()
        self.stop = threading.Event(); self.commands = queue.Queue(maxsize=32)
        self.stopping = False; self.failed = False; self.host_ready = False; self.last_seen = None
        self.status.set('起動中…'); self.host_status.set('ホスト：起動中'); self.session_status.set('会話：待機')
        def run():
            try:
                service = self.factory(fixture=fixture, key=key, model=model, voice=voice)
                service.run(self.stop, self.events.put, commands=self.commands)
            except Exception: self.events.put({'event': 'failed'})
            finally: self.events.put({'event': 'finished'})
        self.worker = threading.Thread(target=run, daemon=False); self.worker.start(); self.controls()

    def request_stop(self):
        if not self.running(): return
        self.stopping = True; self.stop.set(); self.status.set('停止しています…')
        self.host_status.set('ホスト：停止処理中'); self.controls()

    def log(self, text):
        # Only fixed labels enter history. Never copy raw event/provider payloads.
        self.history.configure(state='normal')
        self.history.insert('end', time.strftime('%H:%M:%S') + ' ' + text + '\n')
        if int(self.history.index('end-1c').split('.')[0]) > 81: self.history.delete('1.0', '2.0')
        self.history.see('end'); self.history.configure(state='disabled')

    def handle_event(self, raw):
        if isinstance(raw, dict) and raw.get('internal') in ('preview-playing', 'preview-ended', 'preview-waiting', 'preview-generating', 'preview-output'):
            self.preview_event(raw); return
        if isinstance(raw, dict) and raw.get('event') == 'finished':
            self.host_ready = False; self.host_status.set('ホスト：停止中（エラー）' if self.failed else 'ホスト：停止中')
            self.session_status.set('会話：待機'); return
        event = public_event(raw)
        if event is None: return
        kind = event['event']
        if kind not in LABELS: return
        text = LABELS[kind]
        if kind == 'turn-failed': text = FAILURE_LABELS.get(event.get('code'), text)
        if kind == 'ready':
            self.host_ready = True
            if not self.stopping: self.host_status.set('ホスト：待受中')
        if kind in ('device-online', 'session-busy', 'voice-played'):
            self.last_seen = self.clock()
        if kind == 'session-busy': self.session_status.set('会話：質問・回答を処理中')
        elif kind == 'turn-complete': self.session_status.set('会話：端末へ音声送信中')
        elif kind == 'voice-played': self.session_status.set('会話：端末の再生完了')
        elif kind == 'session-idle': self.session_status.set('会話：待機')
        elif kind == 'turn-failed': self.session_status.set('会話：応答失敗')
        elif kind == 'failed': self.failed = True
        elif kind == 'stopped':
            self.host_ready = False; self.host_status.set('ホスト：停止中')
        if kind in ('voice-selected', 'voice-failed'):
            if kind == 'voice-failed' or event.get('id') == self.request_id: self.voice_status.set(text)
        elif not (kind == 'stopped' and self.failed) and not (self.stopping and kind not in ('stopped', 'failed')):
            self.status.set(text)
        self.log(text)

    def update_monitor(self):
        if self.preview_job is not None and self.preview_job[3] == '端末':
            self.host_status.set('ホスト：端末試聴モード')
            self.device_status.set('端末：試聴画面の案内に従って操作してください。'); return
        if not self.running(): self.host_status.set('ホスト：停止中（エラー）' if self.failed else 'ホスト：停止中')
        if not self.host_ready:
            self.device_status.set('端末：ホスト停止中' if not self.running() else '端末：ホストの待受開始を待っています')
        elif self.last_seen is None: self.device_status.set('端末：通信待ち（未確認）')
        else:
            age = max(0, int(self.clock() - self.last_seen))
            # Existing terminals cache a successful health check; idle time is not a heartbeat timeout.
            label = '通信を確認' if age < 30 else '定期通知なし（現在の接続は判定できません）'
            self.device_status.set(f'端末：{label} / 最終受信 {age}秒前')

    def cancel_pump(self):
        if self.after_id is not None:
            self.root.after_cancel(self.after_id); self.after_id = None

    def destroyed(self, event):
        if event.widget is self.root: self.cancel_pump()

    def pump(self):
        self.cancel_pump()
        while True:
            try: event = self.events.get_nowait()
            except queue.Empty: break
            self.handle_event(event)
        if not self.running(): self.stopping = False
        self.update_monitor(); self.controls()
        if self.closing and not self.running() and not self.preview_running() and self.preview_job is None: self.root.destroy(); return
        self.after_id = self.root.after(100, self.pump)

    def close(self):
        self.closing = True; self.key.set(''); self.stop_preview(); self.request_stop(); self.controls()


def main():
    root = tk.Tk(); HostWindow(root); root.mainloop()
