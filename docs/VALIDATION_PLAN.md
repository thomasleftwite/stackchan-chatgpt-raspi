# 検証計画

## 既存ベースライン（上流記録でありPiでの実測ではない）

上流 `docs/validation.md` にWindows版RC1のPython49件、Node37件、C++169項目、端末3構成ビルド、EXE自己診断15項目成功と記載。これらをRaspberry Pi版の合格結果として転記しない。

## テストマトリクス

| レベル | 試験 | 判定条件 |
| --- | --- | --- |
| L0 静的 | Python構文/型、TypeScript build、秘密値の追跡防止 | エラーなし、秘密値未含有 |
| L1 単体 | Node `npm test`、Python `unittest` | Pi上で成功 |
| L2 結合 | Node起動/停止、stdin JSON、WS fixture、PCMフレーム | 正しいイベント・フレーム境界 |
| L3 GUI | 設定・声採用・音声再生・中断 | UI応答、異常時にクラッシュしない |
| L4 ネットワーク | AP DHCP、gateway IP、AP側bind、上流から拒否 | 端末接続成功、意図しない公開なし |
| L5 実機 | 呼びかけ→質問→回答、半二重、200ms再生待機 | 端末で音声が途切れず再生 |
| L6 復旧 | AP/インターネット断、Pi再起動、Gemini認証/制限 | 安全な停止・再接続・適切な分類 |

## 実行順序

1. APIキーを使わないローカルテスト。
2. ダミー音声を使った模擬通信。
3. AP接続（インターネットなしでも可）。
4. 利用者の承認後にGemini実APIテスト（利用枠消費）。
5. 実機の反復・長時間試験。

## 記録様式

- 実施日時 / Pi OS・カーネル・Python・Node・npmのバージョン
- Git commit SHA / 実施コマンド / 成功・失敗 / 再現手順
- AP構成、端末ファーム版、端末・ホスト接続経路
- 音声・会話本文・APIキー・個人設定は記録しない

参考: https://github.com/thomasleftwite/stackchan-chatgpt/blob/main/docs/validation.md

## 2026-10-23 環境診断

- 基準コミット: `c30d71d`（作業開始時、`origin/main` と一致）。
- Debian 13.6 (trixie)、aarch64、Python 3.13.5、Git 2.47.3。
- `python3 -m unittest discover -s tests -v`: 診断スクリプトの4件成功（欠落、Nodeバージョン境界、出力抑制、タイムアウト）。
- `python3 scripts/check_environment.py`: 終了コード1、Node/npm未導入を検出。前提未充足であり、ホストの合格判定ではない。
- 上流ソース未移管のため、Node/Windows回帰・GUI・AP・実機・外部API試験は未実施。
