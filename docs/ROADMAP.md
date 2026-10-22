# 開発ロードマップ

状態: 全フェーズ未着手（計画作成時点）。完了を推定しない。

| フェーズ | 成果物 | 完了判定 |
| --- | --- | --- |
| P0 ベースライン | 新規repo、上流由来とcommit記録、開発環境、テスト結果 | GitHub mainに資料があり、Piからcloneできる |
| P1 中継単体 | ARM64 Node実行、`npm ci --ignore-scripts`、`npm test`、fixture | Node単体テスト合格、キー不要のローカル疎通 |
| P2 Linuxホスト | `raspi/` GUI/CLI、設定、Node起動停止、Linux音声再生 | Pi上で起動停止・声試聴・秘密保存テスト |
| P3 ネットワーク | AP/DHCP/ゲートウェイ、IPバインド、ロールバック | 端末から接続、遠隔管理維持、上流LANに非公開 |
| P4 実機E2E | 既存ESP32-S3ファームとGemini Live | 1質問1回答・音声再生・復旧を確認 |
| P5 運用 | systemd/GUI起動、ログ、README、リリース候補 | 再起動/通信断/停止/起動が安定し手順が再現可能 |

## フェーズゲート

- P0→P1: Piでnode/npm/python/gitの実行環境を確認。
- P1→P2: 既存NodeテストがARM64で通過。
- P2→P3: GUI/CLIの動作をAP設定なしで確認。
- P3→P4: AP構成の復旧手順、遠隔アクセス保護、設定バックアップを確認。
- P4→P5: 実機音声会話と再接続の証跡を保存（秘密値を除外）。

## ブランチ運用

- `main`: 検証済みの安定状態。
- `feature/raspi-p1-node`, `feature/raspi-p2-host` など小さなブランチで開発。
- Codexが変更→テスト→差分レビュー→PR→merge。
- ESP32ファームウェアへの変更は別途明示承認があるまで禁止。
