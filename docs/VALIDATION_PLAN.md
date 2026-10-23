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

## 2026-10-23 有線上流固定・AP構築・Piアプリからの端末設定

- 開始HEAD: `b091908`。`feat/raspi-wired-ap` branchを作成。利用者は有線HTTPS疎通成功後の恒久上流化、AP設定、新しいPi APへ端末接続先を更新することを明示承認し、さらにPiアプリからWiFiManagerへ設定する方式への変更を指示した。
- `curl --interface eth0 ... https://github.com/`: HTTP 200。eth0はlink upで、設定前のIPv4 default metricはeth0=100 / wlan0=600だった。
- 有線profileの自動接続とIPv4/IPv6既定経路を恒久化。旧Wi-Fi client profileは自動接続を無効にし、IPv4/IPv6 never-defaultを有効化。変更後も有線HTTPS成功、IPv4/IPv6の既定経路はeth0だけ。Wi-Fi上流への自動切替は構成していない。
- wlan0のAP対応を確認し、競合しない10.42.0.1/24で2.4GHz channel 6 / 20MHz・WPA2/CCMP・NetworkManager sharedを設定。AP自動接続を有効化。実際のAPモード、wlan0のdnsmasq・DHCP範囲・APアドレス・lease fileを確認。有線HTTPSと既定経路維持も再確認した。
- 有線変更には120秒、AP作成にはwlan0限定180秒checkpointを使用し、検証成功後に確定。秘密値とバックアップはGit除外領域にのみ保存し、ディレクトリ700・認証情報ファイル600を確認。実パスワード・元の接続名・UUID・端末MACを共有記録へ出していない。
- AP上でfixtureホストを10.42.0.1:48443だけに起動。Piからのローカルhealthはprotocol v2でHTTP 200。同じPiのeth0アドレスではTCP 48443に接続できないことを確認。上流LAN上の別機器からの接続試験は未実施。
- 最初の手動設定待機では180秒間の端末参加0台で終了。その後、利用者の追加指示に合わせて手動情報表示を閉じ、`raspi/provision.py`、`provision_network.py`、`provision_ui.py` を追加した。アプリはNetworkManagerからPi AP認証情報を取得し、一時的なメモリ内クライアント接続からWiFiManagerへPOSTし、finallyでPi APを復旧する。
- 初回のアプリ実機試験は `PORTAL_FORM_MISMATCH` で送信前に停止し、AP復帰成功。実機の相対actionへの互換性を疑い、同じ相対フォームの回帰テストでエラーを再現した。許可するactionを `/wifisave` と `wifisave` だけに修正した後、実機再試験で `complete / saved=true / apRestored=true` を確認。任意のURLやリダイレクト先への送信は許可していない。
- アプリで接続先保存後の確認: AP参加1台、DHCPリース1件、端末からのhealthイベント1件。今回はPi自身からhealthを呼ばず、遠隔イベントをローカル疎通と区別した。監視用スクリプトの冒頭表示には前回の固定文言が残っていたが、この回のlocalHealthはfalse（未実施）であり、ローカルhealthの成功結果は先行試験だけを根拠とする。fixtureの実API呼び出し0、会話セッション0、終了コード0。
- 端末設定後にAPモード、IPv4/IPv6 defaultがeth0のみであること、一時接続profileが残っていないことを確認した。
- 最終レビューでアプリのcheckpointはflags=0へ変更し、無関係な新規profileを削除しない構成にした。自分の一時profileだけを削除する。最終版のprepare/checkpoint作成・破棄も実機で確認（Wi-Fi切替・端末保存はこの確認では再実行していない）。
- `python3 -m unittest discover -s tests -v`: 73件中69成功・Windows専用4件スキップ、エラー0。新規17件には失敗時AP復旧、誤経路時送信拒否、フォーム検証、相対パス、秘密値のstdin渡しとGUI欄消去、checkpoint対象限定を含む。GUI接続が可能な隔離制限外で実施した。
- Nodeコードは今回変更しておらず、直前の全42件成功を参照し再実行していない。端末ファーム書込み・保存領域初期化・呼びかけ登録変更・API課金試験は実施していない。
- 未検証: 再起動後の自動接続、別クライアントからの遠隔管理・上流LANからの拒否、Windows実行、Linux用Gemini会話GUI・秘密保存・実音声、長時間稼働。アプリからの端末Wi-Fi設定とHTTP到達の成功を、実会話の成功とは扱わない。
- コミット対象11ファイルを確認し、実APパスワードとの一致0件、既知秘密形式0件、runtime/data/端末ファームの混入0件。`git diff --cached --check`成功。自己レビュー後、今回限りの端末設定用認証ファイルは削除した。

