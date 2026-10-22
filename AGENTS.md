# AGENTS.md — Stackchan Raspberry Pi Port

## 役割

CodexはRaspberry Pi 5上の開発エージェント。設計→最小変更→テスト→レビュー→PRの順に進める。

## 優先順位

1. `docs/PROJECT_SPEC.md` と `docs/ARCHITECTURE.md` の要件。
2. 既存ESP32-S3との通信互換性。
3. Windows版の回帰防止。
4. 変更範囲の最小化、実行可能な検証。

## 変更制限

- `src/`, `include/`, `lib/`, `platformio.ini` の端末ファーム変更は、明示承認なしに行わない。
- Wi-Fi AP/DHCP、NetworkManager、SSH、Raspberry Pi Connect、ファイアウォール、systemdの実機設定変更は、事前に計画と復旧手順を提示し、明示承認を得る。
- APIキー、Wi-Fiパスワード、音声、登録特徴、個人設定、秘密値をログ・PR・Gitに含めない。
- 依存更新、外部API課金を伴うテスト、ファーム書込み、ネットワーク公開を独断で行わない。
- `main` へ直接pushせず、feature branch→テスト→PR→レビュー→merge。

## 実装方針

- `server/` のTypeScriptは最大限再利用。
- Linux固有の処理は `raspi/` へ隔離。共通化する場合は両OSのテストを用意。
- 失敗は再現手順・コマンド・ログの秘密値除去を行って報告。
- 変更時に `TODO.md` と `docs/VALIDATION_PLAN.md` を更新。
- 未実施テストを「成功」と書かない。

## 毎回の報告形式

- 目的 / 変更ファイル / 実施したテストと結果 / 未検証事項 / 次の作業。
