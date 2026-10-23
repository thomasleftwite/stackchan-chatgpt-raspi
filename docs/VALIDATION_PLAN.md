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

## 2026-10-23 作業再開・上流基準確認

- 作業開始HEAD: `cd4099c`、feature branch `feat/raspi-environment-preflight`、作業ツリーに未コミット変更なし。
- `python3 -m unittest discover -s tests -v`: 既存4件成功。
- `python3 scripts/check_environment.py`: 終了コード1、Node/npm未導入。Python 3.13.5、Git 2.47.3、aarch64を再確認。
- GitHub連携で上流mainのSHA、固定SHAのLICENSE（MIT）とserver/package.json（Node >=22.9.0）を確認。根拠と移管方針は `UPSTREAM_IMPORT.md` に記録。
- 通常のシェルからの `git ls-remote origin refs/heads/main refs/heads/feat/raspi-environment-preflight` はDNS解決失敗（github.com）。この時点ではリモート同期未確認。
- 上流の秘密設定・登録特徴・配布物に対するignoreパターンを追加。移管後の内容検査とWindows/Node回帰テストは未実施。
- ネットワーク利用を許可した `git ls-remote` 再実行は成功。origin/main=`c30d71d`、origin/feat/raspi-environment-preflight=`cd4099c`でローカル追跡SHAと一致。
- `git check-ignore -q` による12個の秘密設定/登録特徴/ビルドパスの除外、3個のソース/サンプルパスの非除外を確認。秘密値の内容検査を意味しない。
- `git diff --check`: 成功。変更差分を自己レビューし、ファーム・依存・OS/ネットワーク設定への変更がないことを確認。
- PR準備: feature branchへのローカルコミット成功。`git push origin feat/raspi-environment-preflight` はHTTPS認証情報を取得できず失敗。GitHub連携による代替のtree作成も403（Resource not accessible by integration）。リモート更新・今回の変更を含むPR作成は未実施。

## 2026-10-23 GitHub CLI認証の復旧

- 利用者が対処の実行を承認後に再確認すると、GitHub CLI 2.46.0-3が導入・認証済み。導入とログイン操作自体はエージェントでは実施していない。
- `gh api user --jq .login`: `thomasleftwite`を確認。秘密値は出力していない。
- `gh auth setup-git --hostname github.com`: 成功。
- `git push --dry-run origin feat/raspi-environment-preflight`: 成功（`cd4099c..d5a6188`）。Pi側のHTTPS認証不足は解消。dry-run時点ではリモート変更なし。
- GitHub連携アプリの書き込み403は未解消。GitHub CLI経路とは別の認証であり、この成功を連携アプリの修復とは扱わない。

## 2026-10-23 固定SHAからホストソース移管

- 開始HEAD: `2706623`（PR #1 merge済みmain）。作業branch: `feat/import-upstream-host`。
- 上流cloneのHEADを `dec249696e84f97b63eba122f33dbb624edfd484` に固定。許可リスト60ファイルの移管後バイト比較とSHA256照合は全件一致。`UPSTREAM_FILES.json` に一覧を記録。
- data、端末ファーム、登録特徴、音声、個人設定、配布物を移管していない。空の秘密設定サンプルと固定のテスト用値は保持。Google/GitHubの既知トークン形式・秘密鍵ヘッダーの検査は0件。依存定義・lockfileは上流と一致。
- Debian 13.6 / aarch64、Python 3.13.5。公式Node v22.23.4 / npm 10.9.9をGit除外の `.runtime/` に配置し、公式SHA256一致を確認（手順は `RASPI_DEV_SETUP.md`）。OSのNode・ネットワーク設定は変更していない。
- NodeのbinをPATHに加え、`npm ci --prefix server --ignore-scripts --no-audit --no-fund --cache "$PWD/.runtime/npm-cache"`: 成功、116パッケージ。依存更新は行っていない。
- `cd server; npm test`: TypeScript build成功。隔離環境ではソケット使用テスト7ファイルが失敗したが、制限外で同じコマンドを実行すると37件すべて成功。各サーバーの待受は127.0.0.1のみ。
- `cd server; node dist/host-self-check.js`: PASS、12001 PCM samples、worker=true、apiCalls=0。
- `python3 -m unittest discover -s tests -v`: 制限外で53件中49成功・2エラー・2スキップ、終了コード1。隔離環境ではGUI表示に接続できず追加3エラー（46成功・5エラー・2スキップ）。
- Pythonの残る2エラー: `test_preview_rejects_non_pcm_and_cancelled_playback_does_not_open_audio` は `ValueError: PC_AUDIO`、`test_pairing_is_persistent_encrypted_and_corruption_fails_closed` は `RuntimeError: WINDOWS_REQUIRED`。Windows専用コードを保持したためLinuxでは実行不可。上流cloneで `python3 -m unittest discover -s tests` を実行しても同じ2件がエラー（49件中45成功・2エラー・2スキップ）となり、移管による新規失敗ではない。
- PythonテストやWindows実装は変更せず、Linux向けテスト実行方針をTODOへ追加。Python全体が合格したとは扱わない。
- `PATH="$PWD/.runtime/node-v22.23.4-linux-arm64/bin:$PATH" python3 scripts/check_environment.py`: 終了コード0、ランタイム前提PASS。ホスト/実機動作の合格判定ではない。
- 移管したPythonファイルの構文確認、60ファイルのハッシュ再照合、既知秘密形式の再検査、ファーム/dataパス不在、ランタイムのGit除外を確認。`git diff --check` 成功。差分を自己レビューし、取り込んだコードとテストが固定SHAから未変更であることを確認。
- Windows実環境、wireless-hostの正常起動・停止、AP・実機・実音声・外部APIは未検証。公開待受・OS設定変更・端末書込み・Gemini API呼び出しは行っていない。

