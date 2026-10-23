# 上流基準とソース移管手順

確認日: 2026-10-23。ソース移管そのものは未実施。

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

## 現状の制約

Node/npm未導入のためホストテストは未実施。ホストのファイル一覧精査・移管・秘密内容検査も未実施。ネットワークやOS設定の変更、端末書込み、外部APIの呼び出しはこの手順の対象外。
