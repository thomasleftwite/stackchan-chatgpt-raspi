# Stackchan Chat Host — Raspberry Pi 5 移植計画

状態: **LinuxホストCLI/基本GUI・呼びかけから実音声回答まで単発確認済み / 移植継続中**（2026-10-23）

- 上流: https://github.com/thomasleftwite/stackchan-chatgpt
- ベースライン: Windows Host 0.6.0-rc.1 / AtomS3R + Atomic Voice Base A149
- 対象: Raspberry Pi 5、Debian 13 (trixie)、aarch64、VS Code + Codex
- 目的: ESP32-S3ファームウェアと通信プロトコルを変更せず、Gemini Live対応ホストをRaspberry Pi上で動作させる。

## ドキュメント

- [現在の進捗と次の作業](docs/PROGRESS.md)
- [開発経緯と判断の記録](docs/DEVELOPMENT_HISTORY.md)
- [移植仕様](docs/PROJECT_SPEC.md)
- [アーキテクチャと移植対象](docs/ARCHITECTURE.md)
- [開発ロードマップ](docs/ROADMAP.md)
- [ToDo](TODO.md)
- [検証計画](docs/VALIDATION_PLAN.md)
- [Raspberry Pi開発環境と引継ぎ](docs/RASPI_DEV_SETUP.md)
- [有線上流・端末APと復旧](docs/NETWORK_AP_SETUP.md)
- [Piアプリから端末Wi-Fiを設定](raspi/README.md)
- [PiホストCLI/GUIの起動](raspi/README.md#会話ホストの起動停止)
- [上流基準と移管記録](docs/UPSTREAM_IMPORT.md)
- [開発エージェント指示](AGENTS.md)

## 重要な制約

端末はDHCPゲートウェイのTCP 48443へ接続する。既存端末を無改造で使うには、Raspberry Piが端末側ネットワークのゲートウェイになる構成が必要。**既存のRaspberry Pi Connect/SSH接続を維持するまで、Wi-Fi/APやNetworkManager設定を変更しない。**

上流固定SHAのserver・Windows desktop・関連テストを収録。Piで起動・停止のfixture試験を含むNodeテスト42件とオフライン自己診断が成功しています。Linux用CLI/基本GUIを追加し、実機で呼びかけからGemini Liveの音声回答まで1回確認しました。声のPi試聴、設定保存、反復会話や障害復帰の検証は残っています。起動・検証手順は開発環境資料を参照してください。
