# PROJECT_SPEC — Raspberry Pi版チャットホスト

更新: 2026-10-22 / 状態: Draft v0.1

## 目的とスコープ

- Raspberry Pi 5 / Debian GNU/Linux 13 (trixie) / ARM64 で既存Stackchan音声対話ホストを動作させる。
- 既存Windows版 0.6.0-rc.1 の通信仕様・Gemini Live連携・声の試聴/採用・1質問1回答を可能な限り維持。
- ESP32-S3側のファームウェア、Wi-Fi保存領域、呼びかけ登録データは変更しない。
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
FR-05: 声のPC試聴、採用/除外、保存、次の質問への反映を保持する。
FR-06: APIキーをGit・ログ・端末・配布物へ含めない。保存は任意で、Linuxの適切な保護方式を用いる。
FR-07: 停止、切断、API制限、端末再接続を処理する。
FR-08: CLI/ヘッドレス起動とsystemd常駐は段階導入し、GUIと同じ設定を扱える設計とする。

## 非機能要件

- Python/Node.jsの依存はバージョン固定。Node.js >=22.9.0（上流 package.json）。
- 既存Windowsテストの後方互換性を保持。
- 設定/音声データはXDG Base Directoryに準じて分離。権限・原子的書込み・破損時復旧を試験。
- 外部APIを使用する試験は明示的な承認後にのみ実施。API利用枠の消費に注意。
- SSH/Raspberry Pi Connectの遠隔管理経路を保護。AP設定はロールバック手順を先に用意する。

## 受入条件

A. 端末なしでNode/Python回帰テスト成功。
B. Raspberry Pi GUI起動・停止・声の試聴・設定保存の動作確認。
C. AP/ゲートウェイ構成で現行端末が接続し、質問→Gemini応答→音声再生を確認。
D. 再起動、ネットワーク断、APIエラー、電源断後の復旧を試験。
E. Windows版の既存動作を壊さないことをテストで確認。

## 未決事項

- Raspberry Piの上流インターネット接続方法（有線LAN / 別USB Wi-Fi / 同一無線の同時AP+STA）。
- 端末専用APのSSID、IPレンジ、DHCP方式（NetworkManager/hostapdなど）。
- Linux秘密保存（Secret Service/keyring等）とヘッドレス起動時の解除方式。
- Linux PCM出力バックエンド（ALSA/PipeWire等）とGUI/ヘッドレス対応。
- 常駐化・自動起動を初回リリースの必須とするか。

## 根拠

- https://github.com/thomasleftwite/stackchan-chatgpt/blob/main/README.md
- https://github.com/thomasleftwite/stackchan-chatgpt/blob/main/docs/HOTSPOT_TRUST.md
- https://github.com/thomasleftwite/stackchan-chatgpt/blob/main/docs/RESUME.md
