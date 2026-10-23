# アーキテクチャと移植境界

## データフロー

ESP32-S3 (16kHz PCM) → Wi-Fi AP → Raspberry Pi TCP 48443 HTTP/WS → Node.js `server/wireless-host.ts` → Gemini Live WSS → Node.js → ESP32-S3 (24kHz PCM)

## 再利用するコンポーネント

- `server/wireless-host.ts`: 標準入力JSON `{host,port,subnet,fixture?}` で待受先を指定。通常のAP待受と、明示したfixtureに限るループバック検証に対応。
- `server/gemini-server.ts`, `server/gemini-*`, `server/voice-control.ts`, `server/voice-preview.ts`: 原則再利用。
- `desktop/voices.py` のカタログと評価理由を再利用。Linuxの権限・保存・再生は `raspi/voice_*.py` に隔離する。

### API不要の起動・停止検証

`wireless-host.ts` は `fixture:true`（boolean）、`host:"127.0.0.1"`、`subnet:"127.0.0.1/32"` の組合せに限り、ループバックでの試験起動を許可する。実APIキー・秘密設定を読み込まず、固定の無音PCMを返す。通常起動でのループバックや、fixtureによる全インターフェース/公開IP待受は拒否する。既存のprivate IPv4/AP側の起動条件は維持する。

実プロセステストは専用ポートを使い、終了時に自身の子プロセスを回収する。端末や音声デバイスを使わないため、この成功をAP接続・実音声・Gemini応答の証明とはしない。

## 実装済みLinuxホスト

- `raspi/host_network.py`: NetworkManagerのAP/sharedと一意なprivate IPv4/サブネットを読み取る。設定変更は行わない。
- `raspi/host.py`: ARM64 Nodeを起動し、標準入力で待受設定を渡す。キーは明示入力のセッション内だけで保持し、子の環境へ渡す。EOF→SIGTERM→SIGKILLで自身のプロセスグループを回収する。
- `raspi/host_ui.py`: Tkinterで声選択・開始/停止・通信/会話モニターを表示。声カタログは既存serverのJSONを共有し、稼働中の変更は有界キューから既存stdin voiceコマンドへ渡す。確認応答は安全なrequest IDだけをGUIへ返し、進行中の回答は既存VoiceControlのスナップショットを維持する。初期状態はAPI不要のfixture。Live利用時のキーはアプリ終了まで非表示のメモリ内で再利用し、明示消去または終了時に削除する。ファイルへ保存しない。
- 端末モニターは既存health/セッション開始/再生完了イベントの受信時刻を保持。既存端末は一度成功したhealthを再送しないため、30秒以上未受信なら定期通知なし・現在の接続は判定できない旨を示し、端末の画面状態やWi-Fi切断を断定しない。履歴は固定文言80件に限定し、provider本文・PCM・声の選択値を記録しない。
- `raspi/provision*.py`: 端末WiFiManager経由の接続先設定とPi AP復帰。実機設定の変更は承認済みの操作範囲に限る。

- `raspi/voice_preview.py`: 既存の`server/dist/voice-preview.js`を停止中ホストの別プロセスとして呼び出す。明示入力キーを子の環境にだけ渡し、stdoutを650000 bytes、PCMを480000 bytes（24kHz mono S16_LE・最大10秒）に制限。48秒で生成を打ち切り、終了時は自身のプロセスグループを回収する。PCMはファイルへ保存せずALSAのaplayへ渡し、再生・中断後にバッファを消去する。
- `raspi/voice_ui.py`: ホスト停止中・端末Sleeping確認後の明示操作で生成/再生。試聴中はホストの開始を禁止し、再生完了した候補だけ採用可能。通常一覧は採用済みの声とサービス既定。稼働中の選択変更は既存voiceコマンドを使用し、使用中の声の除外はホストを停止する。
- `raspi/voice_settings.py`: XDGの専用ディレクトリ700・ファイル600で声の評価と選択だけ保存。カタログrevision/モデルを照合。原子的置換とfsync、サイズ/権限/シンボリックリンク検証、破損時の明示再評価による原本保全・復旧を提供。GUIとCLIは同じ保存選択を読む。

Windows用desktopと既存serverは変更しない。LinuxのAPIキー永続保護と、稼働中ホストでの試聴は今後の実装とする。

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


## 端末での声試聴（2026-10-23）

- 利用者の指定により、RasPi版の既定の試聴先を端末へ変更。通常ホストを停止し、`server/device-preview-host.ts`を同じAP IP/TCP 48443で1回だけ起動する。待受条件は`host-boundary.ts`に抽出し、通常のwireless-hostと同じprivate AP/厳密fixture境界を共有する。
- 端末は既存ファームのReady→長押し→一言の録音で通信を開始する。サーバーから端末を起動する命令や新しい端末プロトコルは追加しない。GUIはこの操作を案内し、120秒で試聴待受を打ち切る。
- `server/device-preview.ts`は受信した入力PCMをすぐに消去し、既存VoiceControl.previewの固定テキストを生成する。SDK/生成ワーカーへ録音を渡さない。既存createGeminiServerの出力フレーム/credit/drain/playedを使って24kHz PCMを返す。
- 既存gemini-serverに任意のonDisconnectコールバックを追加し、通常会話のbusy解除とは独立に端末切断を検出する。端末試聴では生成中の切断でAbortSignalを発火し、遅れて返るPCMも消去する。通常の呼出元は未指定のままで動作を維持する。
- 専用ホストのstdoutは固定イベントとrequest ID/失敗分類だけ。PCMをPython/GUIへ渡さず、preview-playedとsession-idleの両方を受けてから親が停止・回収する。切断・中断・期限切れを成功扱いしない。終了時は生成ワーカーを含む自身のプロセスグループを回収する。
- `raspi.host.make_device_preview_service`、VoiceUiの端末バックエンドを追加。通常ホスト/試聴を排他にし、再生完了通知後だけ声評価のheardを付ける。採用/除外・XDG保存は従来と同じ。Piローカル試聴は任意の補助経路として保持。
- 端末ファーム、Windows製品コード、実機ネットワーク設定は変更しない。共通の待受境界抽出は通常会話を含むNode全54件で回帰確認。
