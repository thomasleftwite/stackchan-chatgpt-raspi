# 開発経緯と判断の記録

更新: 2026-10-23。実測の詳細・コマンドは [VALIDATION_PLAN.md](VALIDATION_PLAN.md)、現在の未完了項目は [TODO.md](../TODO.md) を参照。

| 段階 | 結果と判断 | 統合・根拠 |
| --- | --- | --- |
| 計画・環境確認 | Pi 5 / Debian 13.6 ARM64でホスト移植。GitHub連携アプリの403に対し、認証済みgh CLIとGitを使用してpush可能と確認。連携アプリ自体の403は未解消 | PR #1、`2706623` |
| 上流移管 | MITの固定SHAからホスト関連60ファイルだけ移管。ファームと個人データを含めない。Node 22.23.4をプロジェクト内へ固定 | PR #2、`ed15d4b`、[移管記録](UPSTREAM_IMPORT.md) |
| Linuxテスト修正 | Windows DPAPI/音声のテスト条件不足を再現。専用試験をOS条件付きにし、共通PCMとLinuxの安全な拒否を検証 | [検証記録](VALIDATION_PLAN.md) |
| ホスト起動停止 | fixtureに限る厳密なloopback境界を追加。EOF/シグナル停止、ポート解放、二重起動失敗を実プロセスで確認 | Node全42件成功、[アーキテクチャ](ARCHITECTURE.md) |
| 有線上流・端末AP | 利用者承認後、eth0を恒久上流に固定しwlan0を端末APへ。端末接続障害でもWi-Fi上流へ戻さない | PR #3、`d3f000d`、[構成と復旧](NETWORK_AP_SETUP.md) |
| 端末設定方式変更 | 利用者の指定によりPiアプリから端末WiFiManagerへ接続先を保存。相対form actionへの対応を修正し、Pi APへの復帰も確認 | `raspi/provision*.py`、[Piアプリ](../raspi/README.md) |
| 端末再起動 | AP再参加・DHCP・fixtureホスト到達を確認。Pi再起動や再起動後の実会話は別項目として保持 | [検証記録](VALIDATION_PLAN.md) |
| Linuxホスト | AP読み取り、CLI/基本GUI、セッション限定キー、子プロセス回収を実装。Python88件中84成功・Windows専用4件スキップ | PR #4、`c581b22` |
| 実API初回失敗 | 長押し質問は届いたがAUTHで停止。生成なしのGETでもAPI_KEY_INVALID。呼びかけ試行時はStart PC Service表示と利用者が確認 | PR #5の検証記録 |
| 認証・音声成功 | ローカル再入力後のGETは200。Live再試行でturn-complete/voice-playedを受信し、利用者も呼びかけ反応と音声回答を確認。試験ホスト停止済み | 単発E2E成功。反復・復帰・長時間の合格とはしない |

## 保持する運用判断

- 端末ファーム書込み、呼びかけ登録の変更は行っていない。端末のWi-Fi接続先更新だけは利用者の明示承認済み。
- APIキーはローカルの非表示入力で受け取り、セッション内だけ使用。キー・音声・質問内容・AP秘密値をGitやPRへ含めない。
- 実API試験は利用者承認済み。次工程のオフライン試験ではfixtureを使う。
- GUI/CLIを手動起動する段階で、キーの永続保存、systemd、自動起動は未導入。
- ネットワークの再設定やPi再起動は今回の文書整理・オフライン回帰検証には含めない。

## 次工程と検証境界

文書整理のPR #5は `1483b29` へmerge済み。その後の実ホストfixture試験で反復質問、入力中/出力フレーム途中の切断・stop、SIGKILL後の同一ポート再起動・次質問完了の5件を追加し、Node全47件成功。実装の修正は不要だった。HTTP/WSの復帰と実機Wi-Fi断・実API中断は区別する。次は実機検証の継続と、声のPi試聴・設定保存の方式決定。

PR: [#1](https://github.com/thomasleftwite/stackchan-chatgpt-raspi/pull/1)、[#2](https://github.com/thomasleftwite/stackchan-chatgpt-raspi/pull/2)、[#3](https://github.com/thomasleftwite/stackchan-chatgpt-raspi/pull/3)、[#4](https://github.com/thomasleftwite/stackchan-chatgpt-raspi/pull/4)、[#5](https://github.com/thomasleftwite/stackchan-chatgpt-raspi/pull/5)。

## 2026-10-23 Windows版に合わせたRasPi GUIの拡充

利用者の指定に合わせ、声カタログのプルダウン、ホストサービスの開始/停止、端末状態モニターを追加。既存の開始/停止を拡張し、二重開始防止、停止中の操作制御、再開、終了待機を整備した。声の選択は初期環境と既存stdinコマンドへ渡し、実行中の回答を変えず次の質問へ反映する。端末のhealth等に基づく最終受信時刻、30秒の通信未確認表示、会話/再生状態と固定文言の履歴を追加した。端末ファーム・server・Windows製品コード・実機設定・依存の変更はない。新GUIでの有料API試験は実施していない。

Python95件中91成功・Windows専用4件スキップ、TypeScript buildとNode47件成功。GUI破棄時の予約コールバックも回収し、終了後のTkエラーを解消。声の試聴・採用評価・保存とLinuxのキー保護方式は次工程として残す。