## 2026-10-23 端末再起動後の接続復帰

- 利用者が端末を再起動し、画面に「Start PC Service」と表示されたと報告。Pi自体は再起動していない。
- 開始HEAD: `c8893ec`。読み取り確認でAP参加1台、DHCPリース1件、IPv4の既定経路はeth0のみ。
- `sudo -n env VERIFY_REMOTE_ONLY=1 python3 .runtime/network/verify-device.py`: AP側10.42.0.1:48443へfixtureホストを起動し、端末からのhealthイベント1件を確認。Pi自身からhealthを呼ばず、端末の到達と区別した。端末再起動後のAP再接続・DHCP取得・ホストへのHTTP到達が成功。
- 同じPiの有線側アドレスへのTCP 48443接続は拒否。実API呼び出し0、会話セッション0、確認後のホスト終了コード0。ホストは常駐していない。
- 「Start PC Service」はホスト停止中の待機表示と整合する。起動後の画面遷移は利用者からの確認を得ておらず、画面検証の成功とは記録しない。
- 変更はTODOと検証記録のみ。コード・OS設定・端末ファームは変更せず、Python/Nodeテストは再実行していない。Pi再起動、実API会話、実音声、会話後復帰は未検証。

## 2026-10-23 進捗整理と統合準備

- 利用者から、現状の整理・push・mergeと、その後の次工程への移行を明示指示された。
- `docs/PROGRESS.md` を追加し、TODO/READMEの古い状態表示を現在の実測に合わせた。合格結果は直前のNode42件、Python73件中69成功・4スキップ、端末/APの実測を参照し、文書変更だけのため再実行はしていない。
- PR #2/#3の先頭はそれぞれ `b091908` / `4aa7716`、競合なし、CI未設定であることを確認。統合前に文書差分・秘密値非混入を確認し、PRの依存順にmergeする。

## 2026-10-23 統合完了とLinuxホスト次工程

- 進捗整理を `fcbebe7` へコミット・push。利用者の明示承認に従い、PR #2を `ed15d4b` でmerge後、PR #3をmainへretargetし、先頭 `fcbebe7`・MERGEABLE/CLEANを再確認して `d3f000d` でmergeした。mainはorigin/mainへfast-forward同期し、新しい `feat/raspi-host-cli` branchを作成した。
- Linux専用のAP読み取り、Node実行、CLI/基本GUIを `raspi/host_network.py`、`host.py`、`host_ui.py` に追加。AP/shared接続かつ一意なRFC1918 IPv4/16〜/30だけを選び、上流・公開IP・曖昧なアドレスを拒否する。OS/ネットワーク設定は今回変更していない。
- Node >=22.9.0を検証し、自身のNodeを専用プロセスグループで起動。EOF→SIGTERM→SIGKILLで自身の子だけを終了・回収し、GUIを閉じる際も処理の終了を待つ。Nodeのstderrやprovider本文を表示せず、固定イベントと許可された失敗分類だけを取り出す。
- GUIはAPI不要のfixtureを初期状態とし、実APIを使うモードではキーを今回のセッションだけで保持。入力欄は開始時に消去する。CLIは明示の `--live` と対話端末での非表示入力を要求し、非TTYでキー入力へフォールバックしない。継承済みキー・NODE_OPTIONS・秘密設定を子へ渡さない。
- `python3 -m raspi.host --fixture --duration 3`: 実APを自動検出してready→stopped、終了コード0。
- CLIを実AP上で別プロセスとしてfixture起動後、親CLIへSIGTERMを送信: stoppedイベント、終了コード0。検証後にこのbuildのwireless-hostプロセスが0件であることを確認した。
- 新規テストはAP境界、Nodeバージョン、継承キー排除、明示キー必須、固定エラー分類、秘密情報除去、キー入力取消、非TTY拒否、CLIのシグナル、子の強制回収、実Node再起動/同一ポート再利用、GUIの初期状態とキー欄消去を検証する。実APIの接続はモックであり、課金API呼び出しは行っていない。
- 非TTYガード追加時のテストでキー入力取消が期待130に対し1となる失敗を検出。sys import漏れを修正し、最終の `python3 -m unittest discover -s tests` は88件中84成功・Windows専用4件スキップ、失敗/エラー0。
- Node/Windows共通コードや依存は変更しておらず、Node全42件は前工程の結果を参照して再実行していない。`git diff --check`とPython構文確認は成功。
- 未検証: 実APIによる会話・音声とその中断、Linuxの声管理/PC試聴、設定永続化、Pi再起動と外部LAN/Windows実測。今回のGUIは基本起動・停止の段階であり、全受入条件の達成とは扱わない。

