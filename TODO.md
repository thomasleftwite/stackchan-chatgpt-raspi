# TODO — Raspberry Pi 5 ホスト移植

更新: 2026-10-23。未チェックは未実施。優先度 P0 > P1 > P2 > P3。

## P0 リポジトリ・環境

- [x] `thomasleftwite/stackchan-chatgpt-raspi` の存在とorigin同期を確認（2026-10-23、`c30d71d`）
- [x] 上流 `stackchan-chatgpt` の基準コミットSHAとライセンスを記録（`dec249696e84f97b63eba122f33dbb624edfd484`、MIT。`docs/UPSTREAM_IMPORT.md`）
- [x] 上流ソースの安全な移管方法を決定（固定SHAからホスト関連だけをスナップショット移管。実際の移管は未実施）
- [ ] 移管対象のファイル一覧を精査し、LICENSE・server・desktop・関連テストを固定SHAから移管
- [ ] この計画資料とAGENTS.mdを新規repoへ追加、PRレビュー、mainへmerge
- [x] Raspberry Pi上のclone済み作業ツリーを確認（VS Codeでの表示確認は別項目）
- [ ] VS Codeで作業ツリーを開いたことを確認
- [x] 実行環境を記録：Debian 13.6 / aarch64、Python 3.13.5、Git 2.47.3。Node/npm未導入
- [x] 読み取り専用の環境診断 `scripts/check_environment.py` と単体テストを追加
- [ ] 秘密情報がコミット対象に入らないことを確認
  - 2026-10-23: 上流の秘密設定・登録特徴・配布物の除外パターンを追加。移管後の内容検査は未実施。

## P1 Node.js基盤

- [ ] Node.js >=22.9.0 をARM64に用意
- [ ] `server` で `npm ci --ignore-scripts` と `npm test` を実行
- [ ] `wireless-host.ts` のfixtureと起動・停止を確認
- [ ] HTTP/WSプロトコル、音声PCMの回帰テストを追加
- [ ] WindowsとLinuxの両環境でテスト可能なCIを検討

## P2 Pythonホスト移植

- [ ] `raspi/` の構成とCLIエントリポイントを設計
- [ ] PowerShell依存のホットスポット検出をLinuxへ置換
- [ ] `node.exe` 起動をLinux `node` 起動へ置換
- [ ] Linuxの設定保存先と秘密保護方式を決定
- [ ] GUI/Tkinterのフォント・表示・文言を調整
- [ ] 24kHz PCMの再生/中断を実装し、音声デバイス未接続時も安全に失敗
- [ ] 声の試聴/採用/保存、Geminiキー管理をテスト
- [ ] 停止・SIGTERM・子プロセス回収をテスト

## P3 ネットワーク

- [ ] Piの現在の上流接続（Ethernet/無線）と遠隔管理経路を確認
- [ ] APに使用するWi-Fiインターフェースを決定
- [ ] AP/DHCP/NATの設計とロールバック手順を文書化
- [ ] AP設定変更前に利用者承認を取得
- [ ] TCP 48443の待受をAP側IPのみに制限
- [ ] ESP32-S3のDHCPゲートウェイがPiであることを確認
- [ ] 上流LAN側からTCP 48443にアクセスできないことを確認

## P4 実機・運用

- [ ] ESP32-S3ファームウェア無変更でWi-Fi接続確認
- [ ] ウェイクワード→録音→Gemini Live→音声再生を確認
- [ ] 会話後待受・端末再起動・Pi再起動・通信断復帰を検証
- [ ] 長時間稼働、API制限、音声冒頭欠け、再生停止を検証
- [ ] systemd/デスクトップ起動方式を選択
- [ ] インストール・更新・トラブルシュート手順を整備
- [ ] Raspberry Pi版リリース候補を作成

## 後回し

- [ ] 端末ファームウェア変更、連続会話、多ターン、Gemini直結（今回のスコープ外）
