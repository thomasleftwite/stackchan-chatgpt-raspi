"""First Linux conversation-host UI; keys are session-only."""
import queue
import threading
import tkinter as tk
from tkinter import ttk

from raspi.host import make_service


class HostWindow:
    def __init__(self, root, factory=make_service):
        self.root = root; self.factory = factory; self.worker = None; self.closing = False
        self.events = queue.Queue(); self.stop = threading.Event()
        root.title('スタックちゃん — Raspberry Piホスト'); root.geometry('720x420')
        frame = ttk.Frame(root, padding=24); frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='端末専用APでホストを起動します。有線インターネットを使用します。').pack(anchor='w')
        self.fixture = tk.BooleanVar(value=True)
        self.fixture_box = ttk.Checkbutton(frame, text='APIを使わず接続だけ確認（無音応答）',
            variable=self.fixture, command=self.controls)
        self.fixture_box.pack(anchor='w', pady=12)
        self.key = tk.StringVar(); self.model = tk.StringVar(value='gemini-3.8-live')
        ttk.Label(frame, text='Gemini APIキー（今回の起動中だけ使用、保存しません）').pack(anchor='w')
        self.key_box = ttk.Entry(frame, textvariable=self.key, show='●'); self.key_box.pack(fill='x', pady=5)
        ttk.Label(frame, text='Gemini Liveモデル').pack(anchor='w')
        self.model_box = ttk.Entry(frame, textvariable=self.model); self.model_box.pack(fill='x', pady=5)
        ttk.Label(frame, text='接続確認を外すと、端末からの質問時にGemini APIを使用します。').pack(anchor='w', pady=10)
        self.status = tk.StringVar(value='停止中。接続確認、またはAPIキーを指定して開始してください。')
        ttk.Label(frame, textvariable=self.status, wraplength=660).pack(anchor='w', pady=12)
        buttons = ttk.Frame(frame); buttons.pack(anchor='e')
        self.start_button = ttk.Button(buttons, text='開始', command=self.start); self.start_button.pack(side='left', padx=5)
        self.stop_button = ttk.Button(buttons, text='停止', command=self.stop.set); self.stop_button.pack(side='left')
        self.controls(); root.protocol('WM_DELETE_WINDOW', self.close); root.after(100, self.pump)

    def controls(self):
        busy = self.worker is not None and self.worker.is_alive()
        self.start_button.configure(state='disabled' if busy else 'normal')
        self.stop_button.configure(state='normal' if busy else 'disabled')
        self.fixture_box.configure(state='disabled' if busy else 'normal')
        state = 'disabled' if busy or self.fixture.get() else 'normal'
        self.key_box.configure(state=state); self.model_box.configure(state=state)

    def start(self):
        if self.worker is not None and self.worker.is_alive(): return
        fixture = self.fixture.get(); key = self.key.get() if not fixture else ''; model = self.model.get()
        self.key.set(''); self.stop = threading.Event(); self.status.set('起動中…')
        # The stop button must reference the current event, not the previous run's event.
        self.stop_button.configure(command=self.stop.set)
        def run():
            try:
                service = self.factory(fixture=fixture, key=key, model=model)
                service.run(self.stop, self.events.put)
            except Exception: self.events.put({'event': 'failed'})
            finally: self.events.put({'event': 'finished'})
        self.worker = threading.Thread(target=run, daemon=False); self.worker.start(); self.controls()

    def pump(self):
        labels = {'ready': '待受中。端末からの接続を受け付けます。', 'device-online': '端末からの接続を確認しました。',
            'session-busy': '質問・回答を処理しています。', 'session-idle': '待受中。',
            'turn-failed': '応答に失敗しました。APIキー・利用制限・接続状態を確認してください。',
            'failed': '起動できませんでした。AP・Node環境・APIキーを確認してください。',
            'stopped': '停止しました。'}
        while True:
            try: event = self.events.get_nowait()
            except queue.Empty: break
            if event.get('event') in labels:
                text = labels[event['event']]
                if event.get('event') == 'turn-failed':
                    text = {'AUTH': 'APIキーの認証に失敗しました。', 'QUOTA': 'APIの利用制限に達しました。',
                        'MODEL': '指定したモデルを利用できません。', 'TIMEOUT': '応答が時間切れになりました。'}.get(event.get('code'), text)
                self.status.set(text)
        self.controls()
        if self.closing and (self.worker is None or not self.worker.is_alive()):
            self.root.destroy(); return
        self.root.after(100, self.pump)

    def close(self):
        self.closing = True; self.key.set(''); self.stop.set()


def main():
    root = tk.Tk(); HostWindow(root); root.mainloop()
