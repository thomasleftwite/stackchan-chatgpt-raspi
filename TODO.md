# TODO — Raspberry Pi 5 ホスト移植

更新: 2026-10-23。未チェックは未実施。優先度 P0 > P1 > P2 > P3。

現在の到達点: 上流ホスト移管、有線上流・Wi-Fi AP、Piアプリからの端末Wi-Fi設定、端末再起動後のホスト到達まで確認済み。次工程としてLinux用ホストの基本CLI/GUIを追加し、fixtureで検証。実APIの初回試行はAUTHで停止したが、キー再入力後に呼びかけから音声回答まで1回成功。[進捗整理](docs/PROGRESS.md)。

直近の記録: [開発経緯](docs/DEVELOPMENT_HISTORY.md)。ホスト停止中の声試聴・中断、採用/除外、XDGへの声設定保存・復元を追加。API不要の回帰とPiのALSA無音出力は成功。実APIサンプルの聴感確認は利用者の操作待ち。既存GUIの声変更・音声回答2回の成功記録とは区別する。

## P0 リポジトリ・環境

- [x] `thomasleftwite/stackchan-chatgpt-raspi` の存在とorigin同期を確認（2026-10-23、`c30d71d`）
- [x] 上流 `stackchan-chatgpt` の基準コミットSHAとライセンスを記録（`dec249696e84f97b63eba122f33dbb624edfd484`、MIT。`docs/UPSTREAM_IMPORT.md`）
- [x] 上流ソースの安全な移管方法を決定（固定SHAからホスト関連だけをスナップショット移管）
- [x] 移管対象のファイル一覧を精査し、LICENSE・server・desktop・関連テストを固定SHAから移管（60ファイル、一覧とSHA256は `docs/UPSTREAM_FILES.json`）
- [x] この計画資料とAGENTS.mdを新規repoへ追加、PRレビュー、mainへmerge（PR #1、`2706623`）
  - 2026-10-23: PiのGitHub CLI認証（`thomasleftwite`）とGit credential helperを確認し、feature branchのpush dry-run成功。GitHub連携アプリの403は別経路のため未解消。
- [x] Raspberry Pi上のclone済み作業ツリーを確認（VS Codeでの表示確認は別項目）
- [ ] VS Codeで作業ツリーを開いたことを確認
- [x] 実行環境を記録：Debian 13.6 / aarch64、Python 3.13.5、Git 2.47.3。Node 22.23.4 / npm 10.9.9をプロジェクト用に導入済み
- [x] 読み取り専用の環境診断 `scripts/check_environment.py` と単体テストを追加
- [x] 今回の移管対象に秘密設定・音声・登録特徴・個人設定が含まれないことを確認（空の `.env.example` と既知のテスト用値を含む。既知トークン形式検査0件、今後の変更も都度検査）
  - 2026-10-23: 秘密設定・登録特徴・配布物の除外に加え、移管時と変更時に内容検査を実施。実機秘密値はGit除外領域だけに保存。

## P1 Node.js基盤

- [x] Node.js >=22.9.0 をARM64に用意（公式22.23.4 / npm 10.9.9、Git除外の `.runtime/` に配置、SHA256照合済み）
- [x] `server` で `npm ci --ignore-scripts` と `npm test` を実行（固定依存116パッケージ、TypeScript buildとNode 47件成功）
- [x] Linux用PythonテストのOS条件を整備（声試聴/保存試験込み119件: 115成功・Windows専用4件スキップ。GUI試験には表示接続が必要）
- [x] `wireless-host.ts` のfixtureと起動・停止を確認（EOF/SIGTERM/SIGINT・再起動・ポート解放、端末/AP経由のhealth到達も確認）
- [x] HTTP/WSプロトコル、音声PCMの回帰テストを追加（実プロセスのfixture試験計10件、Node計47件成功）
- [ ] WindowsとLinuxの両環境でテスト可能なCIを検討

## P2 Pythonホスト移植