## 2026-10-23 承認済み実API試行・認証失敗の切り分け

- 開始HEAD: `ad4e767`、`feat/raspi-host-cli`。利用者の「ok、進めて」により実API会話試験が承認された。PiのGUI非表示欄に利用者がキーを入力し、開始時に欄を消去。キー・音声・質問内容を共有ログやGitへ保存していない。
- Git除外の監督用ハーネス `python3 .runtime/live-check.py` でGUIと実ホストを起動。固定イベントのみを収集し、`ready → session-busy → turn-failed(code=AUTH) → session-idle → stopped` を確認。セッション1件、音声生成/再生の完了イベント0件。エラー後にホストを停止し、自動再試行していない。
- 利用者は「ウェイクワード無反応、画面ボタン長押しで質問モードに入り、発話後にエラー」と報告。長押しの質問はホストへ到達したが、ウェイクワード検出と実音声応答の成功とは扱わない。
- 有線インターフェースを指定したキーなしHTTPSでGoogle APIホストからHTTP 404を受信。TLS/HTTPの到達だけを確認したもので、API認証の成功ではない。
- コード読み取り: ホスト子プロセスには明示入力のGEMINI_API_KEYだけを渡し、継承済みGOOGLE_API_KEYを渡さない。SDKにはapiKeyとvertexai=falseを明示。AUTH分類は401または認証を示す本文パターンであり、今回の固定イベントに詳細statusはないため、キーの無効化・種類・制限のどれかは確定できない。
- 上流固定SHAの端末実装を読み取り確認: 呼びかけ検出はWakeWait、マイク許可、Wi-Fi接続、ホスト稼働などが条件。ホスト停止中やSleeping時は検出しない。現在の実機ファームとの一致や試行時の画面状態は未確認。端末ファーム・登録特徴は変更していない。
- Google公式キー資料を参照: https://ai.google.dev/gemini-api/docs/api-key 。キーの種類・有効性・制限確認は候補であり、今回の原因と断定していない。キーをチャットへ送らず、発行元と端末画面表示の確認を依頼した。
- 今回のリポジトリ変更はTODOと進捗・検証文書のみ。コード/依存/OS設定の変更なし。コードテストは再実行せず、直前のPython88件中84成功・4スキップとNode42件を参照。実API会話、ウェイクワード、Pi再起動、Windows実測は引き続き未完了。

### 利用者からの追加確認と生成なしの認証診断

- 利用者は、呼びかけを試した時の表示が「Start PC Service」、入力キーがGoogle AI Studio発行のGemini APIキーだったと回答。ホスト未接続時に呼びかけを検出しない上流仕様と整合するが、ホスト接続後の検出は未確認。キーの発行元だけでは有効性やLive API利用可否は確定しない。
- Git除外の `python3 .runtime/auth-check.py` を用意し、Piで非表示入力する診断画面を表示。固定HTTPS先の `GET /v1beta/models?pageSize=1` をボタン操作1回につき1回だけ実行し、生成APIを呼ばない。キーはHTTPヘッダーだけに設定し、入力欄を即時消去。プロキシ・リダイレクト・自動再試行を無効化した。
- 診断の出力はHTTP番号、固定結果、許可したGoogleエラーstatus/reasonのみ。本文・メタデータ・キーを出力せず、結果だけをGit除外のモード600ファイルに保存する。成功してもLive API会話の成功とは扱わない。
- `python3 .runtime/auth-check.py --self-test`: 秘密文字列/任意reasonの除外、既知認証理由の保持、不正JSON、200応答、リダイレクト拒否のオフライン確認が成功。実キーによる診断でHTTP 400、status=INVALID_ARGUMENT、reason=API_KEY_INVALIDを確認。Googleが今回入力されたキーを無効として拒否していることを特定。発行元が異なるという仮説は利用者回答で退けたが、誤コピー・削除済み等の内訳は不明。Pi画面での再コピー/必要なら再発行を案内した。ホスト実装の不具合を示す証拠はなく、製品コードは変更していない。

### 認証GETの再確認

- 利用者がPiの非表示入力で再確認し、固定イベント `http=200, result=MODELS_ACCESS_OK` を受信。モデル一覧への認証成功を確認した。キーの値や、同じキーを再コピーしたか新規発行したかは取得していない。
- モデル一覧の成功とLive APIの利用可否を区別し、有効なキーでホストを再起動して端末画面の遷移・呼びかけ・短い会話を再検証するよう案内。実API試験の承認は継続している。今回のGETでは音声生成APIを呼んでいない。

### 有効なキーでの呼びかけ・音声回答成功

