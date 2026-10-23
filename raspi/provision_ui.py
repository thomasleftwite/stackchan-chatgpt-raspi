"""Small Linux setup window. Secrets travel only over the helper's stdin."""
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk


def main():
    root = tk.Tk(); root.title('スタックちゃん — 端末のWi-Fi設定'); root.geometry('670x330')
    frame = ttk.Frame(root, padding=24); frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='端末のWiFiManagerから、このPiのAPへ接続先を設定します。').pack(anchor='w')
    ttk.Label(frame, text='Wi-Fiは一時的に端末設定用へ切り替わり、完了後にAPへ戻ります。').pack(anchor='w', pady=5)
    ttk.Label(frame, text='インターネット接続は有線のまま維持します。').pack(anchor='w')
    ssid = tk.StringVar(value='Stackchan-Setup'); password = tk.StringVar()
    ttk.Label(frame, text='端末の設定用SSID').pack(anchor='w', pady=(15, 0))
    ttk.Entry(frame, textvariable=ssid).pack(fill='x')
    ttk.Label(frame, text='端末の設定用パスワード').pack(anchor='w', pady=(8, 0))
    ttk.Entry(frame, textvariable=password, show='●').pack(fill='x')
    status = tk.StringVar(value='端末をWi-Fi設定画面にしてから実行してください。')
    ttk.Label(frame, textvariable=status, wraplength=610).pack(anchor='w', pady=10)
    events = queue.Queue(); busy = False

    def start():
        nonlocal busy
        if busy: return
        request = json.dumps({'ssid': ssid.get(), 'password': password.get()})
        password.set(''); busy = True; button.configure(state='disabled')
        status.set('端末へ設定中です。APの復帰までしばらくお待ちください。')
        def worker():
            try:
                result = subprocess.run(['sudo', '-n', sys.executable, '-m', 'raspi.provision', '--execute-stdin'],
                    cwd=Path(__file__).resolve().parents[1], input=request, capture_output=True,
                    text=True, timeout=170)
                value = json.loads(result.stdout)
                events.put(value if result.returncode == 0 or value.get('event') == 'failed' else {'event': 'failed'})
            except Exception: events.put({'event': 'failed'})
        threading.Thread(target=worker, daemon=False).start()

    def poll():
        nonlocal busy
        try:
            value = events.get_nowait(); busy = False; button.configure(state='normal')
            message = '設定を完了できませんでした。端末の設定画面・パスワードとPiのAP状態を確認してください。'
            if value.get('code') == 'AP_RESTORE_FAILED':
                message = 'APへ復帰できませんでした。有線接続を維持したまま、PiのAP状態を確認してください。'
            if value.get('code') == 'WIRED_REQUIRED':
                message = '有線のインターネット接続を確認できないため、設定を開始しませんでした。'
            if value.get('event') == 'complete':
                message = '設定を送信し、PiのAPへ復帰しました。端末の接続を確認してください。'
            status.set(message)
        except queue.Empty: pass
        root.after(100, poll)

    def close():
        if not busy: root.destroy()
    button = ttk.Button(frame, text='端末の接続先をこのPiへ設定', command=start); button.pack(anchor='e')
    root.protocol('WM_DELETE_WINDOW', close); root.after(100, poll); root.mainloop()