- [x] Piアプリから端末WiFiManagerへ接続先を設定し、Pi APへ復帰（`python3 -m raspi.provision --gui`、実機保存・再接続成功）
- [x] `raspi/` の構成とCLIエントリポイントを設計（`raspi.host` のCLI/基本GUI、`raspi.provision` の端末設定）
- [x] PowerShell依存のホットスポット検出をLinuxへ置換（NetworkManagerのAP/sharedと実IPv4を読み取り検証）
- [x] `node.exe` 起動をLinux `node` 起動へ置換（プロジェクト用ARM64 Nodeまたは明示パス）
- [x] 声の評価・選択はXDG配下へ700/600・原子的置換で保存し、GUI/CLIで復元
- [ ] LinuxのAPIキー永続保護方式を決定（声設定へキーは保存しない）
- [x] 声カタログのプルダウン選択と、稼働中の声変更コマンド/確認応答を追加（試聴・採用評価・保存は別項目）
- [x] GUIの開始/停止/再開、二重開始防止、停止中の操作制御と終了待機を追加・回帰試験（実APで開始/停止2回も成功）
- [x] 端末通信の最終受信、未確認への遷移、会話/再生状態、安全な履歴モニターを追加・GUI試験
- [ ] GUI/Tkinterのフォント・表示・文言を調整（今回の操作と状態表示を追加。画面サイズ別の確認は継続）
- [x] 新GUIで2回の実音声回答と、稼働中の声変更後に声が切り替わることを確認（端末再生完了イベントと利用者の聴感が一致）
- [x] ALSAで24kHz PCMの再生/中断を実装し、デバイス不在・失敗・時間切れ・子プロセス回収を試験（実機は無音PCM出力まで確認）
- [x] 声の試聴/採用/除外/保存の回帰、権限・原子的書込み・破損原本の保全と復旧を試験
- [x] 試聴画面をホストの子画面として画面内に配置し、再操作では既存画面を再利用（Connect上の表示は再表示・再読込後に利用者が確認）
- [x] 試聴画面にも共有する非表示キー欄を追加し、生成時の両画面での消去を回帰試験
- [ ] 実APIサンプルのPiでの聴感、採用・再起動後の保存選択を実機確認
- [ ] Geminiキーの永続保護・任意保存を実装/試験
- [x] 停止・SIGTERM・子プロセス回収をテスト（実APのfixture、親CLI SIGTERM、同一ポート再利用、強制回収の単体試験。実API中断は未検証）

## P3 ネットワーク

- [ ] Piの現在の上流接続（Ethernet/無線）と遠隔管理経路を確認
  - 2026-10-23: 現在はeth0有線がIPv4/IPv6の唯一の既定経路、wlan0はAP。別クライアントからのSSH/Pi Connect再接続試験は未実施。
- [x] APに使用するWi-Fiインターフェースを決定（wlan0。上流eth0有線を恒久化）
- [x] AP/DHCP/NATの設計とロールバック手順を文書化（`docs/NETWORK_AP_SETUP.md`、実機AP起動済み）
- [x] AP設定変更前に利用者承認を取得（有線固定、AP化、新APへの端末接続先更新を承認）
- [x] TCP 48443の待受をAP側IPのみに制限（fixtureを10.42.0.1にbind、同一Piのeth0アドレスでは接続拒否を確認）
- [x] ESP32-S3のDHCPゲートウェイがPiであることを確認（AP DHCP取得とゲートウェイのホスト/healthzへの到達を確認）
- [ ] 上流LAN側からTCP 48443にアクセスできないことを確認

## P4 実機・運用

- [x] ESP32-S3ファームウェア無変更でWi-Fi接続確認（新APへの接続先保存は利用者承認済み。登録特徴は変更せず）
- [x] ウェイクワード→録音→Gemini Live→音声再生を確認（2026-10-23、承認済み実APIの単発試験）
  - 2026-10-23: 承認済みの実API試行で長押し質問1件を受信したが、AUTHで終了。音声生成・再生なし。利用者から呼びかけ無反応の報告あり。試行時の端末表示はStart PC Service、キーはGoogle AI Studio発行と利用者が確認。生成なしの認証GETもHTTP 400 / API_KEY_INVALIDで拒否。利用者による再入力後の認証GETはHTTP 200で成功。再試行でturn-complete/voice-played/session-idle/stoppedを受信し、利用者も呼びかけ反応と音声回答を確認。長時間・反復会話・障害復帰は別途検証。
- [ ] 会話後待受・端末再起動・Pi再起動・通信断復帰を検証
  - [x] 実API不要の実プロセスfixtureで、3回の反復質問、入力中の切断、出力フレーム途中の切断/stop、SIGKILL後の同一ポート再起動と質問完了を確認（回帰5件追加）。実機Wi-Fi断・実API中断とは区別。
  - [x] 端末再起動後のAP再接続・DHCP取得・fixtureホスト到達を確認（2026-10-23）。実会話復帰とPi再起動は未検証。
- [ ] 長時間稼働、API制限、音声冒頭欠け、再生停止を検証
- [ ] systemd/デスクトップ起動方式を選択
- [ ] インストール・更新・トラブルシュート手順を整備
- [ ] Raspberry Pi版リリース候補を作成

## 後回し

- [ ] 端末ファームウェア変更、連続会話、多ターン、Gemini直結（今回のスコープ外）
