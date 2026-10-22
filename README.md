# Stackchan Chat Host — Raspberry Pi 5 移植計画

状態: **計画資料 / 未実装**（2026-10-22）

- 上流: https://github.com/thomasleftwite/stackchan-chatgpt
- ベースライン: Windows Host 0.6.0-rc.1 / AtomS3R + Atomic Voice Base A149
- 対象: Raspberry Pi 5、Debian 13 (trixie)、aarch64、VS Code + Codex
- 目的: ESP32-S3ファームウェアと通信プロトコルを変更せず、Gemini Live対応ホストをRaspberry Pi上で動作させる。

## ドキュメント

- [移植仕様](docs/PROJECT_SPEC.md)
- [アーキテクチャと移植対象](docs/ARCHITECTURE.md)
- [開発ロードマップ](docs/ROADMAP.md)
- [ToDo](TODO.md)
- [検証計画](docs/VALIDATION_PLAN.md)
- [Raspberry Pi開発環境と引継ぎ](docs/RASPI_DEV_SETUP.md)
- [開発エージェント指示](AGENTS.md)

## 重要な制約

端末はDHCPゲートウェイのTCP 48443へ接続する。既存端末を無改造で使うには、Raspberry Piが端末側ネットワークのゲートウェイになる構成が必要。**既存のRaspberry Pi Connect/SSH接続を維持するまで、Wi-Fi/APやNetworkManager設定を変更しない。**

このパッケージは移植計画資料のみ。元リポジトリのソースコードを含まず、Linux版ホストはまだ完成していない。