- 同じ監督用GUIで利用者がキーをローカル入力しホストを開始。`ready → device-online → session-busy → turn-complete → voice-played → session-idle → stopped` を受信。キー再入力後の実API試行で音声生成完了と端末再生完了を確認した。初回AUTHを除外せず、失敗と再試行を別の結果として記録。
- 利用者も「呼びかけに反応し、音声で回答した」と回答。今回の呼びかけ・録音・Gemini Live・端末音声再生の単発試験は成功。端末ファームや登録特徴の変更なし。音声/質問/キーを共有ログやGitへ保存していない。
- 試験ハーネスは再生完了後にホストを停止。session-idleイベントは確認したが、連続する次の質問、実API処理中断、端末/Pi再起動後の実会話復帰、長時間稼働、声のPC試聴/保存は未検証。
- 更新はTODO、進捗、検証記録、raspi README。コード/依存/OS設定の変更なし。コードテストは直前の合格結果を参照し再実行せず、文書の差分チェックを実施する。

- GitHubでPR #4は `ad4e767` を先頭として `c581b22` へmerge済みであることを確認。後続の実機検証文書4ファイルは `docs/live-hardware-validation` branchで別PRにまとめる。実装の追加差分はない。

## 2026-10-23 開発経緯の整理と継続準備

- 利用者からTODOほか資料更新、push/merge、その後のコンパクト化と開発継続を明示指示された。
- README、TODO、PROGRESS、ROADMAP、RASPI_DEV_SETUP、ARCHITECTUREの古い未着手/未導入表示を実測に合わせ、DEVELOPMENT_HISTORYを追加。成功・失敗・未検証と承認済み運用判断を分離して記録。
- PR #5の先頭 `e90e344` がMERGEABLE/CLEANであることを確認した。今回の文書追加後に再度先頭・差分を確認してmergeする。コード変更なしのためPython/Nodeテストは再実行しない。既存結果はPython88件中84成功・4スキップ、Node42件。
- コンパクト化の継続用要約はhandoffスキルに従い一時ディレクトリへ保存し、Gitへ含めない。チャットを圧縮する操作ツールはこの接続にはないため、実際のチャット圧縮が完了したとは扱わない。
- 文書差分を自己レビューし、更新資料のローカルリンク不在0件、`git diff --check`成功。秘密値、音声、個人設定、端末ファーム、runtimeの混入なしを変更対象で確認。

## 2026-10-23 fixtureホストの反復質問・接続断回復

- PR #5を先頭 `eae235f`・MERGEABLE/CLEAN・変更文書9ファイル・CI設定なしで最終確認し、利用者承認に従い `1483b29` へmerge。mainをfast-forward同期し、`test/host-reconnection` branchへ移動。
- 継続要約を `/tmp/stackchan-raspi-handoff.md`（モード600）へ保存。チャットを圧縮する操作ツールはなく、公式の入力欄 `/compact` 操作が必要と利用者へ説明済み。実際の圧縮は未確認のまま、引継ぎ記録に基づき次工程を実施した。
- `server/test/wireless-host.test.ts` に実プロセスの回帰試験5件を追加。本番コード・Windows desktop・依存・端末ファーム・実機OS/ネットワーク設定の変更なし。子ホストは既存のキーを継承せず、127.0.0.1/32のfixtureだけを使用する。
  - 同じホストで3回の質問を完了し、各回のsession-idle・voice-playedとプロセス継続を確認。
  - 入力PCMのack後にtransportを切断し、再生完了0件のままidleへ復帰。再接続した質問は最後まで成功。
  - 出力開始後に先頭PCMフレームだけを受け取り、transport切断またはstopを送信。不完全な応答はvoice-playedを報告せず、再接続後の質問は完了。
  - 先頭出力フレームの受信後に自身のfixture子プロセスへSIGKILL。同一ポートで新ホストを起動し、質問が完了。Windowsではこの1件をスキップする。
- `PATH="$PWD/.runtime/node-v22.23.4-linux-arm64/bin:$PATH" npm --prefix server run build`: TypeScript build成功。
- `.runtime/node-v22.23.4-linux-arm64/bin/node --test --test-timeout=10000 server/dist/test/*.test.js`: 47件すべて成功、失敗/スキップ0、終了コード0。実API呼び出し・音声生成・実機操作は行っていない。
- Pythonは変更しておらず、前工程の88件中84成功・4スキップを参照して再実行しない。合成peerによるplayed通知は実スピーカー再生の証拠とはしない。実機Wi-Fi断、実API処理中断、Pi再起動、長時間稼働、Windows実測は未検証。
- 最終差分を自己レビューし、`git diff --check`成功、更新文書のローカルリンク不在0件、禁止対象の変更0件、検証後のwireless-host残存0件を確認した。
