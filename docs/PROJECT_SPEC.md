# PROJECT_SPEC — Raspberry Pi版チャットホスト

更新: 2026-10-23 / 状態: Draft v0.2

## 目的とスコープ

- Raspberry Pi 5 / Debian GNU/Linux 13 (trixie) / ARM64 で既存Stackchan音声対話ホストを動作させる。
- 既存Windows版 0.6.0-rc.1 の通信仕様・Gemini Live連携・声の試聴/採用・1質問1回答を可能な限り維持。
- ESP32-S3側のファームウェア、Wi-Fi保存領域、呼びかけ登録データは変更しない。例外: 2026-10-23、利用者は新しいPi APへ接続するため、端末の設定画面で接続先Wi-Fiだけを更新することを承認した。保存領域の消去や呼びかけ登録の変更は行わない。
- Windows版への変更は必要最小限。Linux専用実装を `raspi/` に配置し、共通化は互換性テストを通してから行う。

## 現行版から確認した事実

- 端末: M5AtomS3R + Atomic Voice Base A149。
- ホスト: Python/Tkinter UI + Node.js/TypeScriptサーバー、Gemini Live。
- 通常接続: 2.4GHz Wi-Fi、端末がDHCPゲートウェイのTCP 48443へHTTP/WS接続。
- 入力: 16kHz、16bit、mono PCM。出力: 24kHz PCM。半二重、1質問1回答。
- 端末内ウェイクワード検出。通常時USB操作不要。
- Gemini APIキーはホスト内で管理し、端末へ送らない。
- Windows側の秘密保存はDPAPI。Linuxでは同じ実装は使えない。

## 機能要件

FR-01: 現行ファームウェアと互換性のあるHTTP/WSを提供する。
FR-02: 端末ネットワーク側IPとサブネットのみで待ち受ける。上流LANに公開しない。
FR-03: Gemini Liveへの中継、PCMフォーマット、時間制限、例外分類を保持する。
FR-04: GUIから起動・停止・状態確認ができる。
FR-05: 声の試聴、採用/除外、保存、次の質問への反映を保持する。2026-10-23の利用者指定により、RasPi版は端末スピーカーでの試聴を既定とする。端末ファーム無変更で、GUIから専用の試聴待受を準備し、端末の明示的な録音操作を開始の合図として使用する。その録音は破棄してAPIへ送らず、固定の日本語文だけを生成し、端末の再生完了通知後に採用できる。Pi/Windows自身での試聴は利用可能な環境の補助経路とする。
FR-06: APIキーをGit・ログ・端末・配布物へ含めない。利用者指定により、一度設定したキーはPi内に暗号化保存し、次回起動時に復元して変更・削除まで再利用する。GUIの保存・更新またはLive開始/試聴準備時に保存する。保存失敗時は処理を開始しない。保存済みキーはGUIから削除できる。
FR-07: 停止、切断、API制限、端末再接続を処理する。
FR-08: CLI/ヘッドレス起動とsystemd常駐は段階導入し、GUIと同じ設定を扱える設計とする。
FR-09: Raspberry Piアプリから端末のWiFiManagerへ接続先を設定できる。有線上流を維持し、一時的なWi-Fiクライアント接続の後は必ず元のPi APへ復帰する。秘密値をログやコマンド引数へ含めない。

## 非機能要件

- Python/Node.jsの依存はバージョン固定。Node.js >=22.9.0（上流 package.json）。
- 既存Windowsテストの後方互換性を保持。
- 設定/音声データはXDG Base Directoryに準じて分離。権限・原子的書込み・破損時復旧を試験。
- 外部APIを使用する試験は明示的な承認後にのみ実施。API利用枠の消費に注意。
- SSH/Raspberry Pi Connectの遠隔管理経路を保護。AP設定はロールバック手順を先に用意する。

## 受入条件

A. 端末なしでNode/Python回帰テスト成功。
B. Raspberry Pi GUI起動・停止・端末での声試聴・採用/除外・設定保存の動作確認。
C. AP/ゲートウェイ構成で現行端末が接続し、質問→Gemini応答→音声再生を確認。
D. 再起動、ネットワーク断、APIエラー、電源断後の復旧を試験。
E. Windows版の既存動作を壊さないことをテストで確認。

## 決定事項と未決事項

- 決定済み: 上流はeth0の有線LANに固定し、端末接続エラー時もWi-Fi上流へ切り替えない。
- 決定済み: wlan0を2.4GHz/WPA2の端末専用APとし、10.42.0.1/24、NetworkManager sharedでDHCPを提供する。[構成と復旧](NETWORK_AP_SETUP.md)。
- 決定済み: Linux秘密保存はAES-256-GCMとユーザー専用のローカル暗号鍵を使用。暗号文と暗号鍵は別のXDG領域へ権限600で保存し、自動復元する。同一ユーザー/rootや両ファイルを含むディスク全体の流出は保護範囲外。詳細は [Piアプリ](../raspi/README.md)。
- Linux PCM出力バックエンド（ALSA/PipeWire等）とGUI/ヘッドレス対応。
- 常駐化・自動起動を初回リリースの必須とするか。

## 根拠

- https://github.com/thomasleftwite/stackchan-chatgpt/blob/main/README.md
- https://github.com/thomasleftwite/stackchan-chatgpt/blob/main/docs/HOTSPOT_TRUST.md
- https://github.com/thomasleftwite/stackchan-chatgpt/blob/main/docs/RESUME.md
