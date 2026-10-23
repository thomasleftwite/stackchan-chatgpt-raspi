"""Voice review UI, with stopped-host audition and no PCM in the event queue."""
import threading
import tkinter as tk
from tkinter import ttk

from raspi.voice_preview import FAILURES, generate_sample, play_pcm
from raspi.voice_settings import REVIEW_REASONS, VoiceSettings


class VoiceUi:
    def init_voices(self, settings=None, generator=generate_sample, player=play_pcm):
        self.settings = settings if settings is not None else VoiceSettings()
        self.generator = generator; self.player = player
        self.preview_worker = None; self.preview_cancel = threading.Event(); self.preview_job = None
        self.heard = set(); self.preview_id = 0; self.review_dialog = None; self.preview_key_box = None
        self.sleep_confirmed = tk.BooleanVar(value=False)
        self.preview_status = tk.StringVar(value='試聴はPiの既定の音声出力から流れ、Gemini APIを使用します。')

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
        height = min(560, self.root.winfo_screenheight()-80)
        x = self.root.winfo_rootx()+self.root.winfo_width()+20
        if x+width > self.root.winfo_screenwidth()-20: x = self.root.winfo_rootx()+40
        x = max(0, min(x, self.root.winfo_screenwidth()-width-20))
        y = max(0, min(self.root.winfo_rooty()+20, self.root.winfo_screenheight()-height-40))
        dialog.geometry(f'{width}x{height}+{x}+{y}')
        def destroyed(event):
            if event.widget is dialog and self.review_dialog is dialog: self.review_dialog = None
        dialog.bind('<Destroy>', destroyed, add='+')
        frame = ttk.Frame(dialog, padding=18); frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Gemini APIキー（試聴ごとに入力、保存しません）').pack(anchor='w')
        self.preview_key_box = ttk.Entry(frame, textvariable=self.key, show='●')
        self.preview_key_box.pack(fill='x', pady=(4, 8))
        model = self.model.get(); candidate = tk.StringVar()
        ttk.Combobox(frame, textvariable=candidate, values=self.settings.candidates(model), state='readonly').pack(fill='x', pady=6)
        ttk.Label(frame, text='ホストを停止し、端末をSleepingにしてから試聴してください。\n最後まで聴いて日本語が適切なら採用します。採用した声だけが通常の一覧に入ります。', wraplength=650).pack(anchor='w', pady=6)
        ttk.Checkbutton(frame, text='端末をSleepingにしました', variable=self.sleep_confirmed).pack(anchor='w')
        ttk.Button(frame, text='日本語サンプルを生成して聴く（Gemini API使用）',
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
        if not self.sleep_confirmed.get():
            self.preview_status.set('端末をSleepingにしてチェックを入れてください。'); return
        if self.fixture.get() or model != self.model.get() or voice not in self.settings.candidates(model):
            self.preview_status.set('接続確認のチェックを外し、モデルと候補の声を確認してください。'); return
        key = self.key.get().strip()
        if not key:
            self.preview_status.set('この画面の非表示欄へAPIキーを入力してください。'); return
        self.key.set(''); self.preview_cancel = threading.Event(); self.preview_id += 1
        job = (self.preview_id, model, voice); self.preview_job = job
        self.heard.discard((model, voice))
        self.preview_status.set('日本語サンプルを生成しています…')
        cancel = self.preview_cancel
        def work():
            pcm = None; ok = False; code = 'TRANSPORT'
            try:
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

    def stop_preview(self):
        self.preview_cancel.set()
        if self.preview_job is not None: self.preview_status.set('試聴を停止しています…')

    def preview_event(self, event):
        job = self.preview_job
        if job is None or event.get('id') != job[0]: return
        if event.get('internal') == 'preview-playing':
            if not self.preview_cancel.is_set(): self.preview_status.set('Piで日本語サンプルを再生しています…')
            return
        if event.get('internal') != 'preview-ended': return
        if event.get('ok') and not self.preview_cancel.is_set():
            self.heard.add((job[1], job[2])); self.preview_status.set('試聴完了。日本語を確認して採用・除外してください。')
        elif self.preview_cancel.is_set(): self.preview_status.set('試聴を停止しました。採用確認は行いません。')
        else:
            text = {'PC_AUDIO': 'Piで再生できません。音声出力先・音声デバイスを確認してください。',
                'AUTH': 'APIキーの認証に失敗しました。', 'QUOTA': 'APIの利用制限に達しました。',
                'TIMEOUT': '試聴が時間切れになりました。', 'MODEL': 'このモデルを利用できません。'}
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
