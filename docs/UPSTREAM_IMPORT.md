# 上流基準とソース移管手順

確認日: 2026-10-23。固定SHAからホスト関連60ファイルを移管済み。

## 固定する基準

- リポジトリ: https://github.com/thomasleftwite/stackchan-chatgpt
- SHA: `dec249696e84f97b63eba122f33dbb624edfd484`（確認時のmain、RC1公開記録コミット）。
- [基準コミット](https://github.com/thomasleftwite/stackchan-chatgpt/commit/dec249696e84f97b63eba122f33dbb624edfd484)
- [LICENSE](https://github.com/thomasleftwite/stackchan-chatgpt/blob/dec249696e84f97b63eba122f33dbb624edfd484/LICENSE): MIT、Copyright (c) 2026 thomasleftwite。移管時は全文をそのまま含め、著作権表示と許諾文を保持する。依存ライブラリのライセンスは別途確認する。
- [server/package.json](https://github.com/thomasleftwite/stackchan-chatgpt/blob/dec249696e84f97b63eba122f33dbb624edfd484/server/package.json): Node >=22.9.0。依存とpackage-lock.jsonは基準のまま移管し、更新しない。

## 決定

固定SHAの追跡済みホスト関連ファイルだけをスナップショットとして移管する。既存の移植計画リポジトリの履歴を保持し、上流履歴全体のmergeは行わない。これにより過去の不要な成果物・端末ファームを取り込む範囲を絞れる。由来はこのSHAと移管時のファイル一覧で追跡する。

## 実施順序

1. feature branchで作業し、上流を別の一時ディレクトリへ取得。checkout後のHEADが固定SHAと一致することを確認する。
2. `git ls-tree -r --name-only` で対象一覧を作る。候補はLICENSE、serverのソース・固定依存定義・テスト、desktopのPythonソース、関連Pythonテストと通信仕様。実際の配置と参照関係を確認してから許可リストを確定する。
3. `.env*`、秘密設定、音声、登録特徴、個人設定、node_modules、dist、ビルド済み配布物を除外する。サンプル設定も内容を検査する。`src/`、`include/`、`lib/`、`platformio.ini`は取り込まない。
4. 既存のAGENTS.md、TODO.md、docs、testsをディレクトリ単位で上書きしない。必要なテストだけを個別配置し、衝突時は既存診断テストを保持する。
5. 元ファイルとのバイト比較、移管一覧、秘密情報検査を記録する。秘密値や疑わしい一致内容をログへ出さない。Gitのignoreだけを秘密検査の代わりにしない。
6. Node ARM64環境を用意した後、`server`で`npm ci --ignore-scripts`と`npm test`を実施。API利用を伴うテストは明示承認まで実施しない。Windows固有PythonテストのLinux結果はWindows互換性の証明としない。
7. TODO.mdと検証記録を更新し、差分をレビューしてPRへまとめる。

## 移管結果

- 許可リストと移管時の各ファイルのSHA256: `UPSTREAM_FILES.json`。LICENSE、server 39ファイル、desktop 10ファイル、Pythonテスト5ファイル、補助スクリプト2ファイル、通信/声仕様3ファイルの計60ファイル。移管時はすべて固定SHAとバイト一致。
- 補助スクリプトはPythonテストとWindows配布処理が参照する `tools/run_gemini_device.py` と `tools/run_lan_probe.py` のみ。端末操作機能は実行していない。
- `server/.env.example` は内容を確認し、キー・トークン・接続先URLが空のサンプルとして例外的に移管。実際の `.env`、data、音声、登録特徴、個人設定、ファーム、配布物は対象外。
- 既知のGoogle/GitHubトークン形式と秘密鍵ヘッダーを全移管ファイルに照合し0件。固定のテスト用ダミー値は保持。これはあらゆる秘密値の不存在を数学的に保証する検査ではない。
- 依存定義・lockfile・Nodeテストを変更せず、Node 37件成功。オフライン自己診断も成功（API呼び出し0）。
- 移管後の変更: `tests/test_voice_features.py` と `tests/test_wireless_host.py` のWindows専用テストにOS条件を付け、PCM検証を共通テストへ分離。非WindowsではWindows APIへの到達拒否とペアリング保存失敗時のファイル保全を検証する。アプリ実装は未変更。他の58ファイルは固定SHAと一致。マニフェストのsha256は移管元の基準を保持し、`local_modifications` に差分対象を記録する。

## 現状の制約

Windows版のコードを保持した段階で、Linux用GUI/秘密保存/音声処理は未実装。上流で再現したPythonの2エラーはWindows専用テストのOS条件漏れだった。修正後はPiで56件中52成功・4スキップ。これはLinux用ホスト機能の完成を意味しない。Windowsでの回帰実測、wireless-hostプロセスの正常起動・停止、AP・実機・外部APIの試験は未実施。
