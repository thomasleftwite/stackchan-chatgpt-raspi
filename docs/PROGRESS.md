# Raspberry Pi移植の進捗

更新: 2026-10-23。PR #2（ホストソース移管・起動停止検証）とPR #3（有線上流・AP・端末Wi-Fi設定アプリ）の統合時点の整理。

## 完了したこと

- 上流固定SHAのホスト関連60ファイルを移管し、MITライセンス・由来・移管後の差分を記録。
- 公式Node 22.23.4 ARM64 / npm 10.9.9をGit除外領域に配置。固定依存を導入し、Node全42件とオフライン自己診断が成功。
- Linuxで不適切に実行されていたWindows専用PythonテストのOS条件を修正。Piアプリの設定・復旧試験を含めPython全73件中69成功、Windows専用4件スキップ。
- eth0を恒久的なインターネット経路に固定。wlan0を2.4GHz/WPA2の端末APに構成し、DHCPを提供。端末接続失敗時もWi-Fiを上流へ戻さない。
- Piアプリから端末のWiFiManagerへ接続先をPOSTで保存し、Pi APへ復帰する機能を実装・実機確認。秘密値はコマンド引数・URL・共有ログへ含めない。
- 端末のAP参加、DHCP取得、ホストのHTTP到達を確認。端末再起動後も同じ経路へ復帰することを確認。端末ファーム書込み・登録特徴変更は行っていない。
- fixtureホストのEOF/SIGTERM/SIGINT停止、子プロセス終了、ポート再利用、二重起動失敗を検証。検証ホストは停止済み。

## 未完了・未検証

- 実会話用LinuxホストのCLI/GUI、Linuxでの設定・APIキー管理、声の試聴・採用・保存とPCM再生/中断。
- Gemini実APIを使う会話・実音声。実APIの課金試験は承認を得てから実施する。
- Pi再起動後の自動復帰、通信断・長時間稼働、上流LAN上の別機器からの接続拒否、Windows実環境での回帰。
- systemd等の常駐方式と配布。現状はアプリやホストを自動常駐させていない。

## 次の実装

Linux用ホストのCLIとプロセス管理を `raspi/` に追加する。NetworkManagerで実際のAP側IPv4/サブネットを読み取り、上流側を拒否し、既存の `server/wireless-host.ts` をLinux Nodeで起動する。まずfixtureで起動・停止・SIGTERM・子プロセス回収を検証する。実APIは自動で呼ばず、キーは初期段階ではメモリ内だけで渡す。

詳細: [TODO](../TODO.md)、[検証記録](VALIDATION_PLAN.md)、[ネットワークと復旧](NETWORK_AP_SETUP.md)、[端末設定アプリ](../raspi/README.md)。