## 2026-10-23 Pythonエラー解析・テストOS条件修正

- 開始HEAD: `efc2078`、PR #2の `feat/import-upstream-host` branch。作業ツリーはクリーン。
- 再現: `PYTHONPATH=tests python3 -m unittest -v test_voice_features.VoiceFeatureTest.test_preview_rejects_non_pcm_and_cancelled_playback_does_not_open_audio test_wireless_host.WirelessHostTests.test_pairing_is_persistent_encrypted_and_corruption_fails_closed`。対象2件ともエラー（`PC_AUDIO` / `WINDOWS_REQUIRED`）。
- 仮説を切り分け: 実装と対象テストは上流ハッシュ一致。Linuxでは取消フラグの有無によらずWindows用再生を拒否。DPAPI保存も拒否しファイルを書き込まない。原因は移管の破損や再生取消の回帰ではなく、上流のWindows専用テストにOS条件が不足していたこと。
- 修正: PCMデコード検証を共通テストへ分離。Windows再生取消・DPAPI往復には `skipUnless(os.name=='nt', ...)` を付与。非WindowsではWindows DLLへ到達せず拒否することを確認し、ペアリング保存失敗で新規ファイル/一時ファイルを作らず、既存ファイルも変更しないことを追加検証。
- 修正した対象5テストの実行: 3成功・2スキップ、終了コード0。
- `python3 -m unittest discover -s tests -v`（GUI表示への接続が可能な制限外環境）: 56件中52成功・Windows専用4件スキップ、エラー/失敗0、終了コード0。
- アプリ/Node/依存/端末ファームに変更なし。58ファイルの上流ハッシュ一致を再確認し、変更したテスト2ファイルは `UPSTREAM_FILES.json` の `local_modifications` に記録。sha256は移管元の値を保持。
- `git diff --check` 成功。自己レビューで共通PCM検証が実行され、Windows専用テストの元の検証内容が維持されることを確認。Windows実環境のテストは未実施。GUI表示接続不可の隔離環境では既存GUIテスト3件の実行に引き続き制限がある。
- Nodeコード・依存が変わらないためNode 37件と自己診断は直前の実測を参照し、今回は再実行していない。実API・実機・実音声の試験も行っていない。

## 2026-10-23 wireless-host起動・停止検証

- 開始HEAD: `9649286`、PR #2の `feat/import-upstream-host` branch。利用者から端末起動済みの報告とホスト起動・停止検証の指示を受けた。
- 読み取り確認: `iw dev` のtypeはmanaged/P2P-device、APなし。`ip -j -4 address show up` の非loopbackはwlan0のみ。SSID/パスワード/IP値は出力していない。APや遠隔管理経路の設定は変更していない。
- 既存ホストはprivate IPv4のみを許可するため、AP未構築のまま端末向け待受を始めず、実APIを使わないfixtureをループバックで検証する方針とした。
- 先に追加した実プロセス試験を実行し、未変更ホストがready前に終了コード1となることを確認。fixture=true（boolean）かつ127.0.0.1/32の場合に限りループバック起動を許可する最小変更を行った。通常起動、曖昧なfixture指定、全インターフェース、公開IPは拒否する。
- `cd server; npm run build; node --test --test-timeout=10000 dist/test/wireless-host.test.js`: build成功、新規5件すべて成功。実際のNode子プロセスを起動し、以下を確認した。
  - health応答とprotocol v2、640 bytesの16kHz入力PCMからfixtureの24kHz無音PCM 1922 bytes/3フレームを受信。
  - stdin EOFで終了コード0、同一ポートでの起動・通信・停止を2回成功。
  - WS接続中のSIGTERM/SIGINTで終了コード0、WS切断、同一ポートで再起動成功。この2件はWindowsではスキップする。
  - ポート使用中の二重起動は終了コード1/failedイベントのみで失敗し、先行ホストはhealth応答を継続。
  - fixture未指定/false/文字列、広いloopback subnet、0.0.0.0/公開IP、特権ポート、null、不正JSONを拒否。標準エラーへ詳細を出していない。
- `cd server; npm test`: TypeScript buildとNode全42件成功（今回の5件を含む）。ソケットを使うため隔離制限外で実施。子プロセスにはAPIキー・NODE_OPTIONS・秘密設定パスを継承しない。
- テスト後にこのbuildを使うwireless-hostプロセスが0件であることを確認。57個の未変更上流ファイルのSHA256一致、`git diff --check`成功。変更したホストはマニフェストに記録し、差分を自己レビューした。
- Pythonは今回変更しておらず、直前の56件中52成功・4スキップを参照。Windows実測、端末/AP経由の接続、Linux GUI、実音声、Gemini実APIは未実施。端末からの入力は受け付けず、ネットワーク公開・OS設定変更・実API呼び出しは行っていない。
