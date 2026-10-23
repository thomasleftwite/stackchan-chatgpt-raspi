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

上流固定SHAのserver・Windows desktop・関連テストを収録。Piで起動・停止のfixture試験を含むNodeテスト47件とオフライン自己診断が成功しています。Linux用CLI/GUIを追加し、声のプルダウン・開始/停止・端末通信/会話モニターを実装しました。Python118件中114成功・Windows専用4件スキップ。従来の基本GUIでは、実機で呼びかけからGemini Liveの音声回答まで1回確認しています。新GUIでも実音声回答2回と、稼働中の声変更による声の切り替えを利用者と確認しました。ホスト停止中のPi声試聴・採用/除外・声設定保存を追加しました（実API試聴の聴感は確認待ち）。キーの永続保護と長時間稼働・障害復帰の検証は残っています。起動・検証手順は開発環境資料を参照してください。
