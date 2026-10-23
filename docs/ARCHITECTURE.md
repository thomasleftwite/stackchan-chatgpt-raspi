# アーキテクチャと移植境界

## データフロー

ESP32-S3 (16kHz PCM) → Wi-Fi AP → Raspberry Pi TCP 48443 HTTP/WS → Node.js `server/wireless-host.ts` → Gemini Live WSS → Node.js → ESP32-S3 (24kHz PCM)

## 再利用するコンポーネント

- `server/wireless-host.ts`: 標準入力JSON `{host,port,subnet}` で待受先を指定。まず変更せず動作検証。
- `server/gemini-server.ts`, `server/gemini-*`, `server/voice-control.ts`, `server/voice-preview.ts`: 原則再利用。
- `desktop/voices.py` と声レビュー処理: OS依存のない部分を抽出できるか検討。

### API不要の起動・停止検証

`wireless-host.ts` は `fixture:true`（boolean）、`host:"127.0.0.1"`、`subnet:"127.0.0.1/32"` の組合せに限り、ループバックでの試験起動を許可する。実APIキー・秘密設定を読み込まず、固定の無音PCMを返す。通常起動でのループバックや、fixtureによる全インターフェース/公開IP待受は拒否する。既存のprivate IPv4/AP側の起動条件は維持する。

実プロセステストは専用ポートを使い、終了時に自身の子プロセスを回収する。端末や音声デバイスを使わないため、この成功をAP接続・実音声・Gemini応答の証明とはしない。

## Windows依存の差し替え候補

| 現行ファイル | Windows依存 | Raspberry Pi対応案 |
| --- | --- | --- |
| desktop/network.py | PowerShell / Wi-Fi Direct検出 | APインターフェースとIPv4/サブネットをLinuxで列挙。上流側を誤選択しない |
| desktop/wireless.py | `node.exe`, LOCALAPPDATA, Windowsプロセスフラグ | `/usr/bin/env node` または明示的実行パス、Linuxのプロセス停止 |
| desktop/settings.py | `ctypes.WinDLL('crypt32')` DPAPI, LOCALAPPDATA | Linux用設定保存と任意の秘密保護、権限・XDG対応 |
| desktop/voice_preview.py | `winmm` PCM再生 | ALSA/PipeWire等で24kHz mono PCMを再生、停止可能にする |
| desktop/host_app.py | Windows固有UI文言、`node.exe`存在検査、ランタイム展開 | Linux UI/CLIエントリ、Linux用バックエンドの注入 |

## ネットワークの必須条件

現行端末はDHCPゲートウェイをホストと認識するため、単にRaspberry Piと端末を同じ家庭内Wi-Fiに接続するだけでは互換性を満たさない。端末側APのゲートウェイをPiにする必要がある。

AP側のみでlistenし、同一サブネットの接続元だけ許可する。通常経路にはアプリ独自TLS/Bearer認証がなく、Wi-Fi参加者を信頼境界とする。SSID/パスワードを安全に管理し、ゲスト接続を禁止する。

## 配布・ランタイム

初期版はソース起動（Python venv + Node/npm）。PyInstaller/パッケージングは動作確認後に検討。ARM64対応済みバイナリを前提にせず、Pi上で依存を解決する。

## 参考

- https://github.com/thomasleftwite/stackchan-chatgpt/blob/main/desktop/network.py
- https://github.com/thomasleftwite/stackchan-chatgpt/blob/main/desktop/wireless.py
- https://github.com/thomasleftwite/stackchan-chatgpt/blob/main/desktop/settings.py
- https://github.com/thomasleftwite/stackchan-chatgpt/blob/main/desktop/voice_preview.py
- https://github.com/thomasleftwite/stackchan-chatgpt/blob/main/server/wireless-host.ts
