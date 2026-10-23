"""Voice review UI, with stopped-host audition and no PCM in the event queue."""
import threading
import tkinter as tk
from tkinter import ttk

from raspi.voice_preview import FAILURES, generate_sample, play_pcm
from raspi.host import make_device_preview_service
from raspi.voice_settings import REVIEW_REASONS, VoiceSettings


class VoiceUi:
    def init_voices(self, settings=None, generator=generate_sample, player=play_pcm, device_factory=make_device_preview_service):
        self.settings = settings if settings is not None else VoiceSettings()
        self.generator = generator; self.player = player; self.device_factory = device_factory
        self.preview_service_stop = threading.Event()
        self.preview_target = tk.StringVar(value='端末'); self.preview_target_box = None
        self.preview_worker = None; self.preview_cancel = threading.Event(); self.preview_job = None
        self.heard = set(); self.preview_id = 0; self.review_dialog = None; self.preview_key_box = None
        self.sleep_confirmed = tk.BooleanVar(value=False)
        self.preview_status = tk.StringVar(value='端末で日本語サンプルを試聴します。Gemini APIを使用します。')

    def preview_running(self):
        return self.preview_worker is not None and self.preview_worker.is_alive()

    def review_voices(self):
        if self.closing: return
        self.root.deiconify(); self.root.lift()
        if self.review_dialog is not None and self.review_dialog.winfo_exists():
            self.review_dialog.deiconify(); self.review_dialog.lift(); self.review_dialog.focus_set(); return
        dialog = tk.Toplevel(self.root); self.review_dialog = dialog
        dialog.title('日本語の声を試聴・採用'); dialog.transient(self.root)
        self.root.update_idletasks()
        width = min(700, self.root.winfo_screenwidth()-40)
        height = min(640, self.root.winfo_screenheight()-80)
        x = self.root.winfo_rootx()+self.root.winfo_width()+20
        if x+width > self.root.winfo_screenwidth()-20: x = self.root.winfo_rootx()+40
        x = max(0, min(x, self.root.winfo_screenwidth()-width-20))
        y = max(0, min(self.root.winfo_rooty()+20, self.root.winfo_screenheight()-height-40))
        dialog.geometry(f'{width}x{height}+{x}+{y}')
        def destroyed(event):
            if event.widget is dialog and self.review_dialog is dialog: self.review_dialog = None
        dialog.bind('<Destroy>', destroyed, add='+')
        frame = ttk.Frame(dialog, padding=18); frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Gemini APIキー（アプリ終了まで保持、ファイル保存なし）').pack(anchor='w')
        self.preview_key_box = ttk.Entry(frame, textvariable=self.key, show='●')
        self.preview_key_box.pack(fill='x', pady=(4, 8))
        ttk.Label(frame, text='試聴先').pack(anchor='w')
        self.preview_target_box = ttk.Combobox(frame, textvariable=self.preview_target,
            values=('端末', 'Pi（ローカル）'), state='readonly')
        self.preview_target_box.pack(fill='x', pady=4)
        ttk.Label(frame, text='候補の声').pack(anchor='w')
        model = self.model.get(); candidate = tk.StringVar()
        ttk.Combobox(frame, textvariable=candidate, values=self.settings.candidates(model), state='readonly').pack(fill='x', pady=6)
        ttk.Label(frame, text='ホストを停止して試聴を準備します。Sleepingなら短押しで起こしてReadyにし、\n約2秒長押しして離し、「テスト」など一言話してください。録音はAPIへ送らず破棄します。\n再生後、日本語が適切なら採用してください。', wraplength=650).pack(anchor='w', pady=6)
        ttk.Checkbutton(frame, text='Piで聴く場合のみ：端末をSleepingにしました', variable=self.sleep_confirmed).pack(anchor='w')
        ttk.Button(frame, text='選択した試聴先で準備（Gemini API使用）',
            command=lambda: self.start_preview(model, candidate.get())).pack(anchor='w', pady=6)
        ttk.Button(frame, text='試聴を停止', command=self.stop_preview).pack(anchor='w', pady=4)
        reason = tk.StringVar(value=REVIEW_REASONS['approved'][0])
        ttk.Label(frame, text='採用・除外の理由').pack(anchor='w')
        ttk.Combobox(frame, textvariable=reason, values=REVIEW_REASONS['approved']+REVIEW_REASONS['excluded'], state='readonly').pack(fill='x', pady=6)
        ttk.Button(frame, text='日本語に適する：採用して保存',
            command=lambda: self.decide_voice(model, candidate.get(), True, reason.get())).pack(anchor='w', pady=4)
        ttk.Button(frame, text='日本語に適さない：除外して保存',
            command=lambda: self.decide_voice(model, candidate.get(), False, reason.get())).pack(anchor='w', pady=4)
        ttk.Label(frame, textvariable=self.preview_status, wraplength=650).pack(anchor='w', pady=10)
        def close(): self.stop_preview(); dialog.destroy()
        dialog.protocol('WM_DELETE_WINDOW', close)
        dialog.lift(); dialog.focus_set()

    def start_preview(self, model, voice):
        if self.closing or self.preview_running() or self.preview_job is not None: return
        if self.running():
            self.preview_status.set('先にホストサービスを停止してください。'); return
        target = self.preview_target.get()
        if target not in ('端末', 'Pi（ローカル）'): return
        if target != '端末' and not self.sleep_confirmed.get():
            self.preview_status.set('端末をSleepingにしてチェックを入れてください。'); return
        if self.fixture.get() or model != self.model.get() or voice not in self.settings.candidates(model):
            self.preview_status.set('接続確認のチェックを外し、モデルと候補の声を確認してください。'); return
        key = self.key.get().strip()
        if not key:
            self.preview_status.set('この画面の非表示欄へAPIキーを入力してください。'); return
        self.preview_cancel = threading.Event(); self.preview_id += 1
        job = (self.preview_id, model, voice, target); self.preview_job = job
        self.preview_service_stop = threading.Event()
        self.heard.discard((model, voice))
        self.preview_status.set('端末用の試聴ホストを起動しています…' if target == '端末' else '日本語サンプルを生成しています…')
        cancel = self.preview_cancel
        def work():
            pcm = None; ok = False; code = 'TRANSPORT'
            try:
                if target == '端末':
                    ok, code = self.run_device_preview(key, model, voice, job[0], cancel)
                    return
                pcm = self.generator(key, model, voice, job[0], cancel)
                if not cancel.is_set():
                    self.events.put({'internal': 'preview-playing', 'id': job[0]})
                    ok = self.player(pcm, cancel)
                    code = '' if ok else ('CANCELLED' if cancel.is_set() else 'PC_AUDIO')
            except Exception as error:
                value = str(error) if isinstance(error, ValueError) else ''
                code = value if value in FAILURES else 'TRANSPORT'
            finally:
                if pcm is not None: pcm[:] = b'\0'*len(pcm)
                self.events.put({'internal': 'preview-ended', 'id': job[0], 'ok': bool(ok), 'code': code})
        self.preview_worker = threading.Thread(target=work, daemon=False)
        self.preview_worker.start(); self.controls()

    def run_device_preview(self, key, model, voice, request_id, cancel):
        played = False; code = 'TIMEOUT'
        stop = self.preview_service_stop
        service = self.device_factory(key=key, model=model, voice=voice, request_id=request_id)
        def event(value):
            nonlocal played, code
            kind = value.get('event')
            if kind == 'ready': stage = 'preview-waiting'
            elif value.get('id') != request_id: stage = None
            elif kind == 'preview-generating': stage = 'preview-generating'
            elif kind == 'preview-output': stage = 'preview-output'
            else: stage = None
            if stage: self.events.put({'internal': stage, 'id': request_id})
            if value.get('id') == request_id:
                if kind == 'preview-played': played = True; code = ''
                elif kind == 'preview-failed':
                    failure = value.get('code')
                    code = failure if failure in FAILURES else 'TRANSPORT'; stop.set()
            # Wait for terminal protocol completion/close before shutting down the host.
            if played and kind == 'session-idle': stop.set()
        service.run(stop, event, duration=130)
        return played and not cancel.is_set(), code

    def stop_preview(self):
        self.preview_cancel.set(); self.preview_service_stop.set()
        if self.preview_job is not None: self.preview_status.set('試聴を停止しています…')

    def preview_event(self, event):
        job = self.preview_job
        if job is None or event.get('id') != job[0]: return
        stage = event.get('internal')
        if stage in ('preview-waiting', 'preview-generating', 'preview-output'):
            text = {'preview-waiting': 'Sleepingなら短押しで起こしてReadyにし、約2秒長押し→離して「テスト」など一言話してください。',
                'preview-generating': '固定の日本語サンプルを生成しています。録音は破棄しました。',
                'preview-output': '端末へサンプルを送信中です。端末の再生完了を待っています。'}
            if not self.preview_cancel.is_set(): self.preview_status.set(text[stage])
            return
        if event.get('internal') == 'preview-playing':
            if not self.preview_cancel.is_set(): self.preview_status.set('Piで日本語サンプルを再生しています…')
            return
        if event.get('internal') != 'preview-ended': return
        if event.get('ok') and not self.preview_cancel.is_set():
            self.heard.add((job[1], job[2])); self.preview_status.set(
                '端末の再生完了を確認しました。聞こえた日本語を確認して採用・除外してください。'
                if job[3] == '端末' else '試聴完了。日本語を確認して採用・除外してください。')
        elif self.preview_cancel.is_set(): self.preview_status.set('試聴を停止しました。採用確認は行いません。')
        else:
            text = {'PC_AUDIO': 'Piで再生できません。音声出力先・音声デバイスを確認してください。',
                'AUTH': 'APIキーの認証に失敗しました。', 'QUOTA': 'APIの利用制限に達しました。',
                'TIMEOUT': '試聴が時間切れになりました。端末の開始操作と接続を確認してください。',
                'INTERRUPTED': '端末との接続が中断しました。採用せず、接続後に再試行してください。', 'MODEL': 'このモデルを利用できません。'}
            self.preview_status.set(text.get(event.get('code'), '試聴できませんでした。APIキー・接続・設定を確認してください。'))
        self.preview_job = None

    def decide_voice(self, model, voice, approved, reason):
        if self.closing or self.preview_running() or self.preview_job is not None:
            self.preview_status.set('試聴の終了を待ってください。'); return
        if model != self.model.get(): return
        heard = (model, voice) in self.heard
        if approved and not heard:
            self.preview_status.set('先にこの声のサンプルを最後まで試聴してください。'); return
        was_active = self.voice.get() == voice
        try: self.settings.decide(model, voice, approved, reason, heard=heard)
        except Exception:
            self.preview_status.set('声の評価を保存できませんでした。理由・設定ファイルの権限を確認してください。'); return
        self.refresh_voices()
        if approved:
            self.voice.set(voice); self.choose_voice()
            self.preview_status.set('採用して保存しました。次回起動でも選択を復元します。')
        else:
            if was_active:
                self.voice.set('サービス既定')
                if self.running(): self.request_stop()
            self.preview_status.set('通常の一覧から除外して保存しました。')
